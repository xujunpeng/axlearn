# Copyright © 2023 Apple Inc.

"""AXLearn Google Cloud CLI."""

import logging

from axlearn.cli.utils import CommandGroup, get_path
from axlearn.cloud.common.config import load_configs
from axlearn.cloud.common.docker import registry_from_repo
from axlearn.cloud.common.utils import infer_cli_name
from axlearn.cloud.aws.config import CONFIG_NAMESPACE


def add_cmd_group(*, parent: CommandGroup):
    """Adds the root AWS command group."""

    aws_cmd = CommandGroup("aws", parent=parent)

    _, aws_configs = load_configs(CONFIG_NAMESPACE, required=True)
    active_config = aws_configs.get("_active", None)

    if active_config is None:
        logging.warning(
            "No AWS project has been activated; please run `%s aws config activate`.",
            infer_cli_name(),
        )

    # Set common flags.
    aws_cmd.add_flag(
        "--project", undefok=True, default=get_path(aws_configs, f"{active_config}.project", None)
    )
    aws_cmd.add_flag(
        "--region", undefok=True, default=get_path(aws_configs, f"{active_config}.aws_region", None)
    )

    # Configure projects.
    aws_cmd.add_cmd_from_module(
        "config", module="axlearn.cloud.aws.config", help="Configure AWS settings"
    )

    # Interact with jobs.
    # TODO(markblee): Make the distinction between launch, tpu, and bastion more clear.
    aws_cmd.add_cmd_from_module(
        "bundle",
        module="axlearn.cloud.aws.bundler",
        help="Bundle the local directory",
    )
    aws_cmd.add_cmd_from_module(
        "bastion",
        module="axlearn.cloud.aws.jobs.bastion_vm",
        help="Launch jobs through Bastion orchestrator",
    )

    """
    # Interact with compute.
    aws_cmd.add_cmd_from_bash("sshvm", command="gcloud compute ssh", help="SSH into a VM")
    aws_cmd.add_cmd_from_bash(
        "sshtpu",
        command="gcloud alpha compute tpus tpu-vm ssh",
        help="SSH into a TPU-VM",
    )

    aws_cmd.add_cmd_from_module(
        "launch",
        module="axlearn.cloud.aws.jobs.launch",
        help="Launch arbitrary commands on remote compute",
    )
    aws_cmd.add_cmd_from_module(
        "tpu",
        module="axlearn.cloud.aws.jobs.tpu_runner",
        help="Create a TPU-VM and execute the given command on it",
    )
    aws_cmd.add_cmd_from_module(
        "vm",
        module="axlearn.cloud.aws.jobs.cpu_runner",
        help="Create a VM and execute the given command on it",
    )
    aws_cmd.add_cmd_from_module(
        "dataflow",
        module="axlearn.cloud.aws.jobs.dataflow",
        help="Run Dataflow jobs locally or on AWS",
    )
    """

    # Auth command.
    docker_repo = get_path(aws_configs, f"{active_config}.docker_repo", None)
    aws_region = get_path(aws_configs, f"{active_config}.aws_region")
    #auth_command = "gcloud auth login && gcloud auth application-default login"
    auth_command = "aws configure"
    if docker_repo:
        # Note: we currently assume that docker_repo is a AWS one.
        auth_command += f" && aws ecr get-login-password " \
                        f"--region {aws_region} |" \
                        f"docker login --username AWS " \
                        f"--password-stdin {registry_from_repo(docker_repo)}"
    aws_cmd.add_cmd_from_bash(
        "auth",
        command=auth_command,
        help="Authenticate to AWS",
        # Match no flags -- `gcloud auth ...` doesn't support `--project`, `--zone`, etc.
        filter_argv="a^",
    )
