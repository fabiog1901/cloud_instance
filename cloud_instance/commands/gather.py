import logging

# setup global logger
logger = logging.getLogger("cloud_instance")

from ..core.fetch import fetch
from ..models import CloudInstance


def gather(
    deployment_id: str,
) -> list[CloudInstance]:

    logger.info(f"Fetching all instances with {deployment_id=}")

    try:
        current_instances = fetch(deployment_id)
    except Exception as e:
        raise ValueError(f"Failed to fetch instances for {deployment_id=}:\n{e}") from e

    logger.info(f"current_instances count={len(current_instances)}")
    for idx, x in enumerate(current_instances, start=1):
        logger.info(f"{idx}:\t{x}")

    return current_instances
