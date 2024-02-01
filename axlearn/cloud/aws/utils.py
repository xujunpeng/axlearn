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
    flags.DEFINE_string("zone", None, "The AWS region name.", **kwargs)


def get_credentials(
    *,
    impersonate_account: Optional[str] = None,
    impersonate_scopes: Optional[Sequence[str]] = None,
) -> Credentials:
    """Get aws credentials, or exits if unauthenticated.

    Args:
        impersonate_account: Service account to impersonate, if not None.
        impersonate_scopes: Scopes of the impersonation token,

    Returns:
        An authorized set of credentials.
    """

    try:
        # Retrieve AWS credentials
        session = boto3.Session()
        credentials = session.get_credentials()
    except NoCredentialsError:
        logging.error("Failed to retrieve AWS credentials. Please ensure AWS CLI is properly configured.")
        exit(1)

    # Optionally, assume a role if impersonate_account is provided
    if impersonate_account:
        sts_client = session.client('sts')
        assumed_role = sts_client.assume_role(
            RoleArn=impersonate_account,
            RoleSessionName='AssumedRoleSession',
            DurationSeconds=3600,  # Adjust as needed
        )
        credentials = assumed_role['Credentials']

    return credentials


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
