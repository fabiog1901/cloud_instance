import logging
import os
from threading import Lock, Thread

# AWS
import boto3

# AZURE
from azure.identity import EnvironmentCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.network import NetworkManagementClient

# GCP
from google.cloud.compute_v1 import AggregatedListInstancesRequest, InstancesClient

from .parse import parse_aws_query, parse_azure_query, parse_gcp_query

logger = logging.getLogger("cloud_instance")

instances: list[dict] = []
errors: list[str] = []


def fetch(deployment_id: str):
    threads: list[Thread] = []
    global instances
    global errors

    # AWS
    thread = Thread(target=fetch_aws_instances, args=(deployment_id,))
    thread.start()
    threads.append(thread)

    # GCP
    thread = Thread(
        target=fetch_gcp_instances,
        args=(deployment_id,),
    )
    thread.start()
    threads.append(thread)

    # AZURE
    # if azure_resource_group:
    #     thread = Thread(
    #         target=fetch_azure_instances, args=(deployment_id,)
    #     )
    #     thread.start()
    #     threads.append(thread)

    # wait for all threads to complete
    for x in threads:
        x.join()

    # sort instances to ensure list is deterministic
    instances = sorted(instances, key=lambda d: d["id"])

    if errors:
        raise ValueError(f"Failed to fetch resources for {deployment_id=}")

    return instances


def update_instances_list(_instances: list):
    global instances
    with Lock():
        logger.debug("Updating instances list")
        instances += _instances


def update_errors(error: str):
    global errors
    logger.error(error)
    with Lock():
        errors.append(error)


def fetch_aws_instances(deployment_id: str):
    logger.debug(f"Fetching AWS instances for deployment_id = '{deployment_id}'")

    threads: list[Thread] = []

    def fetch_aws_instances_per_region(region, deployment_id):
        logger.debug(f"Fetching AWS instances from {region}")

        try:
            ec2 = boto3.client("ec2", region_name=region)
            response = ec2.describe_instances(
                Filters=[
                    {
                        "Name": "instance-state-name",
                        "Values": ["pending", "running"],
                    },
                    {"Name": "tag:deployment_id", "Values": [deployment_id]},
                ]
            )

            aws_instances: list = parse_aws_query(response)

        except Exception as e:
            update_errors(e)

        if aws_instances:
            update_instances_list(aws_instances)

    try:
        ec2 = boto3.client("ec2", region_name="us-east-1")
        regions = [x["RegionName"] for x in ec2.describe_regions()["Regions"]]

        for region in regions:
            thread = Thread(
                target=fetch_aws_instances_per_region,
                args=(region, deployment_id),
                daemon=True,
            )
            thread.start()
            threads.append(thread)

        for x in threads:
            x.join()

    except Exception as e:
        update_errors(e)


def fetch_gcp_instances(deployment_id: str):
    logger.debug(f"Fetching GCP instances for deployment_id = '{deployment_id}'")

    gcp_project = os.getenv("GCP_PROJECT")
    if not gcp_project:
        update_errors("Env var GCP_PROJECT is not set")
        return

    try:
        instance_client = InstancesClient()
        # Use the `max_results` parameter to limit the number of results that the API returns per response page.
        request = AggregatedListInstancesRequest(
            project=gcp_project,
            max_results=5,
            filter=f"labels.deployment_id:{deployment_id}",
        )

        agg_list = instance_client.aggregated_list(request=request)
        instances = []

        # Despite using the `max_results` parameter, you don't need to handle the pagination
        # your The returned `AggregatedListPager` object handles pagination
        # automatically, returning separated pages as you iterate over the results.
        for zone, response in agg_list:
            if response.instances:
                for x in response.instances:
                    if x.status in ("PROVISIONING", "STAGING", "RUNNING"):
                        instances.append(parse_gcp_query(x, zone[6:-2], zone[-1]))

        if instances:
            update_instances_list(instances)

    except Exception as e:
        update_errors(e)


"""
def fetch_azure_instance_network_config(self, vm):
    try:
        credential = EnvironmentCredential()

        client = ComputeManagementClient(credential, azure_subscription_id)
        netclient = NetworkManagementClient(credential, azure_subscription_id)

        # check VM is in running state
        statuses = client.virtual_machines.instance_view(
            azure_resource_group, vm.name
        ).statuses

        status = len(statuses) >= 2 and statuses[1]

        if status and status.code == "PowerState/running":
            nic_id = vm.network_profile.network_interfaces[0].id
            nic = netclient.network_interfaces.get(
                azure_resource_group, nic_id.split("/")[-1]
            )

            private_ip = nic.ip_configurations[0].private_ip_address
            pip = netclient.public_ip_addresses.get(
                azure_resource_group,
                nic.ip_configurations[0].public_ip_address.id.split("/")[-1],
            )

            public_ip = pip.ip_address
            public_hostname = ""

        return private_ip, public_ip, public_hostname

    except Exception as e:
        logger.error(e)
        log_error(e)

def get_azure_instance_details(self, vm):
    update_current_deployment(
        parse_azure_query(vm, *fetch_azure_instance_network_config(vm))
    )

def fetch_azure_instances(self, deployment_id: str):
    logger.debug(f"Fetching Azure instances for deployment_id = '{deployment_id}'")

    threads: list[Thread] = []

    try:
        # Acquire a credential object.
        credential = EnvironmentCredential()

    except Exception as e:
        logger.warning(e)
        return

    client = ComputeManagementClient(credential, azure_subscription_id)

    vm_list = client.virtual_machines.list(azure_resource_group)
    for vm in vm_list:
        if vm.tags.get("deployment_id", "") == deployment_id:
            thread = Thread(
                target=get_azure_instance_details, args=(vm,), daemon=True
            )
            thread.start()
            threads.append(thread)

    for x in threads:
        x.join()

"""
