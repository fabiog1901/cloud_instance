import logging
import os
from threading import Lock, Thread

from ..models import CloudInstance, Group, InstanceDefaults, ProvisionTask, ProvisionTasks
from ..providers.aws import provision_vm as provision_aws
from ..providers.azure import provision_vm as provision_azure
from ..providers.gcp import provision_vm as provision_gcp

logger = logging.getLogger("cloud_instance")

instances: list[CloudInstance] = []
errors: list[str] = []
defaults = InstanceDefaults()


def update_new_deployment(new_instances: list[CloudInstance]):
    global instances
    with Lock():
        logger.debug("Updating pre-existing instances list")
        instances.extend(new_instances)


def update_errors(error: str):
    global errors
    logger.error(error)
    with Lock():
        errors.append(error)


def get_instance_type(group: Group):
    if group.instance_type:
        return group.instance_type

    cpu = group.instance.cpu if group.instance else None
    if cpu is None:
        update_errors("instance cpu cannot be null")
        return

    mem = group.instance.mem if group.instance else None
    global defaults

    return defaults.instance_type(group.cloud, cpu, mem)


def provision(
    new_vms: ProvisionTasks, instance_defaults: InstanceDefaults
) -> list[CloudInstance]:
    global defaults
    global instances
    global errors
    defaults = instance_defaults
    instances = []
    errors = []

    threads = []
    for task in new_vms:
        thread = Thread(
            target={
                "aws": provision_aws_vm,
                "gcp": provision_gcp_vm,
                "azure": provision_azure_vm,
            }.get(task.group.cloud),
            args=(task,),
        )
        thread.start()
        threads.append(thread)

    for x in threads:
        x.join()

    if errors:
        raise ValueError("Failed to provision instances.")

    return instances


def provision_aws_vm(task: ProvisionTask):
    provision_aws(
        task.deployment_id,
        task.cluster_name,
        task.group,
        task.index,
        get_instance_type,
        update_new_deployment,
        update_errors,
    )


def provision_gcp_vm(task: ProvisionTask):
    provision_gcp(
        task.deployment_id,
        task.cluster_name,
        task.group,
        task.index,
        get_instance_type,
        update_new_deployment,
        update_errors,
    )


def provision_azure_vm(task: ProvisionTask):
    provision_azure(
        task.deployment_id,
        task.cluster_name,
        task.group,
        task.index,
        get_instance_type,
        update_new_deployment,
        update_errors,
        os.getenv("AZURE_SUBSCRIPTION_ID"),
        os.getenv("AZURE_RESOURCE_GROUP"),
    )
