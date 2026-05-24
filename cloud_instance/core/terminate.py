import logging
from threading import Lock, Thread

from ..models import CloudInstance
from ..providers import aws, azure, gcp, kloigos
from .errors import operation_error

logger = logging.getLogger("cloud_instance")

errors: list[object] = []
state_lock = Lock()


def terminate(instances: list[CloudInstance]) -> None:
    threads: list[Thread] = []
    global errors
    errors = []

    for x in instances:
        target = {
            "aws": aws.terminate_vm,
            "gcp": gcp.terminate_vm,
            "azure": azure.terminate_vm,
            "kloigos": kloigos.terminate_vm,
        }.get(x.cloud)
        if target is None:
            update_errors(f"Unsupported cloud provider: {x.cloud}")
            continue

        thread = Thread(
            target=target,
            args=(x, update_errors),
        )
        thread.start()
        threads.append(thread)
        logger.info(f"Deleting instance: {x}")

    for x in threads:
        x.join()

    if errors:
        raise operation_error("Terminate instances", errors)


def update_errors(error: object):
    global errors
    logger.error(error)
    with state_lock:
        errors.append(error)
