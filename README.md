# cloud_instance

Usage:

```text
cloud_instance <deployment_id> <present/absent> <deployment> <defaults>
```

Example:

```bash
$ cloud_instance \
    fabio1 \
    present \
    '[
        {
                "cluster_name": "fabio1",
                "copies": 1,
                "inventory_groups": ["haproxy"],
                "exact_count": 1,
                "instance": {"cpu": 4},
                "volumes": {"os": {"size": 20, "type": "standard_ssd"}, "data": []},
                "tags": {"Name": "fabio1-lb"},
                "project": "my-team-key",
                "groups": [
                    {
                        "user": "ubuntu",
                        "public_ip": true,
                        "public_key_id": "workshop",
                        "tags": {"owner": "fabio"},
                        "cloud": "gcp",
                        "image": "projects/ubuntu-os-cloud/global/images/family/ubuntu-2004-lts",
                        "region": "us-east4",
                        "vpc_id": "default",
                        "security_groups": ["cockroachdb"],
                        "zone": "a",
                        "subnet": "default"
                    }
                ]
        }
    ]' \
    '{
        "instances": {
            "aws": {
            "2": {
                "default": "m6i.large",
                "4": "c5.large",
                "8": "m6i.large",
                "16": "r5.large"
            },
            "4": {
                "default": "m6i.xlarge",
                "8": "c5.xlarge",
                "16": "m6i.xlarge",
                "32": "r5.xlarge"
            },
            "8": {
                "default": "m6i.2xlarge",
                "16": "c5.2xlarge",
                "32": "m6i.2xlarge",
                "64": "r5.2xlarge"
            },
            "16": {
                "default": "m6i.4xlarge",
                "32": "c5.4xlarge",
                "64": "m6i.4xlarge",
                "128": "r5.4xlarge"
            },
            "32": {
                "default": "m6i.8xlarge",
                "128": "m6i.8xlarge",
                "256": "r5.8xlarge"
            }
            },
            "azure": {
            "2": {
                "4": "Standard_F2s_v2",
                "8": "Standard_D2s_v3",
                "16": "Standard_E2s_v3",
                "default": "Standard_D2s_v3"
            },
            "4": {
                "8": "Standard_F4s_v2",
                "16": "Standard_D4s_v3",
                "32": "Standard_E4s_v3",
                "default": "Standard_D4s_v3"
            },
            "8": {
                "16": "Standard_F8s_v2",
                "32": "Standard_D8s_v3",
                "64": "Standard_E8s_v3",
                "default": "Standard_D8s_v3"
            },
            "16": {
                "32": "Standard_F16s_v2",
                "64": "Standard_D16s_v3",
                "128": "Standard_E16s_v3",
                "default": "Standard_D16s_v3"
            },
            "32": {
                "64": "Standard_F32s_v2",
                "128": "Standard_D32s_v3",
                "256": "Standard_E32s_v3",
                "default": "Standard_D32s_v3"
            }
            },
            "gcp": {
            "2": {
                "default": "n2-standard-2",
                "2": "n2-highcpu-2",
                "4": "n2-standard-2",
                "8": "n2-standard-2",
                "16": "n2-highmem-2"
            },
            "4": {
                "default": "n2-standard-4",
                "4": "n2-highcpu-4",
                "8": "n2-standard-4",
                "16": "n2-standard-4",
                "32": "n2-highmem-4"
            },
            "8": {
                "default": "n2-standard-8",
                "8": "n2-highcpu-8",
                "16": "n2-standard-8",
                "32": "n2-standard-8",
                "64": "n2-highmem-8"
            },
            "16": {
                "default": "n2-standard-16",
                "16": "n2-highcpu-16",
                "32": "n2-standard-16",
                "64": "n2-standard-16",
                "128": "n2-highmem-16"
            },
            "32": {
                "default": "n2-standard-32",
                "32": "n2-highcpu-32",
                "64": "n2-standard-32",
                "128": "n2-standard-32",
                "256": "n2-highmem-32"
            }
            }
        }
    }'
```
