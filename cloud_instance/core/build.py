import logging

from ..models import (
    BuildResult,
    CloudInstance,
    Cluster,
    Deployment,
    Group,
    ProvisionTask,
)

logger = logging.getLogger("cloud_instance")

current_instances: list[CloudInstance] = []


def build(
    deployment_id: str,
    deployment: Deployment,
    fetched_instances: list[CloudInstance],
) -> BuildResult:
    global current_instances
    current_instances = list(fetched_instances)

    result = BuildResult()

    for cluster in deployment.clusters:
        cluster_name = cluster.cluster_name or deployment_id
        copies = int(cluster.copies or 1)
        for x in range(copies):
            cluster_result = build_cluster(
                f"{cluster_name}-{x}",
                cluster,
                deployment_id,
            )
            result.current_vms.extend(cluster_result.current_vms)
            result.surplus_vms.extend(cluster_result.surplus_vms)
            result.new_vms.extend(cluster_result.new_vms)

    result.surplus_vms.extend(current_instances)
    return result


def build_cluster(
    cluster_name: str,
    cluster: Cluster,
    deployment_id: str,
) -> BuildResult:
    result = BuildResult()

    for group in cluster.groups:
        group_result = build_group(
            cluster_name,
            merge_cluster_group(cluster, group),
            deployment_id,
        )
        result.current_vms.extend(group_result.current_vms)
        result.surplus_vms.extend(group_result.surplus_vms)
        result.new_vms.extend(group_result.new_vms)

    return result


def build_group(
    cluster_name: str,
    group: Group,
    deployment_id: str,
) -> BuildResult:
    result = BuildResult()

    global current_instances

    for instance in list(current_instances):
        if matches_group(instance, cluster_name, group):
            result.current_vms.append(instance)
            current_instances.remove(instance)

    current_count = len(result.current_vms)
    new_exact_count = int(group.exact_count or 0)

    if current_count < new_exact_count:
        for x in range(new_exact_count - current_count):
            result.new_vms.append(
                ProvisionTask(
                    deployment_id=deployment_id,
                    cluster_name=cluster_name,
                    group=group,
                    index=x,
                )
            )
    elif current_count > new_exact_count:
        for x in range(current_count - new_exact_count):
            result.surplus_vms.append(result.current_vms.pop(-1))

    return result


def matches_group(instance: CloudInstance, cluster_name: str, group: Group) -> bool:
    return (
        instance.cluster_name == cluster_name
        and instance.group_name == group.group_name
        and instance.region == group.region
        and instance.zone == group.zone
    )


def merge_cluster_group(parent: Cluster, child: Group) -> Group:
    parent_data = parent.to_dict()
    child_data = child.to_dict()
    merged = {}

    for k, v in parent_data.get("import", {}).items():
        merged[k] = v

    for k, v in parent_data.items():
        merged[k] = v

    for k, v in child_data.get("import", {}).items():
        merged[k] = v

    for k, v in child_data.items():
        merged[k] = v

    tags = parent_data.get("tags", {})
    tags.update(child_data.get("tags", {}))
    merged["tags"] = tags

    merged["inventory_groups"] = list(
        set(
            parent_data.get("inventory_groups", []) + merged.get("inventory_groups", [])
        )
    )

    merged["security_groups"] = list(
        set(parent_data.get("security_groups", []) + merged.get("security_groups", []))
    )

    merged.setdefault("group_name", sorted(merged["inventory_groups"])[0])

    return Group.from_dict(merged)
