import logging
from threading import Lock, Thread

from ..models import IPAddressType
from ..providers.aws import provision_vm as provision_aws
from ..providers.azure import provision_vm as provision_azure
from ..providers.gcp import provision_vm as provision_gcp

logger = logging.getLogger("cloud_instance")

instances: list[dict] = []
errors: list[str] = []
defaults: dict = {}


def update_new_deployment(_instances: list):
    global instances
    with Lock():
        logger.debug("Updating pre-existing instances list")
        instances += _instances


def update_errors(error: str):
    global errors
    logger.error(error)
    with Lock():
        errors.append(error)


def get_instance_type(group: dict):
    if "instance_type" in group:
        return group["instance_type"]

    cpu = str(group["instance"].get("cpu"))
    if cpu == "None":
        update_errors("instance cpu cannot be null")
        return

    mem = str(group["instance"].get("mem", "default"))
    cloud = group["cloud"]
    global defaults

    return defaults[cloud][cpu][mem]


def provision(new_vms: list[Thread], instance_defaults) -> list[dict]:
    global defaults
    defaults = instance_defaults

    for x in new_vms:
        x.start()

    for x in new_vms:
        x.join()

    global instances
    global errors

    if errors:
        raise ValueError("Failed to provision instances.")

    return instances


def provision_aws_vm(
    deployment_id: str,
    cluster_name: str,
    group: dict,
    x: int,
):
    provision_aws(
        deployment_id,
        cluster_name,
        group,
        x,
        get_instance_type,
        update_new_deployment,
        update_errors,
    )


def provision_gcp_vm(
    deployment_id: str,
    cluster_name: str,
    group: dict,
    x: int,
    ip_address_type: IPAddressType = IPAddressType.IPv4_EPHEMERAL,
):
    provision_gcp(
        deployment_id,
        cluster_name,
        group,
        x,
        get_instance_type,
        update_new_deployment,
        update_errors,
        ip_address_type,
    )


def provision_azure_vm(
    deployment_id: str,
    cluster_name: str,
    group: dict,
    x: int,
    azure_subscription_id,
    azure_resource_group,
):
    provision_azure(
        deployment_id,
        cluster_name,
        group,
        x,
        get_instance_type,
        update_new_deployment,
        update_errors,
        azure_subscription_id,
        azure_resource_group,
    )
