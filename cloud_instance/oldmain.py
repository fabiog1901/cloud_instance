#!/usr/bin/python

import argparse
import json
import logging
import os
import random
import threading

# AWS
import boto3

# GCP
import google.cloud.compute_v1
import google.cloud.compute_v1.types

# AZURE
from azure.identity import EnvironmentCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.network import NetworkManagementClient
from google.api_core.extended_operation import ExtendedOperation

# setup global logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# create console handler and set level to debug
ch = logging.FileHandler(filename="/tmp/cloud_instance.log")
ch.setLevel(logging.INFO)

# create formatter
formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] (%(threadName)s) %(lineno)d %(message)s"
)

# add formatter to ch
ch.setFormatter(formatter)

# add ch to logger
logger.addHandler(ch)


class CloudInstance:
    def __init__(
        self,
        deployment_id: str,
        present: bool,
        deployment: list,
        defaults: dict,
        preserve_existing_vms: bool = False,
        return_tobedeleted_vms: bool = False,
        gather_current_deployment_only: bool = False,
    ):
        self.deployment_id = deployment_id
        self.present = present
        self.deployment = deployment
        self.defaults = defaults
        self.preserve_existing_vms = preserve_existing_vms
        self.return_tobedeleted_vms = return_tobedeleted_vms
        self.gather_current_deployment_only = gather_current_deployment_only

        self.threads: list[threading.Thread] = []
        self._lock = threading.Lock()

        self.changed: bool = False

        self.gcp_project = os.environ.get("GCP_PROJECT", None)
        self.azure_resource_group = os.environ.get("AZURE_RESOURCE_GROUP", None)
        self.azure_subscription_id = os.environ["AZURE_SUBSCRIPTION_ID"]

        self.new_instances = []
        self.instances = []
        self.errors: list = []

    def fetch_all(
        self, deployment_id: str, gcp_project: str, azure_resource_group: str
    ):
        """For each public cloud, fetch all instances
        with the given deployment_id and return a clean list of instances

        Args:
            deployment_id (str): the value of the tag deployment_id

        Return:
            list[dict]: the list of instances across all clouds
        """
        # AWS
        thread = threading.Thread(
            target=self.fetch_aws_instances, args=(self.deployment_id,)
        )
        thread.start()
        self.threads.append(thread)

        # GCP
        if gcp_project:
            thread = threading.Thread(
                target=self.fetch_gcp_instances,
                args=(self.deployment_id, self.gcp_project),
            )
            thread.start()
            self.threads.append(thread)

        # AZURE
        # if azure_resource_group:
        #     thread = threading.Thread(
        #         target=self.fetch_azure_instances, args=(self.deployment_id,)
        #     )
        #     thread.start()
        #     self.threads.append(thread)

        # wait for all threads to complete
        for x in self.threads:
            x.join()
        
        self.threads = []
            
        # sort self.instances to ensure list is deterministic
        self.instances = sorted(self.instances, key=lambda d: d['id'])

    def parse_aws_query(self, response):
        instances: list = []

        try:
            for x in response["Reservations"]:
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
        except Exception as e:
            logger.error(e)
            return []

        return instances

    def parse_gcp_query(
        self,
        instance: google.cloud.compute_v1.types.compute.Instance,
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

    def parse_azure_query(self, vm, private_ip, public_ip, public_hostname):
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

    def fetch_aws_instances(self, deployment_id: str):
        logger.debug(f"Fetching AWS instances for deployment_id = '{deployment_id}'")

        threads: list[threading.Thread] = []

        def fetch_aws_instances_per_region(region, deployment_id):
            logger.debug(f"Fetching AWS instances from {region}")

            try:
                ec2 = boto3.client("ec2", region_name=region)
                response = ec2.describe_instances(
                    Filters=[
                        {
                            "Name": "instance-state-name",
                            "Values": ["pending", "running"],
                        },
                        {"Name": "tag:deployment_id", "Values": [deployment_id]},
                    ]
                )

                instances: list = self.parse_aws_query(response)
            except Exception as e:
                self.log_error(e)

            if instances:
                self.update_current_deployment(instances)

        try:
            ec2 = boto3.client("ec2", region_name="us-east-1")
            regions = [x["RegionName"] for x in ec2.describe_regions()["Regions"]]

            for region in regions:
                thread = threading.Thread(
                    target=fetch_aws_instances_per_region,
                    args=(region, deployment_id),
                    daemon=True,
                )
                thread.start()
                threads.append(thread)

            for x in threads:
                x.join()
        except Exception as e:
            self.log_error(
                {
                    "method": "fetch_aws_instances",
                    "error_type": str(type(e)),
                    "msg": str(e.args),
                }
            )

    def fetch_gcp_instances(self, deployment_id: str, project_id: str):
        """
        Return a dictionary of all instances present in a project, grouped by their zone.

        Args:
            project_id: project ID or project number of the Cloud project you want to use.
        Returns:
            A dictionary with zone names as keys (in form of "zones/{zone_name}") and
            iterable collections of Instance objects as values.
        """
        logger.debug(f"Fetching GCP instances for deployment_id = '{deployment_id}'")

        instance_client = google.cloud.compute_v1.InstancesClient()
        # Use the `max_results` parameter to limit the number of results that the API returns per response page.
        request = google.cloud.compute_v1.AggregatedListInstancesRequest(
            project=project_id,
            max_results=5,
            filter=f"labels.deployment_id:{deployment_id}",
        )

        agg_list = instance_client.aggregated_list(request=request)
        instances = []

        # Despite using the `max_results` parameter, you don't need to handle the pagination
        # yourself. The returned `AggregatedListPager` object handles pagination
        # automatically, returning separated pages as you iterate over the results.
        for zone, response in agg_list:
            if response.instances:
                for x in response.instances:
                    if x.status in ("PROVISIONING", "STAGING", "RUNNING"):
                        instances.append(self.parse_gcp_query(x, zone[6:-2], zone[-1]))
        if instances:
            self.update_current_deployment(instances)

    def fetch_azure_instance_network_config(self, vm):
        try:
            credential = EnvironmentCredential()

            client = ComputeManagementClient(credential, self.azure_subscription_id)
            netclient = NetworkManagementClient(credential, self.azure_subscription_id)

            # check VM is in running state
            statuses = client.virtual_machines.instance_view(
                self.azure_resource_group, vm.name
            ).statuses

            status = len(statuses) >= 2 and statuses[1]

            if status and status.code == "PowerState/running":
                nic_id = vm.network_profile.network_interfaces[0].id
                nic = netclient.network_interfaces.get(
                    self.azure_resource_group, nic_id.split("/")[-1]
                )

                private_ip = nic.ip_configurations[0].private_ip_address
                pip = netclient.public_ip_addresses.get(
                    self.azure_resource_group,
                    nic.ip_configurations[0].public_ip_address.id.split("/")[-1],
                )

                public_ip = pip.ip_address
                public_hostname = ""

            return private_ip, public_ip, public_hostname

        except Exception as e:
            logger.error(e)
            self.log_error(e)

    def get_azure_instance_details(self, vm):
        self.update_current_deployment(
            self.parse_azure_query(vm, *self.fetch_azure_instance_network_config(vm))
        )

    def fetch_azure_instances(self, deployment_id: str):
        logger.debug(f"Fetching Azure instances for deployment_id = '{deployment_id}'")

        threads: list[threading.Thread] = []

        try:
            # Acquire a credential object.
            credential = EnvironmentCredential()

        except Exception as e:
            logger.warning(e)
            return

        client = ComputeManagementClient(credential, self.azure_subscription_id)

        vm_list = client.virtual_machines.list(self.azure_resource_group)
        for vm in vm_list:
            if vm.tags.get("deployment_id", "") == deployment_id:
                thread = threading.Thread(
                    target=self.get_azure_instance_details, args=(vm,), daemon=True
                )
                thread.start()
                threads.append(thread)

        for x in threads:
            x.join()

    def update_current_deployment(self, instances: list):
        with self._lock:
            logger.debug("Updating pre-existing instances list")
            self.instances += instances

    def update_new_deployment(self, instances: list):
        with self._lock:
            logger.debug("Updating new instances list")
            self.new_instances += instances

    def log_error(self, error: str):
        with self._lock:
            logger.debug("Updating errors list: ", error)
            self.errors.append(str(error))

    def build_deployment(self):
        # 4. loop through the 'deployment' struct
        #    - through each cluster and copies
        #    - through each group within each cluster

        # loop through each cluster item in the deployment list
        for cluster in self.deployment:
            # extract the cluster name for all copies,
            # then, for each requested copy, add the index suffix
            cluster_name: str = cluster.get("cluster_name", self.deployment_id)
            for x in range(int(cluster.get("copies", 1))):
                self.build_cluster(f"{cluster_name}-{x}", cluster)

    def build_cluster(self, cluster_name: str, cluster: dict):
        # for each group in the cluster,
        # put all cluster defaults into the group
        for group in cluster.get("groups", []):
            self.build_group(cluster_name, self.merge_dicts(cluster, group))

    def build_group(self, cluster_name, group: dict):
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
        for x in self.instances[:]:
            if (
                x["cluster_name"] == cluster_name
                and x["group_name"] == group["group_name"]
                and x["region"] == group["region"]
                and x["zone"] == group["zone"]
            ):
                current_group.append(x)
                self.instances.remove(x)

        current_count = len(current_group)
        new_exact_count = int(group.get("exact_count", 0))

        # CASE 1
        if current_count == new_exact_count:
            pass

        # CASE 2: ADD instances
        elif current_count < new_exact_count:
            self.changed = True
            target = {
                "aws": self.provision_aws_vm,
                "gcp": self.provision_gcp_vm,
                "azure": self.provision_azure_vm,
            }

            for x in range(new_exact_count - current_count):
                thread = threading.Thread(
                    target=target[group["cloud"]], args=(cluster_name, group, x)
                )
                #thread.start()
                self.threads.append(thread)

        # CASE 3: REMOVE instances
        else:
            self.changed = True
            for x in range(current_count - new_exact_count):
                self.instances.append(current_group.pop(-1))

        self.update_new_deployment(current_group)

    def provision_aws_vm(self, cluster_name: str, group: dict, x: int):
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
                        "DeleteOnTermination": bool(
                            x.get("delete_on_termination", True)
                        ),
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
            tags.append({"Key": "deployment_id", "Value": self.deployment_id})
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
                InstanceType=self.get_instance_type(group),
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
            
            allocation = ec2.allocate_address(Domain='vpc')
            resp = ec2.associate_address(AllocationId=allocation['AllocationId'],
                                                InstanceId=response["Instances"][0]["InstanceId"])
            
            # fetch details about the newly created instance
            response = ec2.describe_instances(
                InstanceIds=[response["Instances"][0]["InstanceId"]]
            )

            # add the instance to the list
            self.update_new_deployment(self.parse_aws_query(response))
        except Exception as e:
            logger.error(e)
            self.log_error(e)

    def provision_gcp_vm(self, cluster_name: str, group: dict, x: int):
        logger.debug("++gcp %s %s %s" % (cluster_name, group["group_name"], x))

        gcpzone = "-".join([group["region"], group["zone"]])

        instance_name = (
            self.deployment_id + "-" + str(random.randint(0, 1e16)).zfill(16)
        )

        instance_client = google.cloud.compute_v1.InstancesClient()

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

        boot_disk = google.cloud.compute_v1.AttachedDisk()
        boot_disk.boot = True
        initialize_params = google.cloud.compute_v1.AttachedDiskInitializeParams()
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
            disk = google.cloud.compute_v1.AttachedDisk()
            init_params = google.cloud.compute_v1.AttachedDiskInitializeParams()
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
        tags = google.cloud.compute_v1.types.Metadata()
        item = google.cloud.compute_v1.types.Items()
        l = []

        for k, v in group.get("tags", {}).items():
            item = google.cloud.compute_v1.types.Items()
            item.key = k
            item.value = v
            l.append(item)

        item = google.cloud.compute_v1.types.Items()
        item.key = "ansible_user"
        item.value = group["user"]
        l.append(item)

        item = google.cloud.compute_v1.types.Items()
        item.key = "cluster_name"
        item.value = cluster_name
        l.append(item)

        item = google.cloud.compute_v1.types.Items()
        item.key = "group_name"
        item.value = group["group_name"]
        l.append(item)

        item = google.cloud.compute_v1.types.Items()
        item.key = "inventory_groups"
        item.value = json.dumps(group["inventory_groups"] + [cluster_name])
        l.append(item)

        item = google.cloud.compute_v1.types.Items()
        item.key = "extra_vars"
        item.value = json.dumps(group.get("extra_vars", {}))
        l.append(item)

        tags.items = l

        # Use the network interface provided in the network_link argument.
        network_interface = google.cloud.compute_v1.NetworkInterface()
        network_interface.name = group["subnet"]

        if group["public_ip"]:
            access = google.cloud.compute_v1.AccessConfig()
            access.type_ = google.cloud.compute_v1.AccessConfig.Type.ONE_TO_ONE_NAT.name
            access.name = "External NAT"
            access.network_tier = access.NetworkTier.PREMIUM.name

            network_interface.access_configs = [access]

        # Collect information into the Instance object.
        instance = google.cloud.compute_v1.Instance()
        instance.name = instance_name
        instance.disks = vols
        instance.machine_type = (
            f"zones/{gcpzone}/machineTypes/{self.get_instance_type(group)}"
        )
        instance.metadata = tags
        instance.labels = {"deployment_id": self.deployment_id}

        t = google.cloud.compute_v1.Tags()
        t.items = group["security_groups"]
        instance.tags = t

        instance.network_interfaces = [network_interface]

        # Wait for the create operation to complete.
        try:
            operation = instance_client.insert(
                instance_resource=instance, project=self.gcp_project, zone=gcpzone
            )

            self.wait_for_extended_operation(operation)

            logger.debug(f"GCP instance created: {instance.name}")

            # fetch details
            instance = instance_client.get(
                project=self.gcp_project, zone=gcpzone, instance=instance_name
            )

            # add the instance to the list
            self.update_new_deployment(
                [self.parse_gcp_query(instance, group["region"], group["zone"])]
            )

        except Exception as e:
            logger.error(e)
            self.log_error(e)

    def provision_azure_vm(self, cluster_name: str, group: dict, x: int):
        logger.debug("++azure %s %s %s" % (cluster_name, group["group_name"], x))

        try:
            # Acquire a credential object using CLI-based authentication.
            credential = EnvironmentCredential()
            client = ComputeManagementClient(credential, self.azure_subscription_id)

            instance_name = (
                self.deployment_id + "-" + str(random.randint(0, 1e16)).zfill(16)
            )

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
                    self.azure_resource_group,
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
                        self.azure_subscription_id,
                        self.azure_resource_group,
                        group["security_groups"][0],
                    )
                }

            poller = client.virtual_machines.begin_create_or_update(
                self.azure_resource_group,
                instance_name,
                {
                    "location": group["region"],
                    "tags": {
                        "deployment_id": self.deployment_id,
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
                        "vm_size": self.get_instance_type(group),
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
                                                self.azure_subscription_id,
                                                self.azure_resource_group,
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
            self.update_new_deployment(
                self.parse_azure_query(
                    instance,
                    *self.fetch_azure_instance_network_config(instance),
                )
            )

        except Exception as e:
            logger.error(e)
            self.log_error(e)

    def destroy_all(self, instances: list):
        target = {
            "aws": self.destroy_aws_vm,
            "gcp": self.destroy_gcp_vm,
            "azure": self.destroy_azure_vm,
        }

        for x in instances:
            self.changed = True
            thread = threading.Thread(target=target[x["cloud"]], args=(x,))
            thread.start()
            self.threads.append(thread)

    def destroy_aws_vm(self, instance: dict):
        
        def get_allocation_id(public_ip, instance_id):
            response = ec2.describe_addresses(PublicIps=[public_ip])

            for address in response['Addresses']:
                # Check if the EIP is associated with the given instance ID
                if address.get('InstanceId') == instance_id:
                    public_ip = address.get('PublicIp')
                    allocation_id = address.get('AllocationId')
                    print(f"Instance {instance_id} has EIP {public_ip} with Allocation ID {allocation_id}")
                    return allocation_id

            raise ValueError(f"No Elastic IP found associated with instance {instance_id}")
            
        logger.debug(f"--aws {instance['id']}")

        try:
            ec2 = boto3.client("ec2", region_name=instance["region"])

            alloc = get_allocation_id(instance["public_ip"], instance["id"])
            
            response = ec2.terminate_instances(
                InstanceIds=[instance["id"]],
            )

            waiter = ec2.get_waiter("instance_terminated")
            waiter.wait(InstanceIds=[instance["id"]])
    
            status = response["TerminatingInstances"][0]["CurrentState"]["Name"]

            if status in ["shutting-down", "terminated"]:
                logger.debug(f"Deleted AWS instance: {instance}")
            else:
                logger.error(f"Unexpected response: {response}")
                self.log_error(response)

            ec2.release_address(AllocationId=alloc)
            
        except Exception as e:
            logger.error(e)
            self.log_error(e)

    def destroy_gcp_vm(self, instance: dict):
        logger.debug(f"--gcp {instance['id']}")

        try:
            instance_client = google.cloud.compute_v1.InstancesClient()

            operation = instance_client.delete(
                project=self.gcp_project,
                zone="-".join([instance["region"], instance["zone"]]),
                instance=instance["id"],
            )
            # self.__wait_for_extended_operation(operation)
            logger.debug(f"Deleting GCP instance: {instance}")

        except Exception as e:
            logger.error(e)
            self.log_error(e)

    def destroy_azure_vm(self, instance: dict):
        logger.debug(f"--azure {instance['id']}")

        # Acquire a credential object using CLI-based authentication.
        try:
            credential = EnvironmentCredential()

            client = ComputeManagementClient(credential, self.azure_subscription_id)

            async_vm_delete = client.virtual_machines.begin_delete(
                self.azure_resource_group, instance["id"]
            )
            async_vm_delete.wait()

        except Exception as e:
            logger.error(e)
            self.log_error(e)

    # UTIL METHODS
    # =========================================================================

    def get_instance_type(self, group: dict):
        if "instance_type" in group:
            return group["instance_type"]

        # instance type
        cpu = str(group["instance"].get("cpu"))
        if cpu == "None":
            self.log_error("instance cpu cannot be null")
            return

        mem = str(group["instance"].get("mem", "default"))
        cloud = group["cloud"]
        return self.defaults["instances"][cloud][cpu][mem]

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

    def wait_for_extended_operation(self, operation: ExtendedOperation):
        result = operation.result(timeout=300)

        if operation.error_code:
            logger.debug(
                f"GCP Error: {operation.error_code}: {operation.error_message}"
            )

        return result

    def run(self) -> list[dict]:
        
        # fetch all running instances for the deployment_id and append them to the 'instances' list
        logger.info(
            f"Fetching all instances with deployment_id = '{self.deployment_id}'"
        )
        self.fetch_all(self.deployment_id, self.gcp_project, self.azure_resource_group)

        if self.errors:
            raise ValueError(self.errors)
        
        if self.instances:
            logger.info("Listing pre-existing instances:")
            for x in self.instances:
                logger.info(f"\t{x}")
        else:
            logger.info("No pre-existing instances")
            
        if self.errors:
            raise ValueError(self.errors)
            
        if self.gather_current_deployment_only:
            return self.instances

        # instances of the new deployment will go into the 'new_instances' list
        if self.present:
            logger.info("Building deployment...")
            self.build_deployment()

        # at this point, `instances` only has surplus vms that will be deleted
           
                
        if self.return_tobedeleted_vms:
            logger.info("Listing instances slated for deletion")
            for x in self.instances:
                logger.info(f"\t{x}")
                
            logger.info("Returning list of instances slated to be deleted to client")
            return self.instances

        if self.threads:
            logger.info("Creating new VMs...")
            for x in self.threads:
                x.start()
        else:
            logger.info("No instances to create")
                
        if self.instances and not self.preserve_existing_vms:
            logger.info("Listing instances slated for deletion")
            for x in self.instances:
                logger.info(f"\t{x}")
                
            logger.info("Removing instances...")
            self.destroy_all(self.instances)
            self.instances = []

        logger.info("Waiting for all operation threads to complete")
        for x in self.threads:
            x.join()
        logger.info("All operation threads have completed")

        if self.errors:
            raise ValueError(self.errors)

        if self.new_instances:
            logger.info("Listing new instances:")
            for x in self.new_instances:
                logger.info(f"\t{x}")

        if self.instances:
            logger.info("Listing preserved instances:")
            for x in self.instances:
                logger.info(f"\t{x}")

        logger.info("Returning new deployment list to client")
        return self.new_instances + self.instances


def str_to_bool(value: str) -> bool:
    return value.lower() in ["yes", "y", "true", "present", "1"]


def main():
    parser = argparse.ArgumentParser(description="Process deployment options.")

    parser.add_argument("deployment_id", type=str, help="Deployment ID")
    parser.add_argument(
        "present", type=str_to_bool, help="Whether the instance is present (yes/no)"
    )
    parser.add_argument(
        "deployment", type=json.loads, help="Deployment data as JSON string"
    )
    parser.add_argument(
        "defaults", type=json.loads, help="Default config as JSON string"
    )
    parser.add_argument(
        "--preserve",
        required=False,
        default="no",
        type=str_to_bool,
        help="Whether to preserve existing VMs (yes/no/true/false)",
    )
    parser.add_argument(
        "--return_tobedeleted_vms",
        required=False,
        default="no",
        type=str_to_bool,
        help="Return list of VMs slated to be deleted (yes/no/true/false)",
    )
    parser.add_argument(
        "--gather_current_deployment_only",
        required=False,
        default="no",
        type=str_to_bool,
        help="Only gather the current list of VMs without creating or deleting (yes/no/true/false)",
    )
    
    parser.add_argument(
        "--mod",
        required=False,
        default="no",
        type=str,
        help="The instance ID",
    )
    parser.add_argument(
        "--mod_cpu",
        required=False,
        default="no",
        type=str,
        help="The new cpu count",
    )
    parser.add_argument(
        "--mod_region",
        required=False,
        default="no",
        type=str,
        help="The id region",
    )

    args = parser.parse_args()
    
    
    if args.mod:
        ec2 = boto3.client("ec2", region_name=args.mod_region)
        
        print(f"Stopping instance {args.mod}...")
        ec2.stop_instances(InstanceIds=[args.mod])
        waiter = ec2.get_waiter("instance_stopped")
        waiter.wait(InstanceIds=[args.mod])
        print("Instance stopped.")

        
        print(f"Modifying instance {args.mod} to type {new_type}...")
        ec2.modify_instance_attribute(
            InstanceId=args.mod, InstanceType={"Value": new_type}
        )
        print("Instance type modified.")

        print(f"Starting instance {args.mod}...")
        ec2.start_instances(InstanceIds=[args.mod])
        waiter = ec2.get_waiter("instance_running")
        waiter.wait(InstanceIds=[args.mod])
        print("Instance is running.")

        return

    result = CloudInstance(
        args.deployment_id,
        args.present,
        args.deployment,
        args.defaults,
        args.preserve,
        args.return_tobedeleted_vms,
        args.gather_current_deployment_only,
    ).run()

    print(json.dumps(result))
