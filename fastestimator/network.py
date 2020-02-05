# Copyright 2019 The FastEstimator Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
import pdb
from collections import ChainMap
from typing import Any, Dict, List, Mapping, Set, Union

import tensorflow as tf
import torch

from fastestimator.op import TensorOp, get_inputs_by_op, get_ops_by_mode, write_outputs_by_key
from fastestimator.op.tensorop.model import ModelOp, UpdateOp
from fastestimator.schedule import Scheduler
from fastestimator.util.util import NonContext, to_list


class BaseNetwork:
    def __init__(self, ops, models):
        self.ops = to_list(ops)
        self.models = models
        self.effective_inputs = self.get_effective_input_keys()
        self.all_outputs = self.get_all_output_keys()
        self.effective_outputs = set()

    def get_effective_input_keys(self) -> Set[str]:
        input_keys = set()
        produced_keys = set()
        for op in self.ops:
            #gather input keys
            if isinstance(op, Scheduler):
                keys_lists = [to_list(x.inputs) for x in op.epoch_dict.values() if not x is None]
                for keys_list in keys_lists:
                    input_keys.update(set(key for key in keys_list if not key in produced_keys))
            else:
                input_keys.update(set(key for key in to_list(op.inputs) if not key in produced_keys))
            #keep track of intermediate output keys
            if isinstance(op, Scheduler):
                keys_lists = [x.outputs for x in op.epoch_dict.values() if not x is None]
                if all(map(lambda x: x == keys_lists[0], keys_lists)):
                    produced_keys.update(keys_lists[0])
            else:
                produced_keys.update(to_list(op.outputs))
        input_keys -= {None}
        return input_keys

    def get_all_output_keys(self) -> Set[str]:
        output_keys = set()
        for op in self.ops:
            if isinstance(op, Scheduler):
                keys_lists = [to_list(x.outputs) for x in op.epoch_dict.values() if not x is None]
                for keys_list in keys_lists:
                    output_keys.update(keys_list)
            else:
                output_keys.update(to_list(op.outputs))
        output_keys -= {None}
        return output_keys

    @staticmethod
    def _forward_batch(batch: Mapping[str, Any], state: Dict[str, Any], ops: List[TensorOp]):
        data = None
        for op in ops:
            data = get_inputs_by_op(op, batch, data)
            data = op.forward(data, state)
            if op.outputs:
                write_outputs_by_key(batch, data, op.outputs)


def Network(ops):
    models = set()
    for op in ops:
        if isinstance(op, Scheduler):
            models_in_schedule = set(x.model for x in op.epoch_dict.values() if isinstance(x, (ModelOp, UpdateOp)))
            models.update(models_in_schedule)
        elif isinstance(op, (ModelOp, UpdateOp)):
            models.add(op.model)
    assert models, "cannot find model in Network ops"

    framework = set()
    for model in models:
        if isinstance(model, tf.keras.Model):
            framework.add("tensorflow")
        elif isinstance(model, torch.nn.Module):
            framework.add("pytorch")
    assert len(framework) == 1, "please make sure either tensorflow or torch model is used in network"

    if framework.pop() == "tensorflow":
        network = TFNetwork(ops, models)
    else:
        network = TorchNetwork(ops, models)
    return network


class TorchNetwork(BaseNetwork):
    def __init__(self, ops, models):
        super().__init__(ops, models)
        self.device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        if self.device.type == "cuda":
            for model in self.models:
                model.to(self.device)

    def run_step(self, batch: Dict[str, Any], state: Dict[str, Any], debug: bool = False) -> Dict[str, Any]:
        """Execute the ops in Network
        Args:
            batch : dictionary that contains batch data after the pipeline
            state : dictionary that contains meta data
            debug : whether to run in eager mode (only available for TFNetwork)
        Returns:
            dictionary containing the predictions of current epoch
        """
        new_batch = {}
        ops = get_ops_by_mode(self.ops, state["mode"])
        for key in self.effective_inputs:
            if key in batch:
                new_batch[key] = batch[key]
        prediction = self._forward_step(new_batch, state, ops, self.effective_outputs)
        return prediction

    def _forward_step(self,
                      batch: Dict[str, Any],
                      state: Dict[str, Any],
                      ops: List[TensorOp],
                      effective_outputs: Set[str]) -> Dict[str, Any]:
        prediction = {}
        mode = state["mode"]
        state["tape"] = NonContext()
        if self.device.type == "cuda":
            for key, val in batch.items():
                batch[key] = val.to(self.device)
        with torch.no_grad() if mode != "train" else NonContext():
            self._forward_batch(batch, state, ops)
        for key in effective_outputs:
            if key in batch:
                value = batch[key]
                if self.device.type == "cuda":
                    value = value.to("cpu")
                prediction[key] = value
        return prediction


class TFNetwork(BaseNetwork):
    def __init__(self, ops, models):
        super().__init__(ops, models)

    def run_step(self, batch: Dict[str, Any], state: Dict[str, Any], debug: bool = False) -> Dict[str, Any]:
        """Execute the ops in Network
        Args:
            batch : dictionary that contains batch data after the pipeline
            state : dictionary that contains meta data
            debug : whether to run in eager mode (only available for TFNetwork)
        Returns:
            dictionary containing the predictions of current epoch
        """
        new_batch = {}
        ops = get_ops_by_mode(self.ops, state["mode"])
        for key in self.effective_inputs:
            if key in batch:
                new_batch[key] = batch[key]
        if debug:
            prediction = self._forward_step_eager(new_batch, state, ops, self.effective_outputs)
        else:
            prediction = self._forward_step_static(new_batch, state, ops, to_list(self.effective_outputs))
        return prediction

    def _forward_step_eager(self,
                            batch: Dict[str, Any],
                            state: Dict[str, Any],
                            ops: List[TensorOp],
                            effective_outputs: Set[str]) -> Dict[str, Any]:
        batch = ChainMap({}, batch)
        prediction = {}
        mode = state["mode"]
        # use gradient tape for tensorflow train, otherwise use a dummy tape
        with tf.GradientTape(persistent=True) if mode == "train" else NonContext() as tape:
            state['tape'] = tape
            self._forward_batch(batch, state, ops)
        del state['tape']
        del tape
        for key in effective_outputs:
            if key in batch:
                prediction[key] = batch[key]
        return prediction

    @tf.function
    def _forward_step_static(self,
                             batch: Dict[str, Any],
                             state: Dict[str, Any],
                             ops: List[TensorOp],
                             effective_outputs: List[str]) -> Dict[str, Any]:
        batch = ChainMap({}, batch)
        prediction = {}
        mode = state["mode"]
        # use gradient tape for tensorflow train, otherwise use a dummy tape
        with tf.GradientTape(persistent=True) if mode == "train" else NonContext() as tape:
            state['tape'] = tape
            self._forward_batch(batch, state, ops)
        del state['tape']
        del tape
        for key in effective_outputs:
            if key in batch:
                prediction[key] = batch[key]
        return prediction


def build(model: Union[tf.keras.Model, torch.nn.Module, List[tf.keras.Model], List[torch.nn.Module]],
          optimizer: Union[str,
                           List[str],
                           tf.optimizers.Optimizer,
                           List[tf.optimizers.Optimizer],
                           torch.optim.Optimizer,
                           List[torch.optim.Optimizer]]
          ) -> Union[tf.keras.Model, torch.nn.Module, List[tf.keras.Model], List[torch.nn.Module]]:
    """Associate model instance(s) with optimizer(s)
    Args:
        model: model instances or list of model instances
        optimizer: optimizer instance/string or list of optimizer instance/string
    Returns:
        models: model(s) compiled by FastEstimator
    """
    models = to_list(model)
    optimizers = to_list(optimizer)
    assert len(models) == len(optimizers)
    for idx, (model, optimizer) in enumerate(zip(models, optimizers)):
        models[idx] = _fe_compile(model, optimizer)
    if len(models) == 1:
        models = models[0]
    return models


def _fe_compile(model: Union[tf.keras.Model, torch.nn.Module],
                optimizer: Union[str, tf.optimizers.Optimizer, torch.optim.Optimizer]
                ) -> Union[tf.keras.Model, torch.nn.Module]:
    # model instance check
    if isinstance(model, tf.keras.Model):
        framework = "tensorflow"
    elif isinstance(model, torch.nn.Module):
        framework = "pytorch"
    else:
        raise ValueError("unrecognized model format: {}".format(type(model)))

    # optimizer auto complete
    if isinstance(optimizer, str):
        tf_optimizer_fn = {
            'adadelta': tf.optimizers.Adadelta,
            'adagrad': tf.optimizers.Adagrad,
            'adam': tf.optimizers.Adam,
            'adamax': tf.optimizers.Adamax,
            'rmsprop': tf.optimizers.RMSprop,
            'sgd': tf.optimizers.SGD
        }
        pytorch_optimizer_fn = {
            'adadelta': torch.optim.Adadelta,
            'adagrad': torch.optim.Adagrad,
            'adam': torch.optim.Adam,
            'adamax': torch.optim.Adamax,
            'rmsprop': torch.optim.RMSprop,
            'sgd': torch.optim.SGD
        }
        if framework == "tensorflow":
            optimizer = tf_optimizer_fn[optimizer]()
        else:
            optimizer = pytorch_optimizer_fn[optimizer](params=model.parameters())

    # optimizer instance check
    if framework == "tensorflow":
        assert isinstance(optimizer, tf.optimizers.Optimizer)
    else:
        assert isinstance(optimizer, torch.optim.Optimizer)
        optimizer.zero_grad()

    model.optimizer = optimizer
    model.fe_compiled = True
    return model
