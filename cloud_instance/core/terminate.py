import logging
from threading import Lock, Thread

from ..models import CloudInstance
from ..providers.aws import terminate_vm as terminate_aws_vm
from ..providers.azure import terminate_vm as terminate_azure_vm
from ..providers.gcp import terminate_vm as terminate_gcp_vm
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
            "aws": terminate_aws_vm,
            "gcp": terminate_gcp_vm,
            "azure": terminate_azure_vm,
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
