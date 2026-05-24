import logging
import time
from threading import Lock, Thread

from ..core.errors import operation_error
from ..core.fetch import fetch
from ..models import CloudInstance, Group, GroupFilter, InstanceDefaults
from ..providers.aws import modify_vm as modify_aws_vm
from ..providers.azure import modify_vm as modify_azure_vm
from ..providers.gcp import modify_vm as modify_gcp_vm

logger = logging.getLogger("cloud_instance")

errors: list[object] = []
state_lock = Lock()
defaults = InstanceDefaults()


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


def modify(
    deployment_id: str,
    new_cpus_count: int,
    filter_by_groups: GroupFilter = GroupFilter(),
    sequential: bool = True,
    pause_between: int = 30,
    instance_defaults: InstanceDefaults = InstanceDefaults(),
) -> None:
    logger.info(f"Fetching all instances with {deployment_id=}")

    try:
        current_instances = fetch(deployment_id)
    except Exception as e:
        raise ValueError(f"Failed to fetch instances for {deployment_id=}:\n{e}") from e

    logger.info(f"current_instances count={len(current_instances)}")
    for idx, x in enumerate(current_instances, start=1):
        logger.info(f"{idx}:\t{x}")

    filtered_instances = [x for x in current_instances if filter_by_groups.matches(x)]

    global defaults
    global errors
    defaults = instance_defaults
    errors = []

    if sequential:
        for x in filtered_instances:
            modify_instance(x, new_cpus_count)
            logger.info(f"Pausing for {pause_between} seconds...")
            time.sleep(pause_between)
    else:
        threads = []
        for x in filtered_instances:
            t = Thread(
                target=modify_instance,
                args=(x, new_cpus_count),
            )
            t.start()
            threads.append(t)

        for x in threads:
            x.join()

    if errors:
        raise operation_error(f"Modify instances for {deployment_id=}", errors)


def modify_instance(instance: CloudInstance, new_cpus_count: int):
    target = {
        "aws": modify_aws_vm,
        "gcp": modify_gcp_vm,
        "azure": modify_azure_vm,
    }.get(instance.cloud)
    if target is None:
        update_errors(f"Unsupported cloud provider: {instance.cloud}")
        return

    target(instance, new_cpus_count, get_instance_type, update_errors)
