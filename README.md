# cloud_instance

`cloud_instance` is a small universal CLI for managing compute instances across
cloud providers. It uses the official provider libraries for AWS, GCP, and Azure
so you can describe the instances you want and let one tool handle the provider
API calls. ☁️

The goal is practical infrastructure automation without needing a separate
workflow for each cloud. Give `cloud_instance` a deployment description, a set of
instance-size defaults, and a `deployment_id`; it can create, query, resize,
modify, scale, and delete the matching VMs.

## Why Use It?

- One interface for major cloud providers: AWS, GCP, and Azure.
- Works well from shell scripts, CI jobs, and Ansible playbooks.
- Tracks instances by `deployment_id` and tags/labels.
- Supports common VM lifecycle tasks:
  - create deployments
  - delete deployments
  - gather/query existing instances
  - show instances slated for deletion
  - resize disks
  - modify instance type / CPU size
  - scale groups by changing `exact_count`
- Designed to grow: new environments can be added when suitable provider
  libraries or APIs are available. 🔧

## Create Deployment Payload

The `create --deployment` argument is a JSON array of clusters. There is no
extra top-level deployment object; the CLI receives `list[Cluster]` directly.

Each cluster can hold shared defaults such as `copies`, `inventory_groups`,
`instance`, `volumes`, `tags`, and `security_groups`. Each item in `groups`
describes one provider-specific group of instances. Cluster fields are merged
into each group, and group fields win when both define the same setting.

Common cluster fields:

- `cluster_name`: base name for generated cluster copies; defaults to the
  `deployment_id` when omitted.
- `copies`: number of cluster copies to create.
- `inventory_groups`: Ansible inventory groups shared by every child group.
- `exact_count`: desired number of instances for a group unless overridden.
- `instance`: generic shape such as `cpu`, `mem`, and `arch`.
- `instance_type`: provider-native type; overrides `instance` lookup defaults.
- `volumes`: `os` volume plus optional `data` volumes.
- `tags`: tags/labels/metadata applied to provisioned instances.
- `groups`: provider-specific instance groups.

Common group fields:

- `cloud`: provider name such as `aws`, `gcp`, `azure`, or `kloigos`.
- `group_name`: stable group identity used when matching existing instances.
- `region` and `zone`: provider location.
- `exact_count`: desired number of instances in this group.
- `user`: login/Ansible user.
- `public_ip`: whether to request public network access.
- `public_key_id`: provider key name or SSH public key, depending on provider.
- `image`: provider image reference.
- `subnet`, `vpc_id`, `security_groups`: network placement and firewall inputs.
- `ip_address_type`: `ipv6`, `ipv4_ephemeral`, or `ipv4_reserved` where
  supported.
- `extra_vars`: arbitrary data returned with created instances.

Example YAML shape:

```yaml
- cluster_name: app
  copies: 1
  inventory_groups:
    - web
  exact_count: 2
  instance:
    cpu: 1
  volumes:
    os:
      size: 20
      type: standard_ssd
    data: []
  groups:
    - cloud: aws
      group_name: web
      region: ca-central-1
      zone: b
      user: ubuntu
      public_ip: true
      ip_address_type: ipv6
      image: /canonical/ubuntu/server/24.04
      public_key_id: workshop
      subnet: subnet-1234567890abcdef0
      security_groups:
        - sg-1234567890abcdef0
```

Instance type defaults map a generic CPU/memory request to each provider's
native instance type:

```yaml
defaults:
  aws:
    "1":
      default: t3.micro
    "2":
      default: t3.large
  gcp:
    "1":
      default: e2-micro
    "2":
      default: e2-medium
  azure:
    "4":
      default: Standard_D4s_v3
```

## CLI Examples

Create or converge a deployment:

```bash
cloud_instance create \
  -d workshop \
  --deployment "$DEPLOYMENT_JSON" \
  --defaults "$DEFAULTS_JSON"
```

Query existing instances:

```bash
cloud_instance gather -d workshop
```

Resize disks for instances in a group:

```bash
cloud_instance resize \
  -d workshop \
  --disk-size 300 \
  --filter-by-groups web \
  --pause-between 1
```

Modify instance type by CPU count:

```bash
cloud_instance modify \
  -d workshop \
  --cpu-count 2 \
  --filter-by-groups web \
  --defaults "$DEFAULTS_JSON"
```

Delete a deployment:

```bash
cloud_instance delete -d workshop
```

## Ansible Example

`cloud_instance` is especially handy from Ansible because playbooks can keep the
deployment model in YAML and pass it to the CLI as JSON. 🚀

```yaml
---
- name: Manage cloud instances
  hosts: localhost
  connection: local
  gather_facts: no
  vars:
    deployment_id: workshop
    deployment:
      - cluster_name: app
        copies: 1
        inventory_groups:
          - web
        exact_count: 1
        instance:
          cpu: 1
        volumes:
          os:
            size: 20
            type: standard_ssd
          data:
            - size: 200
              type: standard_ssd
              iops: 500
              throughput: 300
              delete_on_termination: yes
        tags:
          Name: workshop-web
        groups:
          - user: ubuntu
            public_ip: true
            public_key_id: workshop
            cloud: gcp
            image: projects/ubuntu-os-cloud/global/images/family/ubuntu-2404-lts-amd64
            region: us-east4
            zone: b
            subnet: default
            security_groups:
              - web
    defaults:
      gcp:
        "1":
          default: e2-micro
        "2":
          default: e2-medium

  tasks:
    - name: Ensure instances are present
      shell: |
        cloud_instance create \
          -d {{ deployment_id }} \
          --deployment '{{ deployment | to_json }}' \
          --defaults '{{ defaults | to_json }}'
      register: instances

    - debug:
        var: instances.stdout | from_json
```

## Notes

Provider credentials are handled by the underlying official libraries. Make sure
your AWS, GCP, or Azure environment is authenticated before running commands.

For AWS IPv6 deployments, set `ip_address_type: ipv6` in the deployment group and
ensure the target VPC, subnet, route table, and security group are IPv6-ready.
✨
