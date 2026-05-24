import logging

from ..core.build import build
from ..core.fetch import fetch
from ..core.provision import provision
from ..core.terminate import terminate
from ..models import CloudInstance, Deployment, InstanceDefaults

logger = logging.getLogger("cloud_instance")


def create(
    deployment_id: str,
    deployment: Deployment,
    defaults: InstanceDefaults,
    preserve: bool,
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

    logger.info("Provisioning new_vms...")

    try:
        new_instances = provision(build_result.new_vms, defaults)
    except Exception as e:
        raise ValueError(f"Failed to provision for {deployment_id=}:\n{e}") from e

    if not preserve:
        logger.info("Deleting surplus_vms...")
        try:
            terminate(build_result.surplus_vms)
        except Exception as e:
            raise ValueError(
                f"Failed to delete surplus_vms for {deployment_id=}:\n{e}"
            ) from e

    result = list(new_instances)
    result.extend(build_result.current_vms)

    logger.info(f"new deployment count={len(result)}")
    for idx, x in enumerate(result, start=1):
        logger.info(f"{idx}:\t{x}")

    logger.info("Returning new deployment list to client")

    return result
