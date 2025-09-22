import logging

from google.api_core.extended_operation import ExtendedOperation

logger = logging.getLogger("cloud_instance")


def wait_for_extended_operation(op: ExtendedOperation):
    result = op.result(timeout=300)

    if op.error_code:
        logger.error(f"GCP Error: {op.error_code}: {op.error_message}")
        raise ValueError(f"GCP Error: {op.error_code}: {op.error_message}")

    return result
