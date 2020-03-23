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
from copy import deepcopy
from typing import List

import numpy as np
from torch.utils.data import Dataset

from fastestimator.dataset import BatchDataset
from fastestimator.op import NumpyOp, get_inputs_by_op, write_outputs_by_op


class OpDataset(Dataset):
    def __init__(self, dataset: Dataset, ops: List[NumpyOp], mode: str):
        self.dataset = dataset
        if isinstance(self.dataset, BatchDataset):
            self.dataset.shuffle()
        self.ops = ops
        self.mode = mode

    def __getitem__(self, index):
        items = deepcopy(self.dataset[index])  # Deepcopy to prevent ops from overwriting values in datasets
        if isinstance(self.dataset, BatchDataset):
            for item in items:
                self._forward(item)
            items = {key: np.array([item[key] for item in items]) for key in items[0]}
        else:
            self._forward(items)
        return items

    def __len__(self):
        return len(self.dataset)

    def _forward(self, item):
        op_data = None
        for op in self.ops:
            op_data = get_inputs_by_op(op, item, op_data)
            op_data = op.forward(op_data, {"mode": self.mode})
            if op.outputs:
                write_outputs_by_op(op, item, op_data)
        return item
