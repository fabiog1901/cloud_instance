import logging

# setup global logger
logger = logging.getLogger("cloud_instance")


from .build import build_deployment
from .destroy import destroy_all
from .fetch import fetch_all
from .modify import modify
from .provision import provision


def gather_current_deployment(
    deployment_id: str,
) -> list[dict]:

    logger.info(f"Fetching all instances with deployment_id = '{deployment_id}'")
    current_instances, errors = fetch_all(deployment_id)

    logger.info(f"current_instances count={len(current_instances)}")
    for idx, x in enumerate(current_instances, start=1):
        logger.info(f"{idx}:\t{x}")

    if errors:
        raise ValueError(errors)

    return current_instances


def create(
    deployment_id: str,
    deployment: list,
    defaults: dict,
    preserve: bool,
) -> list[dict]:

    # fetch all running instances for the deployment_id and append them to the 'instances' list
    logger.info(f"Fetching all instances with deployment_id = '{deployment_id}'")
    current_instances, errors = fetch_all(deployment_id)

    logger.info(f"current_instances count={len(current_instances)}")
    for idx, x in enumerate(current_instances, start=1):
        logger.info(f"{idx}:\t{x}")

    if errors:
        raise ValueError(errors)

    logger.info("Building deployment...")
    current_vms, surplus_vms, new_vms = build_deployment(
        deployment_id,
        deployment,
        current_instances,
    )

    logger.info(f"current_vms count={len(current_vms)}")
    for idx, x in enumerate(current_vms, start=1):
        logger.info(f"{idx}:\t{x}")

    logger.info(f"surplus_vms count={len(surplus_vms)}")
    for idx, x in enumerate(surplus_vms, start=1):
        logger.info(f"{idx}:\t{x}")

    logger.info(f"new_vms count={len(new_vms)}")
    for idx, x in enumerate(new_vms, start=1):
        logger.info(f"{idx}:\t{x}")

    logger.info("Provisioning new_vms...")
    new_instances, errors = provision(new_vms, defaults)

    if not preserve:
        logger.info("Destroying surplus_vms...")
        destroy_all(surplus_vms)

    logger.info(f"new deployment count={len(new_instances + current_vms)}")
    for idx, x in enumerate(new_instances + current_vms, start=1):
        logger.info(f"{idx}:\t{x}")

    if errors:
        raise ValueError(errors)

    logger.info("Returning new deployment list to client")
    return new_instances + current_vms


def return_to_be_deleted_vms(
    deployment_id: str,
    deployment: list,
) -> list[dict]:

    # fetch all running instances for the deployment_id and append them to the 'instances' list
    logger.info(f"Fetching all instances with deployment_id = '{deployment_id}'")
    current_instances, errors = fetch_all(deployment_id)

    logger.info(f"current_instances count={len(current_instances)}")
    for idx, x in enumerate(current_instances, start=1):
        logger.info(f"{idx}:\t{x}")

    if errors:
        raise ValueError(errors)

    logger.info("Building deployment...")
    current_vms, surplus_vms, new_vms = build_deployment(
        deployment_id,
        deployment,
        current_instances,
    )

    logger.info(f"current_vms count={len(current_vms)}")
    for idx, x in enumerate(current_vms, start=1):
        logger.info(f"{idx}:\t{x}")

    logger.info(f"surplus_vms count={len(surplus_vms)}")
    for idx, x in enumerate(surplus_vms, start=1):
        logger.info(f"{idx}:\t{x}")

    logger.info(f"new_vms count={len(new_vms)}")
    for idx, x in enumerate(new_vms, start=1):
        logger.info(f"{idx}:\t{x}")

    logger.info("Returning to be deleted VMs")
    return surplus_vms


def destroy(
    deployment_id: str,
) -> None:

    # fetch all running instances for the deployment_id and append them to the 'instances' list
    logger.info(f"Fetching all instances with deployment_id = '{deployment_id}'")
    current_instances, errors = fetch_all(deployment_id)

    logger.info(f"current_instances count={len(current_instances)}")
    for idx, x in enumerate(current_instances, start=1):
        logger.info(f"{idx}:\t{x}")

    if errors:
        raise ValueError(errors)

    logger.info("Destroying all instances")
    destroy_all(current_instances)


def modify_instance_type(
    deployment_id: str,
    new_cpus_count: int,
    filter_by_groups: list[str] = [],
    sequential: bool = True,
    pause_between: int = 30,
    defaults: dict = {},
) -> None:

    # fetch all running instances for the deployment_id and append them to the 'instances' list
    logger.info(f"Fetching all instances with deployment_id = '{deployment_id}'")
    current_instances, errors = fetch_all(deployment_id)

    logger.info(f"current_instances count={len(current_instances)}")
    for idx, x in enumerate(current_instances, start=1):
        logger.info(f"{idx}:\t{x}")

    if errors:
        raise ValueError(errors)

    filtered_instances = []

    for idx, x in enumerate(current_instances, start=1):
        inv_grps = set(x.get("inventory_groups", []))
        if (
            len(filter_by_groups) == 0
            or inv_grps
            and set(filter_by_groups).issubset(inv_grps)
        ):
            filtered_instances.append(x)

    modify(
        filtered_instances,
        new_cpus_count,
        sequential,
        pause_between,
        defaults,
    )
