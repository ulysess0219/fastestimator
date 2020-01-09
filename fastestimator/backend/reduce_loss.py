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
import tensorflow as tf
import torch


def reduce_loss(loss):
    if isinstance(loss, tf.Tensor):
        assert len(loss.shape) < 2, "loss must be one-dimentional or scalar"
        if len(loss.shape) == 1:
            loss = tf.reduce_mean(loss)
    elif isinstance(loss, torch.Tensor):
        assert loss.ndim < 2, "loss must be one-dimentional or scalar"
        if loss.ndim == 1:
            loss = torch.mean(loss)
    else:
        raise ValueError("loss must be either tf.Tensor or torch.Tensor")
    return loss
