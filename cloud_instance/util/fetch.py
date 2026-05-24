import logging
from threading import Lock, Thread

from ..providers.aws import fetch_instances as fetch_aws_instances
from ..providers.gcp import fetch_instances as fetch_gcp_instances

logger = logging.getLogger("cloud_instance")

instances: list[dict] = []
errors: list[str] = []


def fetch(deployment_id: str):
    threads: list[Thread] = []
    global instances
    global errors

    thread = Thread(
        target=fetch_aws_instances,
        args=(deployment_id, update_instances_list, update_errors),
    )
    thread.start()
    threads.append(thread)

    thread = Thread(
        target=fetch_gcp_instances,
        args=(deployment_id, update_instances_list, update_errors),
    )
    thread.start()
    threads.append(thread)

    for x in threads:
        x.join()

    instances = sorted(instances, key=lambda d: d["id"])

    if errors:
        raise ValueError(f"Failed to fetch resources for {deployment_id=}")

    return instances


def update_instances_list(_instances: list):
    global instances
    with Lock():
        logger.debug("Updating instances list")
        instances += _instances


def update_errors(error: str):
    global errors
    logger.error(error)
    with Lock():
        errors.append(error)
