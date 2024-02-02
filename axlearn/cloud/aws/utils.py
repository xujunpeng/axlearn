# Copyright © 2023 Apple Inc.

"""GCP general-purpose utilities."""

import functools
import re
import subprocess
import sys
from typing import Optional, Sequence

import google.auth
import boto3
from botocore.exceptions import NoCredentialsError
from absl import flags, logging
from google.auth import exceptions as gauthexceptions
from google.auth import impersonated_credentials
from google.auth.credentials import Credentials

from axlearn.cloud.common.utils import infer_cli_name
from axlearn.cloud.gcp.scopes import DEFAULT_APPLICATION


def common_flags(**kwargs):
    """Defines common AWS flags. Keyword args will be forwarded to flag definitions."""
    flags.DEFINE_string("project", None, "The AWS project name.", **kwargs)
    flags.DEFINE_string("region", None, "The AWS region name.", **kwargs)
    flags.DEFINE_string("ami_id", None, "The EC2 AMI Id", **kwargs)
    flags.DEFINE_string("instance_type", None, "The EC2 instance type.", **kwargs)
    flags.DEFINE_string("key_pair_name", None, "The the key pair used to login to EC2 instance.", **kwargs)


def running_from_vm() -> bool:
    """Check if we're running from GCP VM.

    Reference:
    https://cloud.google.com/compute/docs/instances/detect-compute-engine#use_the_metadata_server_to_detect_if_a_vm_is_running_in
    """
    out = subprocess.run(
        ["curl", "-s", "metadata.google.internal", "-i"],  # Curl silently.
        check=False,
        capture_output=True,
        text=True,
    )
    return (out.returncode == 0) and "Metadata-Flavor: Google" in out.stdout


def is_valid_resource_name(name: Optional[str]) -> bool:
    """Validates names (e.g. TPUs, VMs, jobs) to ensure compat with GCP.

    Reference:
    https://cloud.google.com/compute/docs/naming-resources#resource-name-format
    """
    return name is not None and re.fullmatch(r"^[a-z]([-a-z0-9]*[a-z0-9])?", name) is not None


def catch_auth(fn):
    """Wraps a function by catching auth errors."""

    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        try:
            fn(*args, **kwargs)
        except gauthexceptions.RefreshError:
            logging.error("Please run `%s gcp auth`.", infer_cli_name())
            sys.exit(1)

    return wrapped
