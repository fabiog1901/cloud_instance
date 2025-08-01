import json

from google.cloud.compute_v1.types import Instance


def parse_aws_query(ec2_response: dict):
    instances: list[dict] = []

    for x in ec2_response["Reservations"]:
        for i in x["Instances"]:
            tags = {}
            for t in i["Tags"]:
                tags[t["Key"]] = t["Value"]

            instances.append(
                {
                    # cloud instance id, useful for deleting
                    "id": i["InstanceId"],
                    # locality
                    "cloud": "aws",
                    "region": i["Placement"]["AvailabilityZone"][:-1],
                    "zone": i["Placement"]["AvailabilityZone"][-1],
                    # addresses
                    "public_ip": i["PublicIpAddress"],
                    "public_hostname": i["PublicDnsName"],
                    "private_ip": i["PrivateIpAddress"],
                    "private_hostname": i["PrivateDnsName"],
                    # tags
                    "ansible_user": tags["ansible_user"],
                    "inventory_groups": json.loads(tags["inventory_groups"]),
                    "cluster_name": tags["cluster_name"],
                    "group_name": tags["group_name"],
                    "extra_vars": tags["extra_vars"],
                }
            )
    return instances


def parse_gcp_query(
    instance: Instance,
    region,
    zone,
):
    tags = {}
    for x in instance.metadata.items:
        tags[x.key] = x.value

    ip = instance.network_interfaces[0].access_configs[0].nat_i_p.split(".")
    public_dns = ".".join([ip[3], ip[2], ip[1], ip[0], "bc.googleusercontent.com"])

    return {
        # cloud instance id, useful for deleting
        "id": instance.name,
        # locality
        "cloud": "gcp",
        "region": region,
        "zone": zone,
        # addresses
        "public_ip": instance.network_interfaces[0].access_configs[0].nat_i_p,
        "public_hostname": public_dns,
        "private_ip": instance.network_interfaces[0].network_i_p,
        "private_hostname": f"{instance.name}.c.cea-team.internal",
        # tags
        "ansible_user": tags["ansible_user"],
        "inventory_groups": json.loads(tags["inventory_groups"]),
        "cluster_name": tags["cluster_name"],
        "group_name": tags["group_name"],
        "extra_vars": tags["extra_vars"],
    }


def parse_azure_query(vm, private_ip, public_ip, public_hostname):
    return [
        {
            # cloud instance id, useful for deleting
            "id": vm.name,
            # locality
            "cloud": "azure",
            "region": vm.location,
            "zone": "default",
            # addresses
            "public_ip": public_ip,
            "public_hostname": public_hostname,
            "private_ip": private_ip,
            "private_hostname": vm.name + ".internal.cloudapp.net",
            # tags
            "ansible_user": vm.tags["ansible_user"],
            "inventory_groups": json.loads(vm.tags["inventory_groups"]),
            "cluster_name": vm.tags["cluster_name"],
            "group_name": vm.tags["group_name"],
            "extra_vars": vm.tags["extra_vars"],
        }
    ]
