import logging
import time
from threading import Lock, Thread

from ..core.errors import operation_error
from ..core.fetch import fetch
from ..models import CloudInstance, GroupFilter
from ..providers.aws import resize_vm as resize_aws_vm
from ..providers.azure import resize_vm as resize_azure_vm
from ..providers.gcp import resize_vm as resize_gcp_vm
from ..providers.kloigos import resize_vm as resize_kloigos_vm

logger = logging.getLogger("cloud_instance")

errors: list[object] = []
state_lock = Lock()


def update_errors(error: object):
    global errors
    logger.error(error)
    with state_lock:
        errors.append(error)


def resize(
    deployment_id: str,
    new_disk_size: int,
    filter_by_groups: GroupFilter = GroupFilter(),
    sequential: bool = True,
    pause_between: int = 30,
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

    global errors
    errors = []

    if sequential:
        for x in filtered_instances:
            resize_instance(x, new_disk_size)
            logger.info(f"Pausing for {pause_between} seconds...")
            time.sleep(pause_between)
    else:
        threads = []
        for x in filtered_instances:
            t = Thread(
                target=resize_instance,
                args=(x, new_disk_size),
            )
            t.start()
            threads.append(t)

        for x in threads:
            x.join()

    if errors:
        raise operation_error(f"Resize instances for {deployment_id=}", errors)


def resize_instance(instance: CloudInstance, new_disk_size: int):
    target = {
        "aws": resize_aws_vm,
        "gcp": resize_gcp_vm,
        "azure": resize_azure_vm,
        "kloigos": resize_kloigos_vm,
    }.get(instance.cloud)
    if target is None:
        update_errors(f"Unsupported cloud provider: {instance.cloud}")
        return

    target(instance, new_disk_size, update_errors)
