import ipaddress
import json
import logging
import time
from threading import Thread

import boto3
from botocore.config import Config
from botocore.exceptions import ConnectTimeoutError, ReadTimeoutError, SSLError

from ..models import IPAddressType

logger = logging.getLogger("cloud_instance")


def first_ipv6_address(instance: dict):
    for interface in instance.get("NetworkInterfaces", []):
        for address in interface.get("Ipv6Addresses", []):
            if address.get("Ipv6Address"):
                return address["Ipv6Address"]
    return None


def parse_instances(ec2_response: dict):
    instances: list[dict] = []

    for x in ec2_response["Reservations"]:
        for i in x["Instances"]:
            tags = {}
            for t in i["Tags"]:
                tags[t["Key"]] = t["Value"]

            public_ipv4 = i.get("PublicIpAddress")
            public_ipv6 = first_ipv6_address(i)

            instances.append(
                {
                    "id": i["InstanceId"],
                    "cloud": "aws",
                    "region": i["Placement"]["AvailabilityZone"][:-1],
                    "zone": i["Placement"]["AvailabilityZone"][-1],
                    "public_ip": public_ipv4 or public_ipv6,
                    "public_ipv4": public_ipv4,
                    "public_ipv6": public_ipv6,
                    "public_hostname": i.get("PublicDnsName", ""),
                    "private_ip": i["PrivateIpAddress"],
                    "private_hostname": i["PrivateDnsName"],
                    "ansible_user": tags["ansible_user"],
                    "inventory_groups": json.loads(tags["inventory_groups"]),
                    "cluster_name": tags["cluster_name"],
                    "group_name": tags["group_name"],
                    "extra_vars": tags["extra_vars"],
                    "ip_address_type": tags.get(
                        "ip_address_type", IPAddressType.IPv4_EPHEMERAL.value
                    ),
                }
            )
    return instances


def fetch_instances(deployment_id: str, update_instances_list, update_errors):
    logger.debug(f"Fetching AWS instances for deployment_id = '{deployment_id}'")

    threads: list[Thread] = []

    def fetch_instances_per_region(region, deployment_id):
        logger.debug(f"Fetching AWS instances from {region}")

        try:
            ec2 = boto3.client(
                "ec2",
                region_name=region,
                config=Config(
                    connect_timeout=5,
                    read_timeout=5,
                    retries={"max_attempts": 0},
                ),
            )
            response = ec2.describe_instances(
                Filters=[
                    {
                        "Name": "instance-state-name",
                        "Values": ["pending", "running"],
                    },
                    {"Name": "tag:deployment_id", "Values": [deployment_id]},
                ]
            )

            aws_instances: list = parse_instances(response)

            if aws_instances:
                update_instances_list(aws_instances)

        except ConnectTimeoutError:
            logger.warning("EC2 connection timed out")
        except ReadTimeoutError:
            logger.warning("EC2 response timed out")
        except SSLError as e:
            if (
                "SSL validation failed" in str(e)
                and "UNEXPECTED_EOF_WHILE_READING" in str(e)
            ):
                logger.warning("EC2 SSL validation failed due to unexpected EOF")
            else:
                update_errors(e)
        except Exception as e:
            update_errors(e)

    try:
        ec2 = boto3.client("ec2", region_name="us-east-1")
        regions = [x["RegionName"] for x in ec2.describe_regions()["Regions"]]

        for region in regions:
            thread = Thread(
                target=fetch_instances_per_region,
                args=(region, deployment_id),
                daemon=True,
            )
            thread.start()
            threads.append(thread)

        for x in threads:
            x.join()

    except Exception as e:
        update_errors(e)


def provision_vm(
    deployment_id: str,
    cluster_name: str,
    group: dict,
    x: int,
    get_instance_type,
    update_new_deployment,
    update_errors,
):
    logger.debug("++aws %s %s %s" % (cluster_name, group["region"], x))
    allocation_id = None
    eip_associated = False
    ec2 = None

    def get_ip_address_type(x):
        try:
            return IPAddressType(
                x.get("ip_address_type", IPAddressType.IPv4_EPHEMERAL.value)
            )
        except ValueError:
            raise ValueError(f"Invalid ip_address_type: {x['ip_address_type']}") from None

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
        ip_address_type = get_ip_address_type(group)

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

        bdm[0]["DeviceName"] = "/dev/sda1"

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
        tags.append({"Key": "ip_address_type", "Value": ip_address_type.value})

        if group.get("role", None):
            role = {"Name": group["role"]}
        else:
            role = {}

        arch = group.get("instance", {}).get("arch", "amd64")

        image_id = boto3.client("ssm", region_name=group["region"]).get_parameter(
            Name=f"/aws/service{group['image']}/stable/current/{arch}/hvm/ebs-gp3/ami-id"
        )["Parameter"]["Value"]

        ec2 = boto3.client("ec2", region_name=group["region"])

        network_interface = {
            "Groups": group["security_groups"],
            "DeviceIndex": 0,
            "SubnetId": group["subnet"],
        }

        if group["public_ip"] and ip_address_type == IPAddressType.IPv6:
            network_interface["AssociatePublicIpAddress"] = False
            network_interface["Ipv6AddressCount"] = 1
        elif group["public_ip"] and ip_address_type == IPAddressType.IPv4_RESERVED:
            network_interface["AssociatePublicIpAddress"] = False
        else:
            network_interface["AssociatePublicIpAddress"] = group["public_ip"]

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
            NetworkInterfaces=[network_interface],
            TagSpecifications=[
                {
                    "ResourceType": "instance",
                    "Tags": tags,
                },
            ],
        )

        waiter = ec2.get_waiter("instance_running")
        waiter.wait(InstanceIds=[response["Instances"][0]["InstanceId"]])

        if group["public_ip"] and ip_address_type == IPAddressType.IPv4_RESERVED:
            allocation = ec2.allocate_address(
                Domain="vpc",
                TagSpecifications=[
                    {
                        "ResourceType": "elastic-ip",
                        "Tags": tags,
                    },
                ],
            )
            allocation_id = allocation["AllocationId"]
            ec2.associate_address(
                AllocationId=allocation_id,
                InstanceId=response["Instances"][0]["InstanceId"],
            )
            eip_associated = True

        response = ec2.describe_instances(
            InstanceIds=[response["Instances"][0]["InstanceId"]]
        )

        update_new_deployment(parse_instances(response))
    except Exception as e:
        if ec2 and allocation_id and not eip_associated:
            try:
                ec2.release_address(AllocationId=allocation_id)
            except Exception as release_error:
                logger.warning(release_error)
        update_errors(e)


def terminate_vm(instance: dict, update_errors):
    def get_allocation_id(instance_id):
        response = ec2.describe_addresses(
            Filters=[
                {"Name": "instance-id", "Values": [instance_id]},
                {
                    "Name": "tag:ip_address_type",
                    "Values": [IPAddressType.IPv4_RESERVED.value],
                },
            ]
        )

        for address in response["Addresses"]:
            if address.get("InstanceId") == instance_id:
                return address.get("AllocationId")

        return None

    def get_allocation_id_by_public_ip(public_ip, instance_id):
        try:
            response = ec2.describe_addresses(PublicIps=[public_ip])
        except Exception as e:
            logger.warning(e)
            return None

        for address in response["Addresses"]:
            if address.get("InstanceId") == instance_id:
                return address.get("AllocationId")

        return None

    def is_ipv4_address(address):
        try:
            return ipaddress.ip_address(address).version == 4
        except (TypeError, ValueError):
            return False

    logger.info(f"--aws {instance['id']}")

    try:
        ec2 = boto3.client("ec2", region_name=instance["region"])

        alloc = None
        if instance.get("ip_address_type") == IPAddressType.IPv4_RESERVED.value:
            alloc = get_allocation_id(instance["id"])
        elif is_ipv4_address(instance.get("public_ip")):
            alloc = get_allocation_id_by_public_ip(instance["public_ip"], instance["id"])

        response = ec2.terminate_instances(
            InstanceIds=[instance["id"]],
        )

        waiter = ec2.get_waiter("instance_terminated")
        waiter.wait(InstanceIds=[instance["id"]])

        status = response["TerminatingInstances"][0]["CurrentState"]["Name"]

        if status in ["shutting-down", "terminated"]:
            logger.info(f"Deleted AWS instance: {instance['id']}")
        else:
            logger.error(f"Unexpected response: {response}")
            update_errors(str(response))

        if alloc:
            ec2.release_address(AllocationId=alloc)

    except Exception as e:
        update_errors(str(e))


def modify_vm(instance: dict, new_cpus_count, get_instance_type, update_errors):
    instance_id = instance["id"]

    try:
        client = boto3.client("ec2", region_name=instance["region"])

        logger.info(f"Modifying {instance_id=} {new_cpus_count=}")

        client.stop_instances(InstanceIds=[instance_id])
        client.get_waiter("instance_stopped").wait(InstanceIds=[instance_id])

        logger.info(f"Stopped {instance_id}")

        new_instance_type = get_instance_type(
            {
                "cloud": instance["cloud"],
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

        client.start_instances(InstanceIds=[instance_id])
        client.get_waiter("instance_running").wait(InstanceIds=[instance_id])

        logger.info(f"Restarted {instance_id}")

    except Exception as e:
        update_errors(e)


def resize_vm(instance: dict, new_disk_size, update_errors):
    instance_id = instance["id"]

    client = boto3.client("ec2", region_name=instance["region"])

    def get_volume_id(instance_id: str) -> str:
        resp = client.describe_instances(InstanceIds=[instance_id])
        reservations = resp.get("Reservations", [])
        for r in reservations:
            for inst in r.get("Instances", []):
                for mapping in inst.get("BlockDeviceMappings", []):
                    if mapping["DeviceName"] != "/dev/sda1":
                        return mapping["Ebs"]["VolumeId"]

    def wait_for_resize(volume_id: str, timeout_s: int = 900):
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
        vol = boto3.client("ec2", region_name=instance["region"]).describe_volumes(
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
