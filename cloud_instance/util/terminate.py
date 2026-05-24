import logging
from threading import Lock, Thread

from ..providers.aws import terminate_vm as terminate_aws_vm
from ..providers.azure import terminate_vm as terminate_azure_vm
from ..providers.gcp import terminate_vm as terminate_gcp_vm

logger = logging.getLogger("cloud_instance")

errors: list[str] = []


def terminate(instances: list[dict]) -> None:
    threads: list[Thread] = []

    for x in instances:
        thread = Thread(
            target={
                "aws": terminate_aws_vm,
                "gcp": terminate_gcp_vm,
                "azure": terminate_azure_vm,
            }.get(x["cloud"]),
            args=(x, update_errors),
        )
        thread.start()
        threads.append(thread)
        logger.info(f"Deleting instance: {x}")

    for x in threads:
        x.join()

    global errors

    if errors:
        raise ValueError("Failed to terminate instances.")


def update_errors(error: str):
    global errors
    logger.error(error)
    with Lock():
        errors.append(error)
