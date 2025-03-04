# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import boto3
from syne_tune.backend.sagemaker_backend.sagemaker_utils import get_execution_role

from renate.training import run_training_job

config_space = {
    "optimizer": "SGD",
    "momentum": 0.9,
    "weight_decay": 0.0,
    "learning_rate": 0.001,
    "alpha": 0.5,
    "batch_size": 32,
    "memory_batch_size": 32,
    "memory_size": 300,
    "loss_normalization": 0,
    "loss_weight": 0.5,
}

if __name__ == "__main__":
    AWS_ID = boto3.client("sts").get_caller_identity().get("Account")
    AWS_REGION = "us-west-2"  # use your AWS preferred region here

    run_training_job(
        config_space=config_space,
        mode="max",
        metric="val_accuracy",
        updater="ER",  # we train with Experience Replay
        max_epochs=5,
        config_file="renate_config.py",
        # For this example, we can train on two binary movie review datasets: "rotten_tomatoes" and
        # "imdb". Set chunk_id to [0, 1] to switch between the two.
        chunk_id=0,
        # replace the url below with a different one if you already ran it and you want to avoid
        # overwriting
        output_state_url=f"s3://sagemaker-{AWS_REGION}-{AWS_ID}/renate-training-nlp-finetuning/",
        # uncomment the line below only if you already created a model with this script and you want
        # to update it
        # input_state_url=f"s3://sagemaker-{AWS_REGION}-{AWS_ID}/renate-training-nlp-finetuning/",
        backend="sagemaker",  # run on SageMaker, select "local" to run this locally
        role=get_execution_role(),
        instance_count=1,
        instance_type="ml.g4dn.xlarge",
        job_name="renate-training-nlp-finetuning",
    )
