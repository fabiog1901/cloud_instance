import json
import logging
import os

from azure.identity import EnvironmentCredential
from azure.mgmt.compute import ComputeManagementClient

from ..models import CloudInstance, Group

logger = logging.getLogger("cloud_instance")


def fetch_instances(deployment_id: str, update_instances_list, update_errors):
    logger.debug("Azure fetch is not implemented")


def parse_instance(vm, private_ip, public_ip, public_hostname) -> list[CloudInstance]:
    return [
        CloudInstance(
            id=vm.name,
            cloud="azure",
            region=vm.location,
            zone="default",
            public_ip=public_ip,
            public_hostname=public_hostname,
            private_ip=private_ip,
            private_hostname=vm.name + ".internal.cloudapp.net",
            ansible_user=vm.tags["ansible_user"],
            inventory_groups=json.loads(vm.tags["inventory_groups"]),
            cluster_name=vm.tags["cluster_name"],
            group_name=vm.tags["group_name"],
            extra_vars=vm.tags["extra_vars"],
        )
    ]


def provision_vm(
    deployment_id: str,
    cluster_name: str,
    group: Group,
    x: int,
    get_instance_type,
    update_new_deployment,
    update_errors,
):
    logger.debug("++azure %s %s %s" % (cluster_name, group.group_name, x))
    update_errors("Azure provisioning is not implemented")


def terminate_vm(instance: CloudInstance, update_errors):
    logger.debug(f"--azure {instance.id}")

    azure_subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID")
    azure_resource_group = os.getenv("AZURE_RESOURCE_GROUP")

    try:
        credential = EnvironmentCredential()

        client = ComputeManagementClient(credential, azure_subscription_id)

        async_vm_delete = client.virtual_machines.begin_delete(
            azure_resource_group, instance.id
        )
        async_vm_delete.wait()

    except Exception as e:
        update_errors(e)


def modify_vm(
    instance: CloudInstance, new_cpus_count, get_instance_type, update_errors
):
    update_errors("Azure instance type modification is not implemented")


def resize_vm(instance: CloudInstance, new_disk_size, update_errors):
    update_errors("Azure disk resize is not implemented")
