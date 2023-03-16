# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import Optional, Tuple

import torch

from dummy_datasets import DummyTorchVisionDataModule
from renate.benchmark.models.mlp import MultiLayerPerceptron
from renate.benchmark.scenarios import ClassIncrementalScenario
from renate.data.data_module import RenateDataModule
from renate.models import RenateModule


def model_fn(model_state_url: Optional[str] = None) -> RenateModule:
    if model_state_url is None:
        return MultiLayerPerceptron(5 * 5, 10, 0, 64)
    state_dict = torch.load(model_state_url)
    return MultiLayerPerceptron.from_state_dict(state_dict)


def data_module_fn(
    data_path: str,
    chunk_id: Optional[int] = None,
    val_size: float = 0.0,
    seed: int = 0,
    use_scenario: bool = False,
    class_groupings: Tuple[Tuple[int]] = ((0, 1), (2, 3, 4)),
    optional_tuple: Optional[Tuple[float]] = None,
    optional_float: Optional[float] = None,
    list_param: list = [1, 2],
) -> RenateDataModule:
    data_module = DummyTorchVisionDataModule(transform=None, val_size=val_size, seed=seed)
    if use_scenario:
        return ClassIncrementalScenario(
            data_module=data_module,
            chunk_id=chunk_id,
            class_groupings=class_groupings,
        )
    return data_module
