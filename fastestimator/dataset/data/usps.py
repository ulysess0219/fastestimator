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
import gzip
import os
from multiprocessing import Pool
from pathlib import Path
from typing import Tuple, Optional

import numpy as np
import wget
from PIL import Image

from fastestimator.dataset import LabeledDirDataset
from fastestimator.util import bar_custom, callback_progress

wget.callback_progress = callback_progress


def _write_image(image: np.ndarray, path: str, idx: int, mode: str):
    image = (image - image.min()) / max(image.max() - image.min(), 1e-8) * 255
    img = Image.fromarray(image.astype(np.uint8))
    img.save(os.path.join(path, '{}_{}.png'.format(mode, idx)))


def _write_data(images: np.ndarray, labels: np.ndarray, base_path: str, mode: str):
    if not os.path.exists(base_path):
        print("Writing image data to {}".format(base_path))
        os.makedirs(base_path)
        for i in range(min(labels), max(labels) + 1):
            os.makedirs(os.path.join(base_path, "{}".format(i)))
        with Pool(os.cpu_count()) as p:
            p.starmap(
                _write_image,
                zip(images,
                    map(lambda l: os.path.join(base_path, "{}".format(l)), labels),
                    range(len(labels)), (mode for _ in range(len(labels)))))


def _extract_images_labels(filename: str) -> Tuple[np.ndarray, np.ndarray]:
    # https://github.com/haeusser/learning_by_association/blob/master/semisup/tools/usps.py
    print('Extracting', filename)
    with gzip.open(filename, 'rb') as f:
        raw_data = f.read().split()
    data = np.asarray([raw_data[start:start + 257] for start in range(0, len(raw_data), 257)], dtype=np.float32)
    images_vec = data[:, 1:]
    images = np.reshape(images_vec, (images_vec.shape[0], 16, 16))
    labels = data[:, 0].astype(int)
    return images, labels


def load_data(root_dir: Optional[str] = None) -> Tuple[LabeledDirDataset, LabeledDirDataset]:
    """
    Download the USPS dataset to local storage if not already downloaded
    Args:
        root_dir: The path to store the USPS data. If not provided then data is saved to `fastestimator_data` in the
                  users home directory
    Returns:
        (TrainData, TestData)
    """
    home = str(Path.home())

    if root_dir is None:
        root_dir = os.path.join(home, 'fastestimator_data', 'USPS')
    else:
        root_dir = os.path.join(os.path.abspath(root_dir), 'USPS')
    os.makedirs(root_dir, exist_ok=True)

    # download data to memory
    train_compressed_path = os.path.join(root_dir, "zip.train.gz")
    test_compressed_path = os.path.join(root_dir, "zip.test.gz")
    train_base_path = os.path.join(root_dir, "train")
    test_base_path = os.path.join(root_dir, "test")

    if not os.path.exists(train_base_path):
        if not os.path.exists(train_compressed_path):
            print("Downloading train data to {}".format(root_dir))
            wget.download('http://statweb.stanford.edu/~tibs/ElemStatLearn/datasets/zip.train.gz',
                          root_dir,
                          bar=bar_custom)
        train_images, train_labels = _extract_images_labels(train_compressed_path)
        _write_data(train_images, train_labels, train_base_path, "train")

    if not os.path.exists(test_base_path):
        if not os.path.exists(test_compressed_path):
            print("Downloading test data to {}".format(root_dir))
            wget.download('http://statweb.stanford.edu/~tibs/ElemStatLearn/datasets/zip.test.gz',
                          root_dir,
                          bar=bar_custom)
        test_images, test_labels = _extract_images_labels(test_compressed_path)
        _write_data(test_images, test_labels, test_base_path, "test")

    # make datasets
    return LabeledDirDataset(train_base_path, file_extension=".png"), LabeledDirDataset(test_base_path,
                                                                                        file_extension=".png")
