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

from typing import Set, Union

import numpy as np
from sklearn.metrics import confusion_matrix

from fastestimator.backend import to_number
from fastestimator.trace import Trace
from fastestimator.util import Data


class ConfusionMatrix(Trace):
    """Computes confusion matrix between y_true and y_predict.

    Args:
        true_key: Name of the key that corresponds to ground truth in batch dictionary
        pred_key: Name of the key that corresponds to predicted score in batch dictionary
        num_classes: Total number of classes of the confusion matrix.
        mode: Restrict the trace to run only on given modes {'train', 'eval', 'test'}. None will always
                    execute. Defaults to 'eval'.
        output_name: Name of the key to store to the state. Defaults to "confusion_matrix".
    """
    def __init__(self,
                 true_key: str,
                 pred_key: str,
                 num_classes: int,
                 mode: Union[str, Set[str]] = ("eval", "test"),
                 output_name: str = "confusion_matrix"):
        super().__init__(inputs=(true_key, pred_key), outputs=output_name, mode=mode)
        self.num_classes = num_classes
        self.matrix = None

    @property
    def true_key(self):
        return self.inputs[0]

    @property
    def pred_key(self):
        return self.inputs[1]

    def on_epoch_begin(self, data: Data):
        self.matrix = None

    def on_batch_end(self, data: Data):
        y_true, y_pred = to_number(data[self.true_key]), to_number(data[self.pred_key])
        if y_true.shape[-1] > 1 and y_true.ndim > 1:
            y_true = np.argmax(y_true, axis=-1)
        if y_pred.shape[-1] > 1:
            y_pred = np.argmax(y_pred, axis=-1)
        else:
            y_pred = np.round(y_pred)
        assert y_pred.size == y_true.size

        batch_confusion = confusion_matrix(y_true, y_pred, labels=list(range(0, self.num_classes)))

        if self.matrix is None:
            self.matrix = batch_confusion
        else:
            self.matrix += batch_confusion

    def on_epoch_end(self, data: Data):
        data.write_with_log(self.outputs[0], self.matrix)
