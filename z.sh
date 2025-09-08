poetry run cloud_instance create \
    -d fabio1 \
    --deployment \
    '[
        {
            "cluster_name": "fabio1",
            "copies": 1,
            "inventory_groups": ["haproxy"],
            "exact_count": 1,
            "instance": {"cpu": 1},
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
                "1": {
                    "default": "e2-micro",
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

