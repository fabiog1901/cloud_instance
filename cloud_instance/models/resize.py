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
from google.cloud.compute_v1 import DisksClient, DisksResizeRequest, InstancesClient

from ..util.common import wait_for_extended_operation
from ..util.fetch import fetch

logger = logging.getLogger("cloud_instance")

errors: list[str] = []


def update_errors(error: str):
    global errors
    logger.error(error)
    with Lock():
        errors.append(error)


def resize(
    deployment_id: str,
    new_disk_size: int,
    filter_by_groups: list[str] = [],
    sequential: bool = True,
    pause_between: int = 30,
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

    if sequential:
        for x in filtered_instances:
            if x["cloud"] == "aws":
                resize_aws_vm(x, new_disk_size)
            elif x["cloud"] == "gcp":
                resize_gcp_vm(x, new_disk_size)
            else:
                resize_azure_vm(x, new_disk_size)

            logger.info(f"Pausing for {pause_between} seconds...")
            time.sleep(pause_between)
    else:
        threads = []
        for x in filtered_instances:
            t = Thread(
                target={
                    "aws": resize_aws_vm,
                    "gcp": resize_gcp_vm,
                    "azure": resize_azure_vm,
                }.get(x["cloud"]),
                args=(x, new_disk_size),
            )
            t.start()
            threads.append(t)

        for x in threads:
            x.join()

    global errors

    if errors:
        raise ValueError(f"Failed to resize instances for {deployment_id=}")


def resize_aws_vm(x: dict, new_disk_size):
    instance_id = x["id"]

    client = boto3.client("ec2", region_name=x["region"])

    def get_volume_id(instance_id: str) -> str:
        resp = client.describe_instances(InstanceIds=[instance_id])
        reservations = resp.get("Reservations", [])
        for r in reservations:
            for inst in r.get("Instances", []):
                for mapping in inst.get("BlockDeviceMappings", []):
                    if mapping["DeviceName"] != "/dev/sda1":
                        return mapping["Ebs"]["VolumeId"]

    def wait_for_resize(volume_id: str, timeout_s: int = 900):
        """
        Poll describe_volumes_modifications until the state is 'optimizing' or 'completed'.
        (Either state is OK to proceed with filesystem growth in most cases.)
        """
        start = time.time()
        while True:
            mods = client.describe_volumes_modifications(VolumeIds=[volume_id]).get(
                "VolumesModifications", []
            )
            state = mods[0]["ModificationState"] if mods else "unknown"
            if state in ("optimizing", "completed"):
                return state
            if time.time() - start > timeout_s:
                raise ValueError(
                    f"Timed out waiting for {volume_id} to resize (last state: {state})"
                )

            time.sleep(5)

    try:
        logger.info(f"Resize {instance_id=} {new_disk_size=}")

        vol_id = get_volume_id(instance_id)
        vol = boto3.client("ec2", region_name=x["region"]).describe_volumes(
            VolumeIds=[vol_id]
        )["Volumes"][0]
        current_size = vol["Size"]

        if new_disk_size <= current_size:
            update_errors(
                f"Volume {vol_id} is already {current_size} GiB (>= {new_disk_size}). Nothing to do."
            )
            return

        logger.info(f"Resizing {vol_id} from {current_size} -> {new_disk_size} GiB ...")
        client.modify_volume(VolumeId=vol_id, Size=new_disk_size)

        wait_for_resize(vol_id)

        logger.info(f"Resize complete for volume {vol_id}.")

    except Exception as e:
        update_errors(e)


def resize_gcp_vm(x: dict, new_disk_size: int):

    instance_id = x["id"]

    gcp_project = os.getenv("GCP_PROJECT")
    if not gcp_project:
        update_errors("GCP_PROJECT env var is not defined")
        return

    gcpzone = f"{x['region']}-{x['zone']}"

    try:

        client = InstancesClient()
        instance = client.get(
            project=gcp_project,
            zone=gcpzone,
            instance=instance_id,
        )

        disk_client = DisksClient()

        for disk in instance.disks:
            # `source` is a full URL, last part is the disk name
            disk_name = disk.source.split("/")[-1]
            if not disk.boot:

                logger.info(f"Modifying {instance_id=} {new_disk_size=}")

                op = disk_client.resize(
                    project=gcp_project,
                    zone=gcpzone,
                    disk=disk_name,
                    disks_resize_request_resource=DisksResizeRequest(
                        size_gb=new_disk_size
                    ),
                )
                wait_for_extended_operation(op)
                logger.info(f"Resized {instance_id}")

    except Exception as e:
        update_errors(e)


def resize_azure_vm(
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
