# Copyright © 2023 Apple Inc.

"""Utilities to create, delete, and list VMs."""

import dataclasses
import pathlib
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from absl import logging
import boto3
import botocore
from axlearn.cloud.common.docker import registry_from_repo
from axlearn.cloud.common.utils import format_table
from axlearn.cloud.gcp.config import gcp_settings
from axlearn.cloud.gcp.utils import infer_cli_name, is_valid_resource_name


class VMCreationError(RuntimeError):
    """An error with VM creation."""

    pass


class VMDeletionError(RuntimeError):
    """An error with VM deletion."""

    pass


# pylint: disable-next=too-many-branches
def create_vm(
    name: str,
    *,
    region: str,
    ami_id: str,
    instance_type: str,
    key_pair_name: str,
    bundler_type: str,
    metadata: Optional[Dict[str, str]] = None,
) -> Any:
    """Create VM.

    Args:
        name: Name of VM.
        vm_type: What gcloud machine type to boot.
        disk_size: Size of disk to provision (in GB).
        credentials: Credentials to use when interacting with GCP.
        bundler_type: Type of bundle intended to be loaded to VM.
        metadata: Optional metadata for the instance.

    Raises:
        VMCreationError: If an exeption is raised on the creation request.
        ValueError: If an invalid name is provided.
    """
    if not is_valid_resource_name(name):
        raise ValueError(f"{name} is not a valid resource name.")
    attempt = 0
    while True:
        node = get_vm_node(name)
        if node is None:  # VM doesn't exist.
            if attempt:
                # Exponential backoff capped at 512s.
                backoff_for = 2 ** min(attempt, 9)
                logging.info(
                    "Attempt %d to create VM failed, backoff for %ds. ",
                    attempt,
                    backoff_for,
                    aws_settings("project"),
                )
                time.sleep(backoff_for)
            try:
                ec2_resource = boto3.resource("ec2", region_name=region)
                instance = ec2_resource.create_instances(
                    ImageId=ami_id,
                    InstanceType=instance_type,
                    KeyName=key_pair_name,
                    MinCount=1,
                    MaxCount=1,
                )[0]
                instance.wait_until_running()

                # set instance name:
                response = ec2_resource.create_tags(
                    Resources=[instance.id],
                    Tags=[
                        {"Key": "Name", "Value": f"{name}"},
                    ],
                )

                attempt += 1
            except botocore.exceptions.ClientError as err:
                logging.error(
                    "Couldn't create instance with image %s, instance type %s, and key %s. "
                    "Here's why: %s: %s",
                    ami_id,
                    instance_type,
                    key_pair_name,
                    err.response["Error"]["Code"],
                    err.response["Error"]["Message"],
                )
                raise err
                # raise VMCreationError("Couldn't create VM") from e
            else:
                return instance

        else:  # VM exists.
            status = get_vm_node_status(node)
            if status == "BOOTED":
                logging.info("VM %s is running and booted.", name)
                logging.info("SSH to VM with: %s gcp sshvm %s", infer_cli_name(), name)
                return
            elif status == "RUNNING":
                logging.info(
                    "VM %s RUNNING, waiting for boot to complete "
                    "(which usually takes a few minutes)",
                    name,
                )
            else:
                logging.info("VM %s showing %s, waiting for RUNNING.", name, status)
            time.sleep(10)


def get_vm_node_status(node: Dict[str, Any]) -> str:
    """Get the status from the given VM node info.

    Args:
        node: Node as returned by `get_vm_node`.

    Returns:
        The node status. For valid statuses see:
        https://cloud.google.com/compute/docs/instances/instance-life-cycle

        On top of regular VM statuses, this also returns:
        * BOOTED: VM is RUNNING + finished booting.
        * UNKNOWN: VM is missing a status.
    """
    status = node.get("status", "UNKNOWN")
    if status == "RUNNING" and "labels" in node:
        # Check boot status.
        if node["labels"].get("boot_status", None) == "done":
            return "BOOTED"
    return status


def delete_vm(name: str):
    """Delete VM.

    Args:
        name: Name of VM to delete.
        credentials: Credentials to use when interacting with GCP.

    Raises:
        VMDeletionError: If an exeption is raised on the deletion request.
    """
    print("delete")
    exit()
    node = get_vm_node(name)
    if node is None:  # VM doesn't exist.
        logging.info("VM %s doesn't exist.", name)
        return
    try:
        response = (
            resource.instances()
            .delete(project=gcp_settings("project"), zone=gcp_settings("zone"), instance=name)
            .execute()
        )
        while True:
            logging.info("Waiting for deletion of VM %s to complete.", name)
            zone_op = (
                resource.zoneOperations()
                .get(
                    project=gcp_settings("project"),
                    zone=gcp_settings("zone"),
                    operation=response["name"],
                )
                .execute()
            )
            if zone_op.get("status") == "DONE":
                if "error" in zone_op:
                    raise VMDeletionError(zone_op["error"])
                logging.info("Deletion of VM %s is complete.", name)
                return
            time.sleep(10)
    except (errors.HttpError, Exception) as e:
        raise VMDeletionError("Failed to delete VM") from e


@dataclass
class VmInfo:
    """Information associated with a VM instance."""

    name: str
    metadata: Dict[str, Any]


def get_vm_node(name: str) -> Optional[Dict[str, Any]]:
    """Gets information about a VM node.

    Args:
        name: Name of EC2 VM.

    Returns:
        The VM with the given name, or None if it doesn't exist.
    """

    ec2 = boto3.client("ec2")
    filters = [{"Name": "tag:name", "Values": [name]}]
    nodes = ec2.describe_instances(Filters=filters)["Reservations"]
    return None if not nodes else nodes.pop()
