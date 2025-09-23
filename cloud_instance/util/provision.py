import json
import logging
import os
import random
from threading import Lock, Thread

# AWS
import boto3

# AZURE
from azure.identity import EnvironmentCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.network import NetworkManagementClient
from google.api_core.extended_operation import ExtendedOperation

# GCP
from google.cloud.compute_v1 import (
    AccessConfig,
    AddressesClient,
    AttachedDisk,
    AttachedDiskInitializeParams,
    Instance,
    InstancesClient,
    NetworkInterface,
    Tags,
)
from google.cloud.compute_v1.services.addresses.client import AddressesClient
from google.cloud.compute_v1.services.global_addresses import GlobalAddressesClient
from google.cloud.compute_v1.types import Address, Items, Metadata

from .common import wait_for_extended_operation
from .parse import parse_aws_query, parse_azure_query, parse_gcp_query

logger = logging.getLogger("cloud_instance")

instances: list[dict] = []
errors: list[str] = []
defaults: dict = {}


def update_new_deployment(_instances: list):
    global instances
    with Lock():
        logger.debug("Updating pre-existing instances list")
        instances += _instances


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


def provision(new_vms: list[Thread], instance_defaults) -> list[dict]:
    global defaults
    defaults = instance_defaults

    for x in new_vms:
        x.start()

    for x in new_vms:
        x.join()

    global instances
    global errors

    if errors:
        raise ValueError("Failed to provision instances.")

    return instances


def provision_aws_vm(deployment_id: str, cluster_name: str, group: dict, x: int):
    logger.debug("++aws %s %s %s" % (cluster_name, group["region"], x))

    # volumes
    def get_type(x):
        return {
            "standard_ssd": "gp3",
            "premium_ssd": "io2",
            "gp2": "gp2",
            "standard_hdd": "sc1",
            "premium_hdd": "st1",
        }.get(x, "gp3")

    try:
        vols = [group["volumes"]["os"]] + group["volumes"]["data"]

        bdm = []

        for i, x in enumerate(vols):
            dev = {
                "DeviceName": "/dev/sd" + (chr(ord("e") + i)),
                "Ebs": {
                    "VolumeSize": int(x.get("size", 100)),
                    "VolumeType": get_type(x.get("type", "standard_ssd")),
                    "DeleteOnTermination": bool(x.get("delete_on_termination", True)),
                },
            }

            if x.get("type", "standard_ssd") in ["premium_ssd", "standard_ssd"]:
                dev["Ebs"]["Iops"] = int(x.get("iops", 3000))

            if (
                x.get("throughput", False)
                and x.get("type", "standard_ssd") == "standard_ssd"
            ):
                dev["Ebs"]["Throughput"] = x.get("throughput", 125)

            bdm.append(dev)

        # hardcoded value for root
        bdm[0]["DeviceName"] = "/dev/sda1"

        # logger.debug(f"Volumes: {bdm}")

        # tags
        tags = [{"Key": k, "Value": v} for k, v in group["tags"].items()]
        tags.append({"Key": "deployment_id", "Value": deployment_id})
        tags.append({"Key": "ansible_user", "Value": group["user"]})
        tags.append({"Key": "cluster_name", "Value": cluster_name})
        tags.append({"Key": "group_name", "Value": group["group_name"]})
        tags.append(
            {
                "Key": "inventory_groups",
                "Value": json.dumps(group["inventory_groups"] + [cluster_name]),
            }
        )
        tags.append(
            {"Key": "extra_vars", "Value": json.dumps(group.get("extra_vars", {}))}
        )

        if group.get("role", None):
            role = {"Name": group["role"]}
        else:
            role = {}

        # get latest AMI
        arch = group.get("instance", {}).get("arch", "amd64")

        image_id = boto3.client("ssm", region_name=group["region"]).get_parameter(
            Name=f"/aws/service{group['image']}/stable/current/{arch}/hvm/ebs-gp3/ami-id"
        )["Parameter"]["Value"]

        # logger.debug(f"Arch: {arch}, AMI: {image_id}")

        ec2 = boto3.client("ec2", region_name=group["region"])

        response = ec2.run_instances(
            DryRun=False,
            BlockDeviceMappings=bdm,
            ImageId=image_id,
            InstanceType=get_instance_type(group),
            KeyName=group["public_key_id"],
            MaxCount=1,
            MinCount=1,
            UserData=group.get("user_data", ""),
            IamInstanceProfile=role,
            NetworkInterfaces=[
                {
                    "Groups": group["security_groups"],
                    "DeviceIndex": 0,
                    "SubnetId": group["subnet"],
                    "AssociatePublicIpAddress": group["public_ip"],
                }
            ],
            TagSpecifications=[
                {
                    "ResourceType": "instance",
                    "Tags": tags,
                },
            ],
        )

        # wait until instance is running
        waiter = ec2.get_waiter("instance_running")
        waiter.wait(InstanceIds=[response["Instances"][0]["InstanceId"]])

        allocation = ec2.allocate_address(Domain="vpc")
        resp = ec2.associate_address(
            AllocationId=allocation["AllocationId"],
            InstanceId=response["Instances"][0]["InstanceId"],
        )

        # fetch details about the newly created instance
        response = ec2.describe_instances(
            InstanceIds=[response["Instances"][0]["InstanceId"]]
        )

        # add the instance to the list
        update_new_deployment(parse_aws_query(response))
    except Exception as e:
        update_errors(e)


def provision_gcp_vm(deployment_id: str, cluster_name: str, group: dict, x: int):
    logger.info("++gcp %s %s %s" % (cluster_name, group["group_name"], x))

    gcp_project = os.getenv("GCP_PROJECT")
    if not gcp_project:
        raise ValueError("GCP_PROJECT env var is not defined")

    gcpzone = "-".join([group["region"], group["zone"]])

    instance_name = deployment_id + "-" + str(random.randint(0, 1e16)).zfill(16)

    instance_client = InstancesClient()
    addresses_client = AddressesClient()

    try:
        op = addresses_client.insert(
            project=gcp_project,
            region=group["region"],
            address_resource=Address(
                name=f"{instance_name}-eip",
            ),
        )
        wait_for_extended_operation(op)

        # Get the reserved IP address
        reserved = addresses_client.get(
            project=gcp_project,
            region=group["region"],
            address=f"{instance_name}-eip",
        )
        reserved_ip = reserved.address

        logger.info(
            f"GCP External IP address reserved successfully: {instance_name}-eip"
        )

        # volumes
        def get_type(x):
            return {
                "standard_ssd": "pd-ssd",
                "premium_ssd": "pd-extreme",
                "local_ssd": "local-ssd",
                "standard_hdd": "pd-standard",
                "premium_hdd": "pd-standard",
            }.get(x, "pd-ssd")

        vols = []

        boot_disk = AttachedDisk()
        boot_disk.boot = True
        initialize_params = AttachedDiskInitializeParams()
        initialize_params.source_image = group["image"]
        initialize_params.disk_size_gb = int(group["volumes"]["os"].get("size", 30))
        initialize_params.disk_type = "zones/%s/diskTypes/%s" % (
            gcpzone,
            get_type(group["volumes"]["os"].get("type", "standard_ssd")),
        )
        boot_disk.initialize_params = initialize_params
        boot_disk.auto_delete = group["volumes"]["os"].get(
            "delete_on_termination", True
        )
        vols.append(boot_disk)

        for i, x in enumerate(group["volumes"]["data"]):
            disk = AttachedDisk()
            init_params = AttachedDiskInitializeParams()
            init_params.disk_size_gb = int(x.get("size", 100))
            disk.device_name = f"disk-{i}"

            # local-ssd peculiarities
            if get_type(x.get("type", "standard_ssd")) == "local-ssd":
                disk.type_ = "SCRATCH"
                disk.interface = "NVME"
                del init_params.disk_size_gb
                disk.device_name = f"local-ssd-{i}"

            init_params.disk_type = "zones/%s/diskTypes/%s" % (
                gcpzone,
                get_type(x.get("type", "standard_ssd")),
            )

            disk.initialize_params = init_params
            disk.auto_delete = x.get("delete_on_termination", True)

            vols.append(disk)

        # tags
        tags = Metadata()
        item = Items()
        l = []

        for k, v in group.get("tags", {}).items():
            item = Items()
            item.key = k
            item.value = v
            l.append(item)

        item = Items()
        item.key = "ansible_user"
        item.value = group["user"]
        l.append(item)

        item = Items()
        item.key = "cluster_name"
        item.value = cluster_name
        l.append(item)

        item = Items()
        item.key = "group_name"
        item.value = group["group_name"]
        l.append(item)

        item = Items()
        item.key = "inventory_groups"
        item.value = json.dumps(group["inventory_groups"] + [cluster_name])
        l.append(item)

        item = Items()
        item.key = "extra_vars"
        item.value = json.dumps(group.get("extra_vars", {}))
        l.append(item)

        tags.items = l

        # Use the network interface provided in the network_link argument.
        network_interface = NetworkInterface()
        network_interface.name = group["subnet"]

        if group["public_ip"]:
            access = AccessConfig()
            access.type_ = AccessConfig.Type.ONE_TO_ONE_NAT.name
            access.name = "External NAT"
            access.network_tier = access.NetworkTier.PREMIUM.name
            access.nat_i_p = reserved_ip
            network_interface.access_configs = [access]

        # Collect information into the Instance object.
        instance = Instance()
        instance.name = instance_name
        instance.disks = vols
        instance.machine_type = (
            f"zones/{gcpzone}/machineTypes/{get_instance_type(group)}"
        )
        instance.metadata = tags
        instance.labels = {"deployment_id": deployment_id}

        t = Tags()
        t.items = group["security_groups"]
        instance.tags = t

        instance.network_interfaces = [network_interface]

        operation = instance_client.insert(
            instance_resource=instance, project=gcp_project, zone=gcpzone
        )

        wait_for_extended_operation(operation)

        logger.debug(f"GCP instance created: {instance.name}")

        # fetch details
        instance = instance_client.get(
            project=gcp_project, zone=gcpzone, instance=instance_name
        )

        # add the instance to the list
        update_new_deployment(
            [parse_gcp_query(instance, group["region"], group["zone"])]
        )

    except Exception as e:
        update_errors(e)


def provision_azure_vm(
    deployment_id: str,
    cluster_name: str,
    group: dict,
    x: int,
    azure_subscription_id,
    azure_resource_group,
):
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
        update_errors(e)
