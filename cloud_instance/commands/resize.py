import logging
import time
from threading import Lock, Thread

from ..providers.aws import resize_vm as resize_aws_vm
from ..providers.azure import resize_vm as resize_azure_vm
from ..providers.gcp import resize_vm as resize_gcp_vm
from ..util.fetch import fetch

logger = logging.getLogger("cloud_instance")

errors: list[str] = []


def update_errors(error: str):
    global errors
    logger.error(error)
    with Lock():
        errors.append(error)


def resize(
    deployment_id: str,
    new_disk_size: int,
    filter_by_groups: list[str] = [],
    sequential: bool = True,
    pause_between: int = 30,
) -> None:
    logger.info(f"Fetching all instances with {deployment_id=}")

    try:
        current_instances = fetch(deployment_id)
    except:
        raise ValueError(f"Failed to fetch instances for {deployment_id=}")

    logger.info(f"current_instances count={len(current_instances)}")
    for idx, x in enumerate(current_instances, start=1):
        logger.info(f"{idx}:\t{x}")

    filtered_instances = []

    for idx, x in enumerate(current_instances, start=1):
        inv_grps = set(x.get("inventory_groups", []))
        if (
            len(filter_by_groups) == 0
            or inv_grps
            and set(filter_by_groups).issubset(inv_grps)
        ):
            filtered_instances.append(x)

    if sequential:
        for x in filtered_instances:
            resize_vm(x, new_disk_size)
            logger.info(f"Pausing for {pause_between} seconds...")
            time.sleep(pause_between)
    else:
        threads = []
        for x in filtered_instances:
            t = Thread(
                target=resize_vm,
                args=(x, new_disk_size),
            )
            t.start()
            threads.append(t)

        for x in threads:
            x.join()

    global errors

    if errors:
        raise ValueError(f"Failed to resize instances for {deployment_id=}")


def resize_vm(instance: dict, new_disk_size: int):
    {
        "aws": resize_aws_vm,
        "gcp": resize_gcp_vm,
        "azure": resize_azure_vm,
    }.get(instance["cloud"])(instance, new_disk_size, update_errors)
