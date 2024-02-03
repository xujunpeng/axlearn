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
    volume_size: int,
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
                # create security group first
                ec2_client = boto3.client("ec2", region_name=region)

                security_groups_name = [
                    g["GroupName"] for g in ec2_client.describe_security_groups()["SecurityGroups"]
                ]

                if "axlearn-security-group" in security_groups_name:
                    security_group = ec2_client.describe_security_groups(
                        GroupNames=["axlearn-security-group"]
                    )
                else:
                    security_group = ec2_client.create_security_group(
                        GroupName="axlearn-security-group",
                        Description="The security group for axlearn",
                    )

                    ec2_client.authorize_security_group_ingress(
                        GroupId=security_group["GroupId"],
                        IpPermissions=[
                            {
                                "IpProtocol": "tcp",
                                "FromPort": 80,
                                "ToPort": 80,
                                "IpRanges": [
                                    {"CidrIp": "0.0.0.0/0"}
                                ],  # Allow inbound traffic on port 80 from all IP addresses
                            },
                            {
                                "IpProtocol": "tcp",
                                "FromPort": 22,
                                "ToPort": 22,
                                "IpRanges": [
                                    {"CidrIp": "0.0.0.0/0"}
                                ],  # Allow SSH access on port 22 from all IP addresses
                            },
                        ],
                    )

                # create ec2 instance
                ec2_resource = boto3.resource("ec2", region_name=region)

                instance_params = {
                    "ImageId": f"{ami_id}",
                    "InstanceType": f"{instance_type}",
                    "KeyName": f"{key_pair_name}",
                    "SecurityGroupIds": [security_group["GroupId"]],
                    "MinCount": 1,
                    "MaxCount": 1,
                    "BlockDeviceMappings": [
                        {
                            "DeviceName": "/dev/sda1",
                            "Ebs": {
                                "VolumeSize": volume_size,
                                "VolumeType": "gp3",
                            },
                        }
                    ],
                    "TagSpecifications": [
                        {"ResourceType": "instance", "Tags": [{"Key": "Name", "Value": f"{name}"}]}
                    ],
                }

                instance = ec2_resource.create_instances(**instance_params)[0]
                instance.wait_until_running()
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

        else:  # VM exists.
            status = get_vm_node_status(node)
            if status == "running":
                logging.info(
                    "VM %s is RUNNING",
                    name,
                )
                return
            else:
                logging.info("VM %s showing %s, waiting for RUNNING.", name, status)
            time.sleep(10)


def get_vm_node_status(node: Dict[str, Any]) -> str:
    """Get the status from the given VM node info.

    Args:
        node: Node as returned by `get_vm_node`.

    Returns:
        The node status.
    """
    return node["Instances"][0]["State"]["Name"]


def delete_vm(name: str):
    """Delete VM.

    Args:
        name: Name of VM to delete.

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
    nodes = ec2.describe_instances(Filters=[{"Name": "tag:Name", "Values": [name]}])["Reservations"]
    return None if not nodes else nodes.pop()
