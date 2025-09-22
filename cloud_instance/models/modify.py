import json
import logging
import os
import random
import time
from threading import Lock, Thread

# AWS
import boto3

# AZURE
from azure.identity import EnvironmentCredential
from azure.mgmt.compute import ComputeManagementClient
from google.api_core.extended_operation import ExtendedOperation

# GCP
from google.cloud.compute_v1 import InstancesClient, InstancesSetMachineTypeRequest

from ..util.common import wait_for_extended_operation
from ..util.fetch import fetch

logger = logging.getLogger("cloud_instance")

errors: list[str] = []
defaults: dict = {}


def update_errors(error: str):
    global errors
    logger.error(error)
    with Lock():
        errors.append(error)


def get_instance_type(group: dict):
    if "instance_type" in group:
        return group["instance_type"]

    # instance type
    cpu = str(group["instance"].get("cpu"))
    if cpu == "None":
        update_errors("instance cpu cannot be null")
        return

    mem = str(group["instance"].get("mem", "default"))
    cloud = group["cloud"]
    global defaults

    return defaults[cloud][cpu][mem]


def modify(
    deployment_id: str,
    new_cpus_count: int,
    filter_by_groups: list[str] = [],
    sequential: bool = True,
    pause_between: int = 30,
    instance_defaults: dict = {},
) -> None:

    logger.info(f"Fetching all instances with {deployment_id=}")

    try:
        current_instances = fetch(deployment_id)
    except:
        raise ValueError(f"Failed to fetch instances for {deployment_id=}")

    logger.info(f"current_instances count={len(current_instances)}")
    for idx, x in enumerate(current_instances, start=1):
        logger.info(f"{idx}:\t{x}")

    filtered_instances = []

    for idx, x in enumerate(current_instances, start=1):
        inv_grps = set(x.get("inventory_groups", []))
        if (
            len(filter_by_groups) == 0
            or inv_grps
            and set(filter_by_groups).issubset(inv_grps)
        ):
            filtered_instances.append(x)

    global defaults
    defaults = instance_defaults

    if sequential:
        for x in filtered_instances:
            if x["cloud"] == "aws":
                modify_aws_vm(x, new_cpus_count)
            elif x["cloud"] == "gcp":
                modify_gcp_vm(x, new_cpus_count)
            else:
                modify_azure_vm(x, new_cpus_count)

            logger.info(f"Pausing for {pause_between} seconds...")
            time.sleep(pause_between)
    else:
        threads = []
        for x in filtered_instances:
            t = Thread(
                target={
                    "aws": modify_aws_vm,
                    "gcp": modify_gcp_vm,
                    "azure": modify_azure_vm,
                }.get(x["cloud"]),
                args=(x, new_cpus_count),
            )
            t.start()
            threads.append(t)

        for x in threads:
            x.join()

    global errors

    if errors:
        raise ValueError(f"Failed to modify instances for {deployment_id=}")


def modify_aws_vm(x: dict, new_cpus_count):
    instance_id = x["id"]

    try:
        client = boto3.client("ec2", region_name=x["region"])

        logger.info(f"Modifying {instance_id=} {new_cpus_count=}")

        # 1) Stop (required to change type)
        client.stop_instances(InstanceIds=[instance_id])
        client.get_waiter("instance_stopped").wait(InstanceIds=[instance_id])

        logger.info(f"Stopped {instance_id}")

        # 2) Modify type
        new_instance_type = get_instance_type(
            {
                "cloud": x["cloud"],
                "instance": {
                    "cpu": new_cpus_count,
                },
            }
        )

        client.modify_instance_attribute(
            InstanceId=instance_id,
            InstanceType={"Value": new_instance_type},
        )

        logger.info(f"Modified {instance_id} to {new_instance_type}")

        # 3) Start
        client.start_instances(InstanceIds=[instance_id])
        client.get_waiter("instance_running").wait(InstanceIds=[instance_id])

        logger.info(f"Restarted {instance_id}")

    except Exception as e:
        update_errors(e)


def modify_gcp_vm(x: dict, new_cpus_count: int):

    instance_id = x["id"]

    gcp_project = os.getenv("GCP_PROJECT")
    if not gcp_project:
        update_errors("GCP_PROJECT env var is not defined")
        return

    gcpzone = f"{x['region']}-{x['zone']}"

    try:
        client = InstancesClient()

        logger.info(f"Modifying {instance_id=} {new_cpus_count=}")

        # 1) Stop the instance (required to change machine type)
        op = client.stop(project=gcp_project, zone=gcpzone, instance=instance_id)
        wait_for_extended_operation(op)
        logger.info(f"Stopped {instance_id}")

        # 2) Set the new machine type
        new_instance_type = get_instance_type(
            {
                "cloud": x["cloud"],
                "instance": {
                    "cpu": new_cpus_count,
                },
            }
        )

        req = InstancesSetMachineTypeRequest(
            machine_type=f"zones/{gcpzone}/machineTypes/{new_instance_type}"
        )
        op = client.set_machine_type(
            project=gcp_project,
            zone=gcpzone,
            instance=instance_id,
            instances_set_machine_type_request_resource=req,
        )
        wait_for_extended_operation(op)
        logger.info(f"Modified {instance_id} to {new_instance_type}")

        # 3) Start the instance
        op = client.start(project=gcp_project, zone=gcpzone, instance=instance_id)
        wait_for_extended_operation(op)
        logger.info(f"Restarted {instance_id}")

    except Exception as e:
        update_errors(e)


def modify_azure_vm(
    deployment_id: str,
    cluster_name: str,
    group: dict,
    x: int,
    azure_subscription_id,
    azure_resource_group,
):
    # TODO: implement
    raise ValueError("NOT IMPLEMENTED")
    return

    logger.debug("++azure %s %s %s" % (cluster_name, group["group_name"], x))

    try:
        # Acquire a credential object using CLI-based authentication.
        credential = EnvironmentCredential()
        client = ComputeManagementClient(credential, azure_subscription_id)

        instance_name = deployment_id + "-" + str(random.randint(0, 1e16)).zfill(16)

        def get_type(x):
            return {
                "standard_ssd": "Premium_LRS",
                "premium_ssd": "PremiumV2_LRS",
                "local_ssd": "Premium_LRS",
                "standard_hdd": "Standard_LRS",
                "premium_hdd": "Standard_LRS",
            }.get(x, "Premium_LRS")

        vols = []
        i: int
        x: dict

        for i, x in enumerate(group["volumes"]["data"]):
            poller = client.disks.begin_create_or_update(
                azure_resource_group,
                instance_name + "-disk-" + str(i),
                {
                    "location": group["region"],
                    "sku": {"name": get_type(x.get("type", "standard_ssd"))},
                    "disk_size_gb": int(x.get("size", 100)),
                    "creation_data": {"create_option": "Empty"},
                },
            )

            #     "diskIOPSReadWrite": "15000",
            # "diskMBpsReadWrite": "250"
            data_disk = poller.result()

            disk = {
                "lun": i,
                "name": instance_name + "-disk-" + str(i),
                "create_option": "Attach",
                "delete_option": (
                    "Delete" if x.get("delete_on_termination", True) else "Detach"
                ),
                "managed_disk": {"id": data_disk.id},
            }
            vols.append(disk)

        # Provision the virtual machine
        publisher, offer, sku, version = group["image"].split(":")

        nsg = None
        if group["security_groups"]:
            nsg = {
                "id": "/subscriptions/%s/resourceGroups/%s/providers/Microsoft.Network/networkSecurityGroups/%s"
                % (
                    azure_subscription_id,
                    azure_resource_group,
                    group["security_groups"][0],
                )
            }

        poller = client.virtual_machines.begin_create_or_update(
            azure_resource_group,
            instance_name,
            {
                "location": group["region"],
                "tags": {
                    "deployment_id": deployment_id,
                    "ansible_user": group["user"],
                    "cluster_name": cluster_name,
                    "group_name": group["group_name"],
                    "inventory_groups": json.dumps(
                        group["inventory_groups"] + [cluster_name]
                    ),
                    "extra_vars": json.dumps(group.get("extra_vars", {})),
                },
                "storage_profile": {
                    "osDisk": {
                        "createOption": "fromImage",
                        "managedDisk": {"storageAccountType": "Premium_LRS"},
                        "deleteOption": "delete",
                    },
                    "image_reference": {
                        "publisher": publisher,
                        "offer": offer,
                        "sku": sku,
                        "version": version,
                    },
                    "data_disks": vols,
                },
                "hardware_profile": {
                    "vm_size": get_instance_type(group),
                },
                "os_profile": {
                    "computer_name": instance_name,
                    "admin_username": group["user"],
                    "linux_configuration": {
                        "ssh": {
                            "public_keys": [
                                {
                                    "path": "/home/%s/.ssh/authorized_keys"
                                    % group["user"],
                                    "key_data": group["public_key_id"],
                                }
                            ]
                        }
                    },
                },
                "network_profile": {
                    "network_api_version": "2021-04-01",
                    "network_interface_configurations": [
                        {
                            "name": instance_name + "-nic",
                            "delete_option": "delete",
                            "network_security_group": nsg,
                            "ip_configurations": [
                                {
                                    "name": instance_name + "-nic",
                                    "subnet": {
                                        "id": "/subscriptions/%s/resourceGroups/%s/providers/Microsoft.Network/virtualNetworks/%s/subnets/%s"
                                        % (
                                            azure_subscription_id,
                                            azure_resource_group,
                                            group["vpc_id"],
                                            group["subnet"],
                                        )
                                    },
                                    "public_ip_address_configuration": {
                                        "name": instance_name + "-pip",
                                        "sku": {
                                            "name": "Standard",
                                            "tier": "Regional",
                                        },
                                        "delete_option": "delete",
                                        "public_ip_allocation_method": "static",
                                    },
                                }
                            ],
                        }
                    ],
                },
            },
        )

        instance = poller.result()

        # add the instance to the list
        # update_new_deployment(
        #     parse_azure_query(
        #         instance,
        #         *fetch_azure_instance_network_config(instance),
        #     )
        # )

    except Exception as e:
        logger.error(e)
        update_errors(e)
