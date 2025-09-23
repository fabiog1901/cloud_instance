import logging
from threading import Lock, Thread

from .provision import provision_aws_vm, provision_azure_vm, provision_gcp_vm

logger = logging.getLogger("cloud_instance")

current_instances: list[dict] = []


def build(
    deployment_id: str,
    deployment: list[dict],
    _current_instances: list[dict],
):
    # 4. loop through the 'deployment' struct
    #    - through each cluster and copies
    #    - through each group within each cluster
    new_vms = []
    surplus_vms = []
    current_vms = []

    global current_instances
    current_instances = _current_instances

    # loop through each cluster item in the deployment list
    for cluster in deployment:
        # extract the cluster name for all copies,
        # then, for each requested copy, add the index suffix
        cluster_name: str = cluster.get("cluster_name", deployment_id)
        for x in range(int(cluster.get("copies", 1))):
            _current_vms, _surplus_vms, _new_vms = build_cluster(
                f"{cluster_name}-{x}",
                cluster,
                deployment_id,
            )
            new_vms += _new_vms
            surplus_vms += _surplus_vms
            current_vms += _current_vms

    return current_vms, surplus_vms + current_instances, new_vms


def build_cluster(
    cluster_name: str,
    cluster: dict,
    deployment_id,
):
    # for each group in the cluster,
    # put all cluster defaults into the group
    new_vms = []
    surplus_vms = []
    current_vms = []

    for group in cluster.get("groups", []):
        _current_vms, _surplus_vms, _new_vms = build_group(
            cluster_name,
            merge_dicts(cluster, group),
            deployment_id,
        )
        new_vms += _new_vms
        surplus_vms += _surplus_vms
        current_vms += _current_vms

    return current_vms, surplus_vms, new_vms


def build_group(
    cluster_name: str,
    group: dict,
    deployment_id,
):
    # for each group, compare what is in 'deployment' to what is in 'current_deployment':
    #     case NO DIFFERENCE
    #       return the details in current_deployment
    #
    #     case TOO FEW
    #       for each exact count, start a thread to create the requested instance
    #       return current_deployment + the details of the newly created instances
    #
    #     case TOO MANY
    #        for each instance that's too many, start a thread to destroy the instance
    #        return current_deployment minus what was distroyed

    # get all instances in the current group
    current_group = []
    new_vms = []
    surplus_vms = []

    global current_instances

    for x in current_instances.copy():
        if (
            x["cluster_name"] == cluster_name
            and x["group_name"] == group["group_name"]
            and x["region"] == group["region"]
            and x["zone"] == group["zone"]
        ):
            current_group.append(x)
            current_instances.remove(x)

    current_count = len(current_group)
    new_exact_count = int(group.get("exact_count", 0))

    # ADD instances
    if current_count < new_exact_count:
        for x in range(new_exact_count - current_count):
            new_vms.append(
                Thread(
                    target={
                        "aws": provision_aws_vm,
                        "gcp": provision_gcp_vm,
                        "azure": provision_azure_vm,
                    }.get(group["cloud"]),
                    args=(deployment_id, cluster_name, group, x),
                )
            )

    # REMOVE instances
    elif current_count > new_exact_count:
        for x in range(current_count - new_exact_count):
            surplus_vms.append(current_group.pop(-1))

    return current_group, surplus_vms, new_vms


def merge_dicts(parent: dict, child: dict):
    merged = {}

    # add all kv pairs of 'import'
    for k, v in parent.get("import", {}).items():
        merged[k] = v

    # parent explicit override parent imports
    for k, v in parent.items():
        merged[k] = v

    # child imports override parent
    for k, v in child.get("import", {}).items():
        merged[k] = v

    # child explicit override child import and parent
    for k, v in child.items():
        merged[k] = v

    # merge the items in tags, child overrides parent
    tags_dict = parent.get("tags", {})
    for k, v in child.get("tags", {}).items():
        tags_dict[k] = v

    merged["tags"] = tags_dict

    # aggregate the inventory groups
    merged["inventory_groups"] = list(
        set(parent.get("inventory_groups", []) + merged.get("inventory_groups", []))
    )

    # aggregate the security groups
    merged["security_groups"] = list(
        set(parent.get("security_groups", []) + merged.get("security_groups", []))
    )

    # group_name
    merged.setdefault("group_name", sorted(merged["inventory_groups"])[0])

    # aggregate the volumes
    # TODO

    return merged
