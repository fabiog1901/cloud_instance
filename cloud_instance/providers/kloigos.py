import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from ..models import CloudInstance, Group

logger = logging.getLogger("cloud_instance")

EMPTY_BODY = " "


def parse_instance(unit: dict[str, Any]) -> CloudInstance:
    tags = unit.get("tags") or {}
    inventory_groups = tags.get("inventory_groups", [])
    if isinstance(inventory_groups, str):
        inventory_groups = json.loads(inventory_groups)

    extra_vars = tags.get("extra_vars", {})
    if isinstance(extra_vars, str):
        try:
            extra_vars = json.loads(extra_vars)
        except json.JSONDecodeError:
            pass

    return CloudInstance(
        id=unit["compute_id"],
        cloud="kloigos",
        region=unit["region"],
        zone=unit["zone"],
        public_ip=unit.get("ip"),
        public_hostname=unit.get("hostname", ""),
        private_ip=unit.get("ip"),
        private_hostname=unit.get("hostname", ""),
        ansible_user=unit.get("cu_user", tags.get("ansible_user", "")),
        inventory_groups=inventory_groups,
        cluster_name=tags.get("cluster_name", ""),
        group_name=tags.get("group_name", ""),
        extra_vars=extra_vars,
    )


def fetch_instances(deployment_id: str, update_instances_list, update_errors):
    if not is_configured():
        logger.debug("Skipping Kloigos fetch because Kloigos env vars are not set")
        return

    try:
        units = request("GET", "/compute_units/", {"deployment_id": deployment_id})
        instances = [
            parse_instance(unit)
            for unit in units
            if unit.get("status") not in ("FREE", "DEALLOCATING", "DEALLOCATED")
        ]
        if instances:
            update_instances_list(instances)
    except Exception as e:
        update_errors(e)


def provision_vm(
    deployment_id: str,
    cluster_name: str,
    group: Group,
    x: int,
    get_instance_type,
    update_new_deployment,
    update_errors,
):
    logger.info("++kloigos %s %s %s" % (cluster_name, group.group_name, x))

    try:
        cpu_count = group.instance.cpu if group.instance else None
        if cpu_count is None:
            raise ValueError("Kloigos requires group.instance.cpu")
        if not group.public_key_id:
            raise ValueError("Kloigos requires group.public_key_id as ssh_public_key")

        tags = dict(group.tags)
        tags.update(
            {
                "deployment_id": deployment_id,
                "ansible_user": group.user or "",
                "cluster_name": cluster_name,
                "group_name": group.group_name or "",
                "inventory_groups": group.inventory_groups + [cluster_name],
                "extra_vars": json.dumps(group.extra_vars),
            }
        )

        compute_id = request(
            "POST",
            "/compute_units/allocate",
            body={
                "compute_id": None,
                "cpu_count": int(cpu_count),
                "region": group.region,
                "zone": group.zone,
                "tags": tags,
                "ssh_public_key": group.public_key_id,
            },
        )

        units = request("GET", "/compute_units/", {"compute_id": compute_id})
        if not units:
            raise ValueError(
                f"Kloigos allocated {compute_id}, but it is not listable yet"
            )

        update_new_deployment([parse_instance(units[0])])
    except Exception as e:
        update_errors(e)


def terminate_vm(instance: CloudInstance, update_errors):
    logger.info(f"--kloigos {instance.id}")

    try:
        request("DELETE", f"/compute_units/deallocate/{instance.id}")
    except Exception as e:
        update_errors(e)


def modify_vm(instance: CloudInstance, new_cpus_count, get_instance_type, update_errors):
    update_errors("Kloigos does not support instance type modification")


def resize_vm(instance: CloudInstance, new_disk_size, update_errors):
    update_errors("Kloigos does not support disk resize")


def request(
    method: str,
    path: str,
    query: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
):
    base_url = os.getenv("KLOIGOS_API_URL")
    access_key = os.getenv("KLOIGOS_ACCESS_KEY")
    secret_key = os.getenv("KLOIGOS_SECRET_ACCESS_KEY")

    if not base_url:
        raise ValueError("KLOIGOS_API_URL env var is not defined")
    if not access_key:
        raise ValueError("KLOIGOS_ACCESS_KEY env var is not defined")
    if not secret_key:
        raise ValueError("KLOIGOS_SECRET_ACCESS_KEY env var is not defined")

    url = build_url(base_url, path, query)
    body_text = (
        json.dumps(body, separators=(",", ":")) if body is not None else EMPTY_BODY
    )
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    signature = sign(method, url, timestamp, body_text, secret_key)

    req = Request(
        url,
        data=body_text.encode(),
        method=method,
        headers={
            "Content-Type": "application/json",
            "X-Kloigos-Access-Key": access_key,
            "X-Timestamp": timestamp,
            "X-Kloigos-Signature": signature,
        },
    )

    try:
        with urlopen(req, timeout=30) as response:
            response_body = response.read().decode()
    except HTTPError as e:
        error_body = e.read().decode()
        raise ValueError(
            f"Kloigos API {method} {path} failed: {e.code} {error_body}"
        ) from e
    except URLError as e:
        raise ValueError(f"Kloigos API {method} {path} failed: {e.reason}") from e

    if not response_body:
        return None

    try:
        return json.loads(response_body)
    except json.JSONDecodeError:
        return response_body


def build_url(
    base_url: str,
    path: str,
    query: dict[str, Any] | None = None,
) -> str:
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    clean_query = {
        k: v
        for k, v in (query or {}).items()
        if v is not None
    }
    if clean_query:
        return f"{url}?{urlencode(clean_query)}"
    return url


def sign(method: str, url: str, timestamp: str, body: str, secret_key: str) -> str:
    parsed = urlparse(url)
    path_and_query = parsed.path
    if parsed.query:
        path_and_query = f"{path_and_query}?{parsed.query}"

    string_to_sign = "\n".join([method, path_and_query, timestamp, body])
    return hmac.new(
        secret_key.encode(),
        string_to_sign.encode(),
        hashlib.sha256,
    ).hexdigest()


def is_configured() -> bool:
    return all(
        os.getenv(name)
        for name in (
            "KLOIGOS_API_URL",
            "KLOIGOS_ACCESS_KEY",
            "KLOIGOS_SECRET_ACCESS_KEY",
        )
    )
