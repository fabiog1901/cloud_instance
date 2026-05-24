import logging
from threading import Lock, Thread

from .errors import operation_error
from ..models import CloudInstance, Group, InstanceDefaults, ProvisionTask
from ..providers import aws, gcp

logger = logging.getLogger("cloud_instance")

instances: list[CloudInstance] = []
errors: list[object] = []
state_lock = Lock()
defaults = InstanceDefaults()


def update_new_deployment(new_instances: list[CloudInstance]):
    global instances
    with state_lock:
        logger.debug("Updating pre-existing instances list")
        instances.extend(new_instances)


def update_errors(error: object):
    global errors
    logger.error(error)
    with state_lock:
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
    new_vms: list[ProvisionTask], instance_defaults: InstanceDefaults
) -> list[CloudInstance]:
    global defaults
    global instances
    global errors
    defaults = instance_defaults
    instances = []
    errors = []

    threads = []
    for task in new_vms:
        target = {
            "aws": aws.provision_vm,
            "gcp": gcp.provision_vm,
        }.get(task.group.cloud)
        if target is None:
            update_errors(f"Unsupported cloud provider: {task.group.cloud}")
            continue

        thread = Thread(
            target=target,
            args=(
                task.deployment_id,
                task.cluster_name,
                task.group,
                task.index,
                get_instance_type,
                update_new_deployment,
                update_errors,
            ),
        )
        thread.start()
        threads.append(thread)

    for x in threads:
        x.join()

    if errors:
        raise operation_error("Provision instances", errors)

    return instances
