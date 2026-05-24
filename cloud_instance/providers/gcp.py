import json
import logging
import os
import random

from google.cloud.compute_v1 import (
    AccessConfig,
    AggregatedListInstancesRequest,
    AddressesClient,
    AttachedDisk,
    AttachedDiskInitializeParams,
    DisksClient,
    DisksResizeRequest,
    Instance,
    InstancesClient,
    InstancesSetMachineTypeRequest,
    NetworkInterface,
    Tags,
)
from google.cloud.compute_v1.services.addresses.client import AddressesClient
from google.cloud.compute_v1.types import Address, Items, Metadata

from ..models import CloudInstance, Group, IPAddressType, InstanceSpec

logger = logging.getLogger("cloud_instance")


def wait_for_extended_operation(op):
    result = op.result(timeout=300)

    if op.error_code:
        logger.error(f"GCP Error: {op.error_code}: {op.error_message}")
        raise ValueError(f"GCP Error: {op.error_code}: {op.error_message}")

    return result


def parse_instance(instance: Instance, region, zone) -> CloudInstance:
    tags = {}
    for x in instance.metadata.items:
        tags[x.key] = x.value

    ip = instance.network_interfaces[0].access_configs[0].nat_i_p.split(".")
    public_dns = ".".join([ip[3], ip[2], ip[1], ip[0], "bc.googleusercontent.com"])

    return CloudInstance(
        id=instance.name,
        cloud="gcp",
        region=region,
        zone=zone,
        public_ip=instance.network_interfaces[0].access_configs[0].nat_i_p,
        public_hostname=public_dns,
        private_ip=instance.network_interfaces[0].network_i_p,
        private_hostname=f"{instance.name}.c.cea-team.internal",
        ansible_user=tags["ansible_user"],
        inventory_groups=json.loads(tags["inventory_groups"]),
        cluster_name=tags["cluster_name"],
        group_name=tags["group_name"],
        extra_vars=tags["extra_vars"],
    )


def fetch_instances(deployment_id: str, update_instances_list, update_errors):
    logger.debug(f"Fetching GCP instances for deployment_id = '{deployment_id}'")

    gcp_project = os.getenv("GCP_PROJECT")
    if not gcp_project:
        update_errors("Env var GCP_PROJECT is not set")
        return

    try:
        instance_client = InstancesClient()
        request = AggregatedListInstancesRequest(
            project=gcp_project,
            max_results=5,
            filter=f"labels.deployment_id:{deployment_id}",
        )

        agg_list = instance_client.aggregated_list(request=request)
        instances: list[CloudInstance] = []

        for zone, response in agg_list:
            if response.instances:
                for x in response.instances:
                    if x.status in ("PROVISIONING", "STAGING", "RUNNING"):
                        instances.append(parse_instance(x, zone[6:-2], zone[-1]))

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
    ip_address_type: IPAddressType = IPAddressType.IPv4_EPHEMERAL,
):
    logger.info("++gcp %s %s %s" % (cluster_name, group.group_name, x))

    try:
        gcp_project = os.getenv("GCP_PROJECT")
        if not gcp_project:
            raise ValueError("GCP_PROJECT env var is not defined")

        gcpzone = "-".join([group.region, group.zone])

        instance_name = deployment_id + "-" + str(random.randint(0, 10**16)).zfill(16)

        instance_client = InstancesClient()

        if ip_address_type == IPAddressType.IPv4_RESERVED:
            addresses_client = AddressesClient()

            op = addresses_client.insert(
                project=gcp_project,
                region=group.region,
                address_resource=Address(
                    name=f"{instance_name}-eip",
                ),
            )
            wait_for_extended_operation(op)

            reserved = addresses_client.get(
                project=gcp_project,
                region=group.region,
                address=f"{instance_name}-eip",
            )
            reserved_ip = reserved.address

            logger.info(
                f"GCP External IP address reserved successfully: {instance_name}-eip"
            )

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
        initialize_params.source_image = group.image
        initialize_params.disk_size_gb = int((group.volumes.os.size or 30))
        initialize_params.disk_type = "zones/%s/diskTypes/%s" % (
            gcpzone,
            get_type((group.volumes.os.type or "standard_ssd")),
        )
        boot_disk.initialize_params = initialize_params
        boot_disk.auto_delete = (group.volumes.os.delete_on_termination if group.volumes.os.delete_on_termination is not None else True)
        vols.append(boot_disk)

        for i, x in enumerate(group.volumes.data):
            disk = AttachedDisk()
            init_params = AttachedDiskInitializeParams()
            init_params.disk_size_gb = int((x.size or 100))
            disk.device_name = f"disk-{i}"

            if get_type((x.type or "standard_ssd")) == "local-ssd":
                disk.type_ = "SCRATCH"
                disk.interface = "NVME"
                del init_params.disk_size_gb
                disk.device_name = f"local-ssd-{i}"

            init_params.disk_type = "zones/%s/diskTypes/%s" % (
                gcpzone,
                get_type((x.type or "standard_ssd")),
            )

            disk.initialize_params = init_params
            disk.auto_delete = (x.delete_on_termination if x.delete_on_termination is not None else True)

            vols.append(disk)

        tags = Metadata()
        l = []

        for k, v in group.tags.items():
            item = Items()
            item.key = k
            item.value = v
            l.append(item)

        item = Items()
        item.key = "ansible_user"
        item.value = group.user
        l.append(item)

        item = Items()
        item.key = "cluster_name"
        item.value = cluster_name
        l.append(item)

        item = Items()
        item.key = "group_name"
        item.value = group.group_name
        l.append(item)

        item = Items()
        item.key = "inventory_groups"
        item.value = json.dumps(group.inventory_groups + [cluster_name])
        l.append(item)

        item = Items()
        item.key = "extra_vars"
        item.value = json.dumps(group.extra_vars)
        l.append(item)

        tags.items = l

        network_interface = NetworkInterface()
        network_interface.name = group.subnet

        if group.public_ip:
            access = AccessConfig()
            access.type_ = AccessConfig.Type.ONE_TO_ONE_NAT.name
            access.name = "External NAT"
            access.network_tier = access.NetworkTier.PREMIUM.name

            if ip_address_type == IPAddressType.IPv4_RESERVED:
                access.nat_i_p = reserved_ip

            network_interface.access_configs = [access]

        instance = Instance()
        instance.name = instance_name
        instance.disks = vols
        instance.machine_type = (
            f"zones/{gcpzone}/machineTypes/{get_instance_type(group)}"
        )
        instance.metadata = tags
        instance.labels = {"deployment_id": deployment_id}

        t = Tags()
        t.items = group.security_groups
        instance.tags = t

        instance.network_interfaces = [network_interface]

        op = instance_client.insert(
            instance_resource=instance, project=gcp_project, zone=gcpzone
        )

        wait_for_extended_operation(op)

        logger.debug(f"GCP instance created: {instance.name}")

        instance = instance_client.get(
            project=gcp_project, zone=gcpzone, instance=instance_name
        )

        update_new_deployment([parse_instance(instance, group.region, group.zone)])

    except Exception as e:
        update_errors(e)


def terminate_vm(instance: CloudInstance, update_errors):
    logger.debug(f"--gcp {instance.id}")

    gcp_project = os.getenv("GCP_PROJECT")
    if not gcp_project:
        raise ValueError("Env var GCP_PROJECT not set.")

    try:
        instance_client = InstancesClient()

        instance_client.delete(
            project=gcp_project,
            zone=f"{instance.region}-{instance.zone}",
            instance=instance.id,
        )
        logger.info(f"Deleting GCP instance: {instance}")

        client = AddressesClient()
        client.delete(
            project=gcp_project,
            region=instance.region,
            address=f"{instance.id}-eip",
        )

        logger.info(f"GCP External IP address {instance.id} released successfully.")

    except Exception as e:
        update_errors(e)


def modify_vm(instance: CloudInstance, new_cpus_count: int, get_instance_type, update_errors):
    instance_id = instance.id

    gcp_project = os.getenv("GCP_PROJECT")
    if not gcp_project:
        update_errors("GCP_PROJECT env var is not defined")
        return

    gcpzone = f"{instance.region}-{instance.zone}"

    try:
        client = InstancesClient()

        logger.info(f"Modifying {instance_id=} {new_cpus_count=}")

        op = client.stop(project=gcp_project, zone=gcpzone, instance=instance_id)
        wait_for_extended_operation(op)
        logger.info(f"Stopped {instance_id}")

        new_instance_type = get_instance_type(
            Group(cloud=instance.cloud, instance=InstanceSpec(cpu=new_cpus_count))
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

        op = client.start(project=gcp_project, zone=gcpzone, instance=instance_id)
        wait_for_extended_operation(op)
        logger.info(f"Restarted {instance_id}")

    except Exception as e:
        update_errors(e)


def resize_vm(instance: CloudInstance, new_disk_size: int, update_errors):
    instance_id = instance.id

    gcp_project = os.getenv("GCP_PROJECT")
    if not gcp_project:
        update_errors("GCP_PROJECT env var is not defined")
        return

    gcpzone = f"{instance.region}-{instance.zone}"

    try:
        client = InstancesClient()
        instance_resource = client.get(
            project=gcp_project,
            zone=gcpzone,
            instance=instance_id,
        )

        disk_client = DisksClient()

        for disk in instance_resource.disks:
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
