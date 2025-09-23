import logging

# setup global logger
logger = logging.getLogger("cloud_instance")


from ..util.build import build
from ..util.fetch import fetch


def slated(
    deployment_id: str,
    deployment: list,
) -> list[dict]:

    logger.info(f"Fetching all instances with {deployment_id=}")

    try:
        current_instances = fetch(deployment_id)
    except:
        raise ValueError(f"Failed to fetch instances for {deployment_id=}")

    logger.info(f"current_instances count={len(current_instances)}")
    for idx, x in enumerate(current_instances, start=1):
        logger.info(f"{idx}:\t{x}")

    logger.info("Building deployment...")
    current_vms, surplus_vms, new_vms = build(
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

    logger.info("Returning instances slated for deletion.")
    return surplus_vms
