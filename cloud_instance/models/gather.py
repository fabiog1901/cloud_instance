import logging

# setup global logger
logger = logging.getLogger("cloud_instance")

from ..util.fetch import fetch_all


def gather(
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
