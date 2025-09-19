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

from ..util.fetch import fetch_all

logger = logging.getLogger("cloud_instance")

errors: list[str] = []


def delete(deployment_id: str):

    # fetch all running instances for the deployment_id and append them to the 'instances' list
    logger.info(f"Fetching all instances with deployment_id = '{deployment_id}'")
    current_instances, _errors = fetch_all(deployment_id)

    logger.info(f"current_instances count={len(current_instances)}")
    for idx, x in enumerate(current_instances, start=1):
        logger.info(f"{idx}:\t{x}")

    if _errors:
        raise ValueError(_errors)

    logger.info("Destroying all instances")

    threads: list[Thread] = []

    for x in current_instances:
        thread = Thread(
            target={
                "aws": delete_aws_vm,
                "gcp": delete_gcp_vm,
                "azure": delete_azure_vm,
            }.get(x["cloud"]),
            args=(x,),
        )
        thread.start()
        threads.append(thread)
        logger.info(f"Destroying instance: {x}")

    for x in threads:
        x.join()

    global errors
    return errors


def update_errors(error: str):
    global errors
    with Lock():
        errors.append(error)


def delete_aws_vm(instance: dict):

    def get_allocation_id(public_ip, instance_id):
        response = ec2.describe_addresses(PublicIps=[public_ip])

        for address in response["Addresses"]:
            # Check if the EIP is associated with the given instance ID
            if address.get("InstanceId") == instance_id:
                public_ip = address.get("PublicIp")
                allocation_id = address.get("AllocationId")
                print(
                    f"Instance {instance_id} has EIP {public_ip} with Allocation ID {allocation_id}"
                )
                return allocation_id

        update_errors(f"No Elastic IP found associated with instance {instance_id}")

    logger.debug(f"--aws {instance['id']}")

    try:
        ec2 = boto3.client("ec2", region_name=instance["region"])

        alloc = get_allocation_id(instance["public_ip"], instance["id"])

        response = ec2.terminate_instances(
            InstanceIds=[instance["id"]],
        )

        waiter = ec2.get_waiter("instance_terminated")
        waiter.wait(InstanceIds=[instance["id"]])

        status = response["TerminatingInstances"][0]["CurrentState"]["Name"]

        if status in ["shutting-down", "terminated"]:
            logger.debug(f"Deleted AWS instance: {instance}")
        else:
            logger.error(f"Unexpected response: {response}")
            update_errors(str(response))

        ec2.release_address(AllocationId=alloc)

    except Exception as e:
        logger.error(e)
        update_errors(e)


def delete_gcp_vm(instance: dict):
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
        logger.error(e)
        update_errors(e)


def delete_azure_vm(instance: dict):
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
        logger.error(e)
        update_errors(e)
