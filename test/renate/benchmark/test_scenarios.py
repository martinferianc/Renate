# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from collections import Counter

import numpy as np
import pytest
import torch
from torchvision.transforms.functional import rotate

from dummy_datasets import DummyTorchVisionDataModule, DummyTorchVisionDataModuleWithChunks
from renate.benchmark.datasets.vision_datasets import TorchVisionDataModule
from renate.benchmark.scenarios import (
    BenchmarkScenario,
    ClassIncrementalScenario,
    FeatureSortingScenario,
    IIDScenario,
    ImageRotationScenario,
    PermutationScenario,
)
from renate.utils.pytorch import randomly_split_data


@pytest.mark.parametrize(
    "scenario_cls,kwargs",
    [
        [
            ImageRotationScenario,  # Wrong chunk id
            {"num_tasks": 3, "chunk_id": 4, "degrees": [0, 60, 180]},
        ],
        [
            ClassIncrementalScenario,
            {
                "num_tasks": 3,
                "chunk_id": 4,  # Wrong chunk id
                "class_groupings": [[0, 1, 2], [3, 5, 9], [4, 6, 7, 8]],
            },
        ],
        [PermutationScenario, {"num_tasks": 3, "chunk_id": 2}],  # Missing input dim
    ],
)
def test_failing_to_init(tmpdir, scenario_cls, kwargs):
    dataset_name = "FashionMNIST"
    data_module = TorchVisionDataModule(
        tmpdir, src_bucket=None, src_object_name=None, dataset_name=dataset_name
    )
    with pytest.raises(Exception):
        scenario_cls(data_module=data_module, **kwargs)


def test_class_incremental_scenario():
    data_module = DummyTorchVisionDataModule(val_size=0.3, seed=42)
    class_groupings = [[0, 1, 3], [2], [3, 4]]
    train_data_class_counts = Counter({3: 16, 4: 15, 0: 15, 2: 13, 1: 11})
    val_data_class_counts = Counter({1: 9, 2: 7, 4: 5, 0: 5, 3: 4})
    test_data_class_counts = Counter({0: 20, 1: 20, 2: 20, 3: 20, 4: 20})
    for i in range(len(class_groupings)):
        scenario = ClassIncrementalScenario(
            data_module=data_module, class_groupings=class_groupings, chunk_id=i
        )
        scenario.prepare_data()
        scenario.setup()
        train_data = scenario.train_data()
        val_data = scenario.val_data()
        assert len(train_data) == sum([train_data_class_counts[c] for c in class_groupings[i]])
        assert len(val_data) == sum([val_data_class_counts[c] for c in class_groupings[i]])
        for j, test_data in enumerate(scenario.test_data()):
            assert len(test_data) == sum([test_data_class_counts[c] for c in class_groupings[j]])


def test_class_incremental_scenario_class_grouping_error():
    """Classes selected do not exist in data."""
    scenario = ClassIncrementalScenario(
        data_module=DummyTorchVisionDataModule(val_size=0.3, seed=42),
        class_groupings=[[0, 1, 3], [2, 200]],
        chunk_id=0,
    )
    scenario.prepare_data()
    with pytest.raises(ValueError, match=r"Chunk 1 does not contain classes \[200\]."):
        scenario.setup()


def test_image_rotation_scenario():
    data_module = DummyTorchVisionDataModule(val_size=0.3)
    degrees = [15, 75]
    for i in range(len(degrees)):
        scenario = ImageRotationScenario(
            data_module=data_module,
            degrees=degrees,
            chunk_id=i,
            seed=data_module._seed,
        )
        scenario.prepare_data()
        scenario.setup()
        for stage in ["train", "val"]:
            scenario_data = getattr(scenario, f"{stage}_data")()
            orig_data_module_data = getattr(data_module, f"{stage}_data")()
            split_orig_data_module_data = randomly_split_data(
                orig_data_module_data, [0.5, 0.5], seed=data_module._seed
            )[i]
            assert len(scenario_data) == len(split_orig_data_module_data)
            for j in range(len(scenario_data)):
                assert torch.equal(
                    rotate(split_orig_data_module_data[j][0], degrees[i]), scenario_data[j][0]
                )
        for j, test_data in enumerate(scenario.test_data()):
            assert len(test_data) == len(data_module.test_data())
            for k in range(len(test_data)):
                assert torch.equal(
                    rotate(data_module.test_data()[k][0], degrees[j]), test_data[k][0]
                )


def test_permutation_scenario():
    data_module = DummyTorchVisionDataModule(val_size=0.3)
    for i in range(3):
        scenario = PermutationScenario(
            data_module=data_module,
            num_tasks=3,
            input_dim=np.prod(data_module.input_shape),
            chunk_id=i,
            seed=data_module._seed,
        )
        scenario.prepare_data()
        scenario.setup()
        for stage in ["train", "val"]:
            scenario_data = getattr(scenario, f"{stage}_data")()
            orig_data_module_data = getattr(data_module, f"{stage}_data")()
            split_orig_data_module_data = randomly_split_data(
                orig_data_module_data, [1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0], seed=data_module._seed
            )[i]
            assert len(scenario_data) == len(split_orig_data_module_data)
            for j in range(len(scenario_data)):
                a, _ = torch.sort(split_orig_data_module_data[j][0].flatten())
                b, _ = torch.sort(scenario_data[j][0].flatten())
                assert torch.equal(a, b)
        for j, test_data in enumerate(scenario.test_data()):
            assert len(test_data) == len(data_module.test_data())
            for k in range(len(test_data)):
                a, _ = torch.sort(data_module.test_data()[k][0].flatten())
                b, _ = torch.sort(test_data[k][0].flatten())
                assert torch.equal(a, b)


@pytest.mark.parametrize(
    "scenario_class, scenario_kwargs",
    (
        (ImageRotationScenario, {"degrees": [0, 90, 180, 270]}),
        (PermutationScenario, {"num_tasks": 4, "input_dim": (1, 5, 5)}),
    ),
)
def test_transforms_in_transform_scenarios_are_distinct(scenario_class, scenario_kwargs):
    """Tests if transformations are different.

    Checks two cases: 1) transforms must not be same objects and 2) transforms must not perform
    identical operations.
    """
    data_module = DummyTorchVisionDataModule()
    scenario = scenario_class(data_module=data_module, **scenario_kwargs, chunk_id=0, seed=0)
    scenario.prepare_data()
    scenario.setup()
    x = data_module.X_train[0]
    for i, transform in enumerate(scenario._transforms):
        for j, transform2 in enumerate(scenario._transforms):
            if i == j:
                continue
            assert transform != transform2
            assert not torch.all(torch.isclose(transform(x), transform2(x)))


def test_benchmark_scenario():
    data_module = DummyTorchVisionDataModuleWithChunks(num_chunks=3, val_size=0.2)
    for chunk_id in range(3):
        scenario = BenchmarkScenario(data_module=data_module, num_tasks=3, chunk_id=chunk_id)
        scenario.prepare_data()
        scenario.setup()
        assert scenario.train_data() is not None
        assert scenario.val_data() is not None
        assert len(scenario.test_data()) == 3


def test_iid_scenario():
    """Tests that the IID scenario creates a non-overlapping split."""
    data_module = DummyTorchVisionDataModule(val_size=0.3)
    counter = {}
    for i in range(3):
        scenario = IIDScenario(
            data_module=data_module,
            num_tasks=3,
            chunk_id=i,
            seed=data_module._seed,
        )
        scenario.prepare_data()
        scenario.setup()
        for stage in ["train", "val"]:
            scenario_data = getattr(scenario, f"{stage}_data")()
            for j in range(len(scenario_data)):
                x, y = scenario_data[j]
                assert x not in counter
                counter[x] = 1
        assert len(scenario.test_data()) == 3


@pytest.mark.parametrize("feature_idx", (0, 1))
def test_feature_sorting_scenario(feature_idx):
    """Tests the FeatureSortingScenario.

    Checks for increasing feature values across chunks.
    """
    data_module = DummyTorchVisionDataModule(val_size=0.3)
    num_tasks = 3
    max_value = {"train": -float("inf"), "val": -float("inf")}
    for i in range(3):
        scenario = FeatureSortingScenario(
            data_module=data_module,
            num_tasks=num_tasks,
            feature_idx=feature_idx,
            randomness=0,
            chunk_id=i,
            seed=data_module._seed,
        )
        scenario.prepare_data()
        scenario.setup()
        for stage in ["train", "val"]:
            scenario_data = getattr(scenario, f"{stage}_data")()
            features = [x[0, feature_idx].mean().item() for x, _ in scenario_data]
            chunk_min = min(features)
            chunk_max = max(features)
            assert max_value[stage] <= chunk_min
            max_value[stage] = chunk_max
        assert len(scenario.test_data()) == num_tasks
