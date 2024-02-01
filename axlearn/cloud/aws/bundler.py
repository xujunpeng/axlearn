# Copyright © 2024 Amazon Inc.

"""Code bundling utilities.

The type of bundler to use is determined by `--bundler_type`. Bundlers can also be configured via
`--bundler_spec` flags; see the corresponding bundler class' `from_spec` method for details.

Examples (elastic container registry):

    # Docker build and push to repo.
    axlearn aws bundle --bundler_type=containerregistry \
        --name=my-tag \
        --bundler_spec=image=my-image \
        --bundler_spec=repo=my-repo \
        --bundler_spec=dockerfile=Dockerfile \
        --bundler_spec=build_arg1=my-build-arg

"""

import os
import subprocess
from typing import Dict

from absl import app, flags, logging

from axlearn.cloud.common.bundler import BaseDockerBundler, BaseTarBundler, DockerBundler
from axlearn.cloud.common.bundler import main as bundler_main
from axlearn.cloud.common.bundler import main_flags as bundler_main_flags
from axlearn.cloud.common.bundler import register_bundler
from axlearn.cloud.common.docker import registry_from_repo
from axlearn.cloud.aws.config import aws_settings
from axlearn.cloud.aws.utils import common_flags

FLAGS = flags.FLAGS

@register_bundler
class ArtifactRegistryBundler(DockerBundler):
    """A DockerBundler that reads configs from aws_settings, and auths to Elastic Container Registry."""

    TYPE = "containerregistry"

    @classmethod
    def default_config(cls):
        cfg = super().default_config()
        cfg.repo = aws_settings("docker_repo", required=False)
        cfg.dockerfile = aws_settings("default_dockerfile", required=False)
        return cfg

    def _build_and_push(self, *args, **kwargs):
        cfg = self.config
        aws_region = aws_settings("aws_region", required=False)
        exit()
        cmd = f"aws ecr get-login-password " \
              f"--region {aws_region} " \
              f"| docker login --username AWS " \
              f"--password-stdin {registry_from_repo(cfg.repo)}"
        subprocess.run(cmd,
            check=True,
            shell=True
        )
        return super()._build_and_push(*args, **kwargs)

if __name__ == "__main__":
    common_flags()
    bundler_main_flags()
    app.run(bundler_main)
