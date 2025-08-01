import logging
from threading import Thread, Lock
from .provision import provision_aws_vm, provision_gcp_vm, provision_azure_vm

logger = logging.getLogger("cloud_instance")

new_instances: list[dict] = []
errors: list[str] = []
threads: list[Thread]


def update_new_deployment(_instances: list):
    global new_instances
    with Lock():
        logger.debug("Updating new instances list")
        new_instances += _instances


def update_errors(error: str):
    global errors
    with Lock():
        errors.append(error)


def build_deployment(
    deployment_id: str,
    deployment: list[dict],
    current_instances,
    gcp_project,
    azure_subscription_id,
    azure_resource_group,
):
    # 4. loop through the 'deployment' struct
    #    - through each cluster and copies
    #    - through each group within each cluster

    # loop through each cluster item in the deployment list
    for cluster in deployment:
        # extract the cluster name for all copies,
        # then, for each requested copy, add the index suffix
        cluster_name: str = cluster.get("cluster_name", deployment_id)
        for x in range(int(cluster.get("copies", 1))):
            build_cluster(
                f"{cluster_name}-{x}",
                cluster,
                deployment_id,
                current_instances,
                gcp_project,
                azure_subscription_id,
                azure_resource_group,
            )

    global threads
    global new_instances
    return new_instances, threads


def build_cluster(
    cluster_name: str,
    cluster: dict,
    deployment_id,
    current_instances,
    gcp_project,
    azure_subscription_id,
    azure_resource_group,
):
    # for each group in the cluster,
    # put all cluster defaults into the group
    for group in cluster.get("groups", []):
        build_group(
            cluster_name,
            merge_dicts(cluster, group),
            current_instances,
            deployment_id,
            gcp_project,
            azure_subscription_id,
            azure_resource_group,
        )


def build_group(
    cluster_name: str,
    group: dict,
    current_instances: list[dict],
    deployment_id,
    gcp_project,
    azure_subscription_id,
    azure_resource_group,
):
    # 5. for each group, compare what is in 'deployment' to what is in 'current_deployment':
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

    for x in current_instances[:]:
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

    # CASE 1
    if current_count == new_exact_count:
        pass

    # CASE 2: ADD instances
    elif current_count < new_exact_count:

        for x in range(new_exact_count - current_count):

            if group["cloud"] == "aws":
                thread = Thread(
                    target=provision_aws_vm,
                    args=(deployment_id, cluster_name, group, x),
                )
            elif group["cloud"] == "gcp":
                thread = Thread(
                    target=provision_gcp_vm,
                    args=(deployment_id, cluster_name, group, x, gcp_project),
                )
            elif group["cloud"] == "azure":
                thread = Thread(
                    target=provision_azure_vm,
                    args=(
                        deployment_id,
                        cluster_name,
                        group,
                        x,
                        azure_subscription_id,
                        azure_resource_group,
                    ),
                )
            else:
                pass

            # thread.start()
            global threads
            threads.append(thread)

    # CASE 3: REMOVE instances
    else:
        for x in range(current_count - new_exact_count):
            current_instances.append(current_group.pop(-1))

    update_new_deployment(current_group)


# UTIL METHODS
# =========================================================================


def merge_dicts(self, parent: dict, child: dict):
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
