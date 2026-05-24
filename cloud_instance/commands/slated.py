import logging

from ..core.build import build
from ..core.fetch import fetch
from ..models import CloudInstance, Deployment

logger = logging.getLogger("cloud_instance")


def slated(
    deployment_id: str,
    deployment: Deployment,
) -> list[CloudInstance]:
    logger.info(f"Fetching all instances with {deployment_id=}")

    try:
        current_instances = fetch(deployment_id)
    except Exception as e:
        raise ValueError(f"Failed to fetch instances for {deployment_id=}:\n{e}") from e

    logger.info(f"current_instances count={len(current_instances)}")
    for idx, x in enumerate(current_instances, start=1):
        logger.info(f"{idx}:\t{x}")

    logger.info("Building deployment...")
    build_result = build(
        deployment_id,
        deployment,
        current_instances,
    )

    logger.info(f"current_vms count={len(build_result.current_vms)}")
    for idx, x in enumerate(build_result.current_vms, start=1):
        logger.info(f"{idx}:\t{x}")

    logger.info(f"surplus_vms count={len(build_result.surplus_vms)}")
    for idx, x in enumerate(build_result.surplus_vms, start=1):
        logger.info(f"{idx}:\t{x}")

    logger.info(f"new_vms count={len(build_result.new_vms)}")
    for idx, x in enumerate(build_result.new_vms, start=1):
        logger.info(f"{idx}:\t{x}")

    logger.info("Returning instances slated for deletion.")
    return build_result.surplus_vms
