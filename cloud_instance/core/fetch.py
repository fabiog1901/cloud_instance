import logging
from threading import Lock, Thread

from ..models import CloudInstance
from ..providers.aws import fetch_instances as fetch_aws_instances
from ..providers.gcp import fetch_instances as fetch_gcp_instances
from .errors import operation_error

logger = logging.getLogger("cloud_instance")

instances: list[CloudInstance] = []
errors: list[object] = []
state_lock = Lock()


def fetch(deployment_id: str) -> list[CloudInstance]:
    threads: list[Thread] = []
    global instances
    global errors
    instances = []
    errors = []

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

    instances = sorted(instances, key=lambda x: x.id)

    if errors:
        raise operation_error(f"Fetch resources for {deployment_id=}", errors)

    return instances


def update_instances_list(_instances: list[CloudInstance]):
    global instances
    with state_lock:
        logger.debug("Updating instances list")
        instances.extend(_instances)


def update_errors(error: object):
    global errors
    logger.error(error)
    with state_lock:
        errors.append(error)
