import logging

from ..util.fetch import fetch
from ..util.terminate import terminate

logger = logging.getLogger("cloud_instance")

errors: list[str] = []


def delete(deployment_id: str) -> None:

    try:
        current_instances = fetch(deployment_id)
    except:
        raise ValueError(f"Failed to fetch instances for {deployment_id=}")

    logger.info(f"current_instances count={len(current_instances)}")
    for idx, x in enumerate(current_instances, start=1):
        logger.info(f"{idx}:\t{x}")

    logger.info("Deleting all instances")

    try:
        terminate(current_instances)
    except Exception as e:
        raise ValueError(f"Failed at terminating instances.")
