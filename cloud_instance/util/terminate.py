import ipaddress
import logging
import os
from threading import Lock, Thread

# AWS
import boto3

# AZURE
from azure.identity import EnvironmentCredential
from azure.mgmt.compute import ComputeManagementClient

# GCP
from google.cloud.compute_v1 import InstancesClient
from google.cloud.compute_v1.services.addresses.client import AddressesClient

from ..models import IPAddressType
from .fetch import fetch

logger = logging.getLogger("cloud_instance")

errors: list[str] = []


def terminate(instances: list[dict]) -> None:

    threads: list[Thread] = []

    for x in instances:
        thread = Thread(
            target={
                "aws": terminate_aws_vm,
                "gcp": terminate_gcp_vm,
                "azure": terminate_azure_vm,
            }.get(x["cloud"]),
            args=(x,),
        )
        thread.start()
        threads.append(thread)
        logger.info(f"Deleting instance: {x}")

    for x in threads:
        x.join()

    global errors

    if errors:
        raise ValueError(f"Failed to terminate instances.")


def update_errors(error: str):
    global errors
    logger.error(error)
    with Lock():
        errors.append(error)


def terminate_aws_vm(instance: dict):
    def get_allocation_id(instance_id):
        response = ec2.describe_addresses(
            Filters=[
                {"Name": "instance-id", "Values": [instance_id]},
                {
                    "Name": "tag:ip_address_type",
                    "Values": [IPAddressType.IPv4_RESERVED.value],
                },
            ]
        )

        for address in response["Addresses"]:
            if address.get("InstanceId") == instance_id:
                return address.get("AllocationId")

        return None

    def get_allocation_id_by_public_ip(public_ip, instance_id):
        try:
            response = ec2.describe_addresses(PublicIps=[public_ip])
        except Exception as e:
            logger.warning(e)
            return None

        for address in response["Addresses"]:
            if address.get("InstanceId") == instance_id:
                return address.get("AllocationId")

        return None

    def is_ipv4_address(address):
        try:
            return ipaddress.ip_address(address).version == 4
        except (TypeError, ValueError):
            return False

    logger.info(f"--aws {instance['id']}")

    try:
        ec2 = boto3.client("ec2", region_name=instance["region"])

        alloc = None
        if instance.get("ip_address_type") == IPAddressType.IPv4_RESERVED.value:
            alloc = get_allocation_id(instance["id"])
        elif is_ipv4_address(instance.get("public_ip")):
            alloc = get_allocation_id_by_public_ip(instance["public_ip"], instance["id"])

        response = ec2.terminate_instances(
            InstanceIds=[instance["id"]],
        )

        waiter = ec2.get_waiter("instance_terminated")
        waiter.wait(InstanceIds=[instance["id"]])

        status = response["TerminatingInstances"][0]["CurrentState"]["Name"]

        if status in ["shutting-down", "terminated"]:
            logger.info(f"Deleted AWS instance: {instance['id']}")
        else:
            logger.error(f"Unexpected response: {response}")
            update_errors(str(response))

        if alloc:
            ec2.release_address(AllocationId=alloc)

    except Exception as e:
        update_errors(str(e))


def terminate_gcp_vm(instance: dict):
    logger.debug(f"--gcp {instance['id']}")

    gcp_project = os.getenv("GCP_PROJECT")
    if not gcp_project:
        raise ValueError("Env var GCP_PROJECT not set.")

    try:
        instance_client = InstancesClient()

        op = instance_client.delete(
            project=gcp_project,
            zone=f"{instance['region']}-{instance['zone']}",
            instance=instance["id"],
        )
        # wait_for_extended_operation(op)
        logger.info(f"Deleting GCP instance: {instance}")

        client = AddressesClient()
        op = client.delete(
            project=gcp_project,
            region=instance["region"],
            address=f"{instance['id']}-eip",
        )

        logger.info(f"GCP External IP address {instance['id']} released successfully.")

    except Exception as e:
        update_errors(e)


def terminate_azure_vm(instance: dict):
    logger.debug(f"--azure {instance['id']}")

    azure_subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID")
    azure_resource_group = os.getenv("AZURE_RESOURCE_GROUP")

    # Acquire a credential object using CLI-based authentication.
    try:
        credential = EnvironmentCredential()

        client = ComputeManagementClient(credential, azure_subscription_id)

        async_vm_delete = client.virtual_machines.begin_delete(
            azure_resource_group, instance["id"]
        )
        async_vm_delete.wait()

    except Exception as e:
        update_errors(e)
