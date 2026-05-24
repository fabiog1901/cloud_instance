import logging
import time
from threading import Lock, Thread

from ..providers.aws import modify_vm as modify_aws_vm
from ..providers.azure import modify_vm as modify_azure_vm
from ..providers.gcp import modify_vm as modify_gcp_vm
from ..util.fetch import fetch

logger = logging.getLogger("cloud_instance")

errors: list[str] = []
defaults: dict = {}


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


def modify(
    deployment_id: str,
    new_cpus_count: int,
    filter_by_groups: list[str] = [],
    sequential: bool = True,
    pause_between: int = 30,
    instance_defaults: dict = {},
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

    global defaults
    defaults = instance_defaults

    if sequential:
        for x in filtered_instances:
            modify_vm(x, new_cpus_count)
            logger.info(f"Pausing for {pause_between} seconds...")
            time.sleep(pause_between)
    else:
        threads = []
        for x in filtered_instances:
            t = Thread(
                target=modify_vm,
                args=(x, new_cpus_count),
            )
            t.start()
            threads.append(t)

        for x in threads:
            x.join()

    global errors

    if errors:
        raise ValueError(f"Failed to modify instances for {deployment_id=}")


def modify_vm(instance: dict, new_cpus_count: int):
    {
        "aws": modify_aws_vm,
        "gcp": modify_gcp_vm,
        "azure": modify_azure_vm,
    }.get(instance["cloud"])(instance, new_cpus_count, get_instance_type, update_errors)
