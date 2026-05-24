from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class IPAddressType(StrEnum):
    IPv6 = "ipv6"
    IPv4_EPHEMERAL = "ipv4_ephemeral"
    IPv4_RESERVED = "ipv4_reserved"


@dataclass(slots=True)
class CloudInstance:
    id: str
    cloud: str
    region: str
    zone: str
    public_ip: str | None = None
    public_hostname: str = ""
    private_ip: str | None = None
    private_hostname: str = ""
    ansible_user: str = ""
    inventory_groups: list[str] = field(default_factory=list)
    cluster_name: str = ""
    group_name: str = ""
    extra_vars: str | dict[str, Any] = field(default_factory=dict)
    public_ipv4: str | None = None
    public_ipv6: str | None = None
    ip_address_type: IPAddressType | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Any) -> "CloudInstance":
        data = _require_mapping(value, "instance")
        return cls(
            id=data.pop("id"),
            cloud=data.pop("cloud"),
            region=data.pop("region"),
            zone=data.pop("zone"),
            public_ip=data.pop("public_ip", None),
            public_hostname=data.pop("public_hostname", ""),
            private_ip=data.pop("private_ip", None),
            private_hostname=data.pop("private_hostname", ""),
            ansible_user=data.pop("ansible_user", ""),
            inventory_groups=_as_str_list(
                data.pop("inventory_groups", []), "inventory_groups"
            ),
            cluster_name=data.pop("cluster_name", ""),
            group_name=data.pop("group_name", ""),
            extra_vars=data.pop("extra_vars", {}),
            public_ipv4=data.pop("public_ipv4", None),
            public_ipv6=data.pop("public_ipv6", None),
            ip_address_type=_ip_address_type(data.pop("ip_address_type", None)),
            extra=data,
        )

    def to_dict(self) -> dict[str, Any]:
        data = _without_empty(
            {
                "id": self.id,
                "cloud": self.cloud,
                "region": self.region,
                "zone": self.zone,
                "public_ip": self.public_ip,
                "public_hostname": self.public_hostname,
                "private_ip": self.private_ip,
                "private_hostname": self.private_hostname,
                "ansible_user": self.ansible_user,
                "inventory_groups": self.inventory_groups,
                "cluster_name": self.cluster_name,
                "group_name": self.group_name,
                "extra_vars": self.extra_vars,
                "public_ipv4": self.public_ipv4,
                "public_ipv6": self.public_ipv6,
                "ip_address_type": (
                    self.ip_address_type.value if self.ip_address_type else None
                ),
            }
        )
        return {**self.extra, **data}


@dataclass(slots=True)
class InstanceDefaults:
    values: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Any) -> "InstanceDefaults":
        return cls(_require_mapping(value, "defaults"))

    def instance_type(
        self, cloud: str, cpu: int | str | None, mem: int | str | None = None
    ):
        cpu_key = str(cpu)
        mem_key = str(mem or "default")
        return self.values[cloud][cpu_key][mem_key]


@dataclass(slots=True)
class GroupFilter:
    groups: tuple[str, ...] = ()

    @classmethod
    def from_csv(cls, value: str | None) -> "GroupFilter":
        if not value:
            return cls()
        return cls(tuple(x for x in value.split(",") if x))

    def matches(self, instance: CloudInstance) -> bool:
        if not self.groups:
            return True
        return set(self.groups).issubset(set(instance.inventory_groups))


@dataclass(slots=True)
class InstanceSpec:
    cpu: int | str | None = None
    mem: int | str | None = None
    arch: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Any) -> "InstanceSpec | None":
        if value is None:
            return None
        data = _require_mapping(value, "instance")
        return cls(
            cpu=data.pop("cpu", None),
            mem=data.pop("mem", None),
            arch=data.pop("arch", None),
            extra=data,
        )

    def to_dict(self) -> dict[str, Any]:
        return _without_empty(
            {
                "cpu": self.cpu,
                "mem": self.mem,
                "arch": self.arch,
                **self.extra,
            }
        )


@dataclass(slots=True)
class Volume:
    size: int | str | None = None
    type: str | None = None
    iops: int | None = None
    throughput: int | None = None
    delete_on_termination: bool | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Any) -> "Volume":
        data = _require_mapping(value, "volume")
        return cls(
            size=data.pop("size", None),
            type=data.pop("type", None),
            iops=data.pop("iops", None),
            throughput=data.pop("throughput", None),
            delete_on_termination=data.pop("delete_on_termination", None),
            extra=data,
        )

    def to_dict(self) -> dict[str, Any]:
        return _without_empty(
            {
                "size": self.size,
                "type": self.type,
                "iops": self.iops,
                "throughput": self.throughput,
                "delete_on_termination": self.delete_on_termination,
                **self.extra,
            }
        )


@dataclass(slots=True)
class Volumes:
    os: Volume | None = None
    data: list[Volume] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Any) -> "Volumes | None":
        if value is None:
            return None
        data = _require_mapping(value, "volumes")
        os_volume = Volume.from_dict(data.pop("os")) if "os" in data else None
        data_volumes = [
            Volume.from_dict(x)
            for x in _require_list(data.pop("data", []), "volumes.data")
        ]
        return cls(os=os_volume, data=data_volumes, extra=data)

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.extra)
        if self.os is not None:
            data["os"] = self.os.to_dict()
        if self.data:
            data["data"] = [x.to_dict() for x in self.data]
        return data


@dataclass(slots=True)
class Group:
    cloud: str | None = None
    user: str | None = None
    public_ip: bool | None = None
    public_key_id: str | None = None
    image: str | None = None
    region: str | None = None
    zone: str | None = None
    subnet: str | None = None
    vpc_id: str | None = None
    security_groups: list[str] = field(default_factory=list)
    inventory_groups: list[str] = field(default_factory=list)
    group_name: str | None = None
    exact_count: int | None = None
    instance: InstanceSpec | None = None
    instance_type: str | None = None
    volumes: Volumes | None = None
    tags: dict[str, str] = field(default_factory=dict)
    role: str | None = None
    user_data: str | None = None
    extra_vars: dict[str, Any] = field(default_factory=dict)
    ip_address_type: IPAddressType | None = None
    imports: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Any) -> "Group":
        data = _require_mapping(value, "group")
        return cls(
            cloud=data.pop("cloud", None),
            user=data.pop("user", None),
            public_ip=data.pop("public_ip", None),
            public_key_id=data.pop("public_key_id", None),
            image=data.pop("image", None),
            region=data.pop("region", None),
            zone=data.pop("zone", None),
            subnet=data.pop("subnet", None),
            vpc_id=data.pop("vpc_id", None),
            security_groups=_as_str_list(
                data.pop("security_groups", []), "security_groups"
            ),
            inventory_groups=_as_str_list(
                data.pop("inventory_groups", []), "inventory_groups"
            ),
            group_name=data.pop("group_name", None),
            exact_count=data.pop("exact_count", None),
            instance=InstanceSpec.from_dict(data.pop("instance", None)),
            instance_type=data.pop("instance_type", None),
            volumes=Volumes.from_dict(data.pop("volumes", None)),
            tags=_as_str_dict(data.pop("tags", {}), "tags"),
            role=data.pop("role", None),
            user_data=data.pop("user_data", None),
            extra_vars=_require_mapping(data.pop("extra_vars", {}), "extra_vars"),
            ip_address_type=_ip_address_type(data.pop("ip_address_type", None)),
            imports=_require_mapping(data.pop("import", {}), "import"),
            extra=data,
        )

    def to_dict(self) -> dict[str, Any]:
        data = _without_empty(
            {
                "cloud": self.cloud,
                "user": self.user,
                "public_ip": self.public_ip,
                "public_key_id": self.public_key_id,
                "image": self.image,
                "region": self.region,
                "zone": self.zone,
                "subnet": self.subnet,
                "vpc_id": self.vpc_id,
                "security_groups": self.security_groups,
                "inventory_groups": self.inventory_groups,
                "group_name": self.group_name,
                "exact_count": self.exact_count,
                "instance": self.instance.to_dict() if self.instance else None,
                "instance_type": self.instance_type,
                "volumes": self.volumes.to_dict() if self.volumes else None,
                "tags": self.tags,
                "role": self.role,
                "user_data": self.user_data,
                "extra_vars": self.extra_vars,
                "ip_address_type": (
                    self.ip_address_type.value if self.ip_address_type else None
                ),
                "import": self.imports,
            }
        )
        return {**self.extra, **data}


@dataclass(slots=True)
class Cluster:
    cluster_name: str | None = None
    copies: int | None = None
    inventory_groups: list[str] = field(default_factory=list)
    security_groups: list[str] = field(default_factory=list)
    exact_count: int | None = None
    instance: InstanceSpec | None = None
    instance_type: str | None = None
    volumes: Volumes | None = None
    tags: dict[str, str] = field(default_factory=dict)
    groups: list[Group] = field(default_factory=list)
    project: str | None = None
    ip_address_type: IPAddressType | None = None
    imports: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Any) -> "Cluster":
        data = _require_mapping(value, "cluster")
        return cls(
            cluster_name=data.pop("cluster_name", None),
            copies=data.pop("copies", None),
            inventory_groups=_as_str_list(
                data.pop("inventory_groups", []), "inventory_groups"
            ),
            security_groups=_as_str_list(
                data.pop("security_groups", []), "security_groups"
            ),
            exact_count=data.pop("exact_count", None),
            instance=InstanceSpec.from_dict(data.pop("instance", None)),
            instance_type=data.pop("instance_type", None),
            volumes=Volumes.from_dict(data.pop("volumes", None)),
            tags=_as_str_dict(data.pop("tags", {}), "tags"),
            groups=[
                Group.from_dict(x)
                for x in _require_list(data.pop("groups", []), "groups")
            ],
            project=data.pop("project", None),
            ip_address_type=_ip_address_type(data.pop("ip_address_type", None)),
            imports=_require_mapping(data.pop("import", {}), "import"),
            extra=data,
        )

    def to_dict(self) -> dict[str, Any]:
        data = _without_empty(
            {
                "cluster_name": self.cluster_name,
                "copies": self.copies,
                "inventory_groups": self.inventory_groups,
                "security_groups": self.security_groups,
                "exact_count": self.exact_count,
                "instance": self.instance.to_dict() if self.instance else None,
                "instance_type": self.instance_type,
                "volumes": self.volumes.to_dict() if self.volumes else None,
                "tags": self.tags,
                "groups": [x.to_dict() for x in self.groups],
                "project": self.project,
                "ip_address_type": (
                    self.ip_address_type.value if self.ip_address_type else None
                ),
                "import": self.imports,
            }
        )
        return {**self.extra, **data}


@dataclass(slots=True)
class Deployment:
    clusters: list[Cluster] = field(default_factory=list)

    @classmethod
    def from_list(cls, value: Any) -> "Deployment":
        return cls(
            clusters=[Cluster.from_dict(x) for x in _require_list(value, "deployment")]
        )

    def to_list(self) -> list[dict[str, Any]]:
        return [x.to_dict() for x in self.clusters]


@dataclass(slots=True)
class ProvisionTask:
    deployment_id: str
    cluster_name: str
    group: Group
    index: int


@dataclass(slots=True)
class BuildResult:
    current_vms: list[CloudInstance] = field(default_factory=list)
    surplus_vms: list[CloudInstance] = field(default_factory=list)
    new_vms: list[ProvisionTask] = field(default_factory=list)


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a dict")
    return dict(value)


def _require_list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    return value


def _as_str_list(value: Any, name: str) -> list[str]:
    return [str(x) for x in _require_list(value, name)]


def _as_str_dict(value: Any, name: str) -> dict[str, str]:
    return {str(k): str(v) for k, v in _require_mapping(value, name).items()}


def _ip_address_type(value: Any) -> IPAddressType | None:
    if value is None:
        return None
    try:
        return IPAddressType(value)
    except ValueError:
        raise ValueError(f"Invalid ip_address_type: {value}") from None


def _without_empty(data: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in data.items() if v is not None and v != {} and v != []}
