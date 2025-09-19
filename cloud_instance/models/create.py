import logging

# setup global logger
logger = logging.getLogger("cloud_instance")


from ..util.build import build_deployment
from ..util.fetch import fetch_all
from ..util.provision import provision
from .delete import delete


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
        delete(surplus_vms)

    logger.info(f"new deployment count={len(new_instances + current_vms)}")
    for idx, x in enumerate(new_instances + current_vms, start=1):
        logger.info(f"{idx}:\t{x}")

    if errors:
        raise ValueError(errors)

    logger.info("Returning new deployment list to client")
    return new_instances + current_vms
