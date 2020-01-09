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
import numpy as np
from typing import Union, List, Optional
from fastestimator.op import NumpyOp


class Minmax(NumpyOp):
    """Normalize data using the minmax method
    
    Args:
            inputs (List[str], str, None): Key(s) of images to be normalized
            outputs (List[str], str, None): Key(s) of images to be normalized
            mode (str, None): What execution mode (train, eval, None) to apply this operation
            epsilon (float): A small value to prevent numeric instability in the division
    """
    def __init__(self,
                 inputs: Union[List[str], str, None] = None,
                 outputs: Union[List[str], str, None] = None,
                 mode: Optional[str] = None,
                 epsilon: float = 1e-7):
        super().__init__(inputs=inputs, outputs=outputs, mode=mode)
        self.epsilon = epsilon

    def forward(self, data, state):
        """Normalizes the data

        Args:
            data: Data to be normalized
            state: A dictionary containing background information such as 'mode'

        Returns:
            Normalized numpy array
        """
        data_max = np.max(data)
        data_min = np.min(data)
        data = (data - data_min) / max((data_max - data_min), self.epsilon)
        return data.astype(np.float32)
