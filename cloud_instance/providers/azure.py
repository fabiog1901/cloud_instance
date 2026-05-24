import json
import logging
import os
import random

from azure.identity import EnvironmentCredential
from azure.mgmt.compute import ComputeManagementClient

from ..models import CloudInstance, Group

logger = logging.getLogger("cloud_instance")


def parse_instance(vm, private_ip, public_ip, public_hostname) -> list[CloudInstance]:
    return [
        CloudInstance(
            id=vm.name,
            cloud="azure",
            region=vm.location,
            zone="default",
            public_ip=public_ip,
            public_hostname=public_hostname,
            private_ip=private_ip,
            private_hostname=vm.name + ".internal.cloudapp.net",
            ansible_user=vm.tags["ansible_user"],
            inventory_groups=json.loads(vm.tags["inventory_groups"]),
            cluster_name=vm.tags["cluster_name"],
            group_name=vm.tags["group_name"],
            extra_vars=vm.tags["extra_vars"],
        )
    ]


def provision_vm(
    deployment_id: str,
    cluster_name: str,
    group: Group,
    x: int,
    get_instance_type,
    update_new_deployment,
    update_errors,
    azure_subscription_id,
    azure_resource_group,
):
    logger.debug("++azure %s %s %s" % (cluster_name, group.group_name, x))

    try:
        credential = EnvironmentCredential()
        client = ComputeManagementClient(credential, azure_subscription_id)

        instance_name = deployment_id + "-" + str(random.randint(0, 10**16)).zfill(16)

        def get_type(x):
            return {
                "standard_ssd": "Premium_LRS",
                "premium_ssd": "PremiumV2_LRS",
                "local_ssd": "Premium_LRS",
                "standard_hdd": "Standard_LRS",
                "premium_hdd": "Standard_LRS",
            }.get(x, "Premium_LRS")

        vols = []

        for i, x in enumerate(group.volumes.data):
            poller = client.disks.begin_create_or_update(
                azure_resource_group,
                instance_name + "-disk-" + str(i),
                {
                    "location": group.region,
                    "sku": {"name": get_type((x.type or "standard_ssd"))},
                    "disk_size_gb": int((x.size or 100)),
                    "creation_data": {"create_option": "Empty"},
                },
            )

            data_disk = poller.result()

            disk = {
                "lun": i,
                "name": instance_name + "-disk-" + str(i),
                "create_option": "Attach",
                "delete_option": (
                    "Delete" if (x.delete_on_termination if x.delete_on_termination is not None else True) else "Detach"
                ),
                "managed_disk": {"id": data_disk.id},
            }
            vols.append(disk)

        publisher, offer, sku, version = group.image.split(":")

        nsg = None
        if group.security_groups:
            nsg = {
                "id": "/subscriptions/%s/resourceGroups/%s/providers/Microsoft.Network/networkSecurityGroups/%s"
                % (
                    azure_subscription_id,
                    azure_resource_group,
                    group.security_groups[0],
                )
            }

        client.virtual_machines.begin_create_or_update(
            azure_resource_group,
            instance_name,
            {
                "location": group.region,
                "tags": {
                    "deployment_id": deployment_id,
                    "ansible_user": group.user,
                    "cluster_name": cluster_name,
                    "group_name": group.group_name,
                    "inventory_groups": json.dumps(
                        group.inventory_groups + [cluster_name]
                    ),
                    "extra_vars": json.dumps(group.extra_vars),
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
                    "admin_username": group.user,
                    "linux_configuration": {
                        "ssh": {
                            "public_keys": [
                                {
                                    "path": "/home/%s/.ssh/authorized_keys"
                                    % group.user,
                                    "key_data": group.public_key_id,
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
                                            group.vpc_id,
                                            group.subnet,
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
        ).result()

    except Exception as e:
        update_errors(e)


def terminate_vm(instance: CloudInstance, update_errors):
    logger.debug(f"--azure {instance.id}")

    azure_subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID")
    azure_resource_group = os.getenv("AZURE_RESOURCE_GROUP")

    try:
        credential = EnvironmentCredential()

        client = ComputeManagementClient(credential, azure_subscription_id)

        async_vm_delete = client.virtual_machines.begin_delete(
            azure_resource_group, instance.id
        )
        async_vm_delete.wait()

    except Exception as e:
        update_errors(e)


def modify_vm(instance: CloudInstance, new_cpus_count, get_instance_type, update_errors):
    update_errors("Azure instance type modification is not implemented")


def resize_vm(instance: CloudInstance, new_disk_size, update_errors):
    update_errors("Azure disk resize is not implemented")
