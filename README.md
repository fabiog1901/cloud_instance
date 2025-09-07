# cloud_instance

Usage:

```text
cloud_instance create \
  -d <deployment_id> 
  --deployment <deployment> \
  --defaults <defaults>
```

Example:

```bash
cloud_instance create \
    -d fabio1 \
    --deployment \
    '[
        {
            "cluster_name": "fabio1",
            "copies": 1,
            "inventory_groups": ["haproxy"],
            "exact_count": 1,
            "instance": {"cpu": 4},
            "volumes": {"os": {"size": 20, "type": "standard_ssd"}, "data": []},
            "tags": {"Name": "fabio1-lb"},
            "project": "my-team",
            "groups": [
                {
                    "user": "ubuntu",
                    "public_ip": true,
                    "public_key_id": "workshop",
                    "tags": {"owner": "fabio"},
                    "cloud": "gcp",
                    "image": "projects/ubuntu-os-cloud/global/images/family/ubuntu-2404-lts-amd64",
                    "region": "us-east4",
                    "vpc_id": "default",
                    "security_groups": ["cockroachdb"],
                    "zone": "a",
                    "subnet": "default"
                }
            ]
        }
    ]' \
    --defaults '{
            "aws": {
                "4": {
                    "default": "m6i.xlarge",
                    "16": "m6i.xlarge",
                    "32": "r5.xlarge"
                },
                "8": {
                    "default": "m6i.2xlarge",
                    "32": "m6i.2xlarge",
                    "64": "r5.2xlarge"
                }
            },
            "azure": {
                "4": {
                    "16": "Standard_D4s_v3",
                    "32": "Standard_E4s_v3",
                    "default": "Standard_D4s_v3"
                },
                "8": {
                    "32": "Standard_D8s_v3",
                    "64": "Standard_E8s_v3",
                    "default": "Standard_D8s_v3"
                }
            },
            "gcp": {
                "4": {
                    "default": "n2-standard-4",
                    "8": "n2-standard-4",
                    "16": "n2-highmem-4"
                },
                "8": {
                    "default": "n2-standard-8",
                    "16": "n2-standard-8",
                    "64": "n2-highmem-8"
                }
            }
        }' | jq
```

Output, formatted thanks to `jq`:

```json
[
  {
    "id": "fabio1-7141637722071383",
    "cloud": "gcp",
    "region": "us-east4",
    "zone": "a",
    "public_ip": "35.245.214.0",
    "public_hostname": "0.214.245.35.bc.googleusercontent.com",
    "private_ip": "10.150.15.208",
    "private_hostname": "fabio1-7141637722071383.c.my-team.internal",
    "ansible_user": "ubuntu",
    "inventory_groups": [
      "haproxy",
      "fabio1-0"
    ],
    "cluster_name": "fabio1-0",
    "group_name": "haproxy",
    "extra_vars": "{}"
  }
]
```
