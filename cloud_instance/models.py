from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class IPAddressType(StrEnum):
    IPv6 = "ipv6"
    IPv4_EPHEMERAL = "ipv4_ephemeral"
    IPv4_RESERVED = "ipv4_reserved"


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a dict")
    return value


def _require_list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    return value


def _normalize_ip_address_type(data: dict[str, Any]) -> dict[str, Any]:
    if "ip_address_type" not in data:
        return data

    try:
        data["ip_address_type"] = IPAddressType(data["ip_address_type"]).value
    except ValueError:
        raise ValueError(f"Invalid ip_address_type: {data['ip_address_type']}") from None

    return data


@dataclass(slots=True)
class Group:
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Group":
        data = dict(_require_mapping(value, "group"))
        _normalize_ip_address_type(data)
        return cls(data)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.data)


@dataclass(slots=True)
class Cluster:
    data: dict[str, Any] = field(default_factory=dict)
    groups: list[Group] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Cluster":
        data = dict(_require_mapping(value, "cluster"))
        groups = [
            Group.from_dict(x)
            for x in _require_list(data.get("groups", []), "groups")
        ]
        data["groups"] = [x.to_dict() for x in groups]
        _normalize_ip_address_type(data)
        return cls(data, groups)

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.data)
        data["groups"] = [x.to_dict() for x in self.groups]
        return data


@dataclass(slots=True)
class Deployment:
    clusters: list[Cluster] = field(default_factory=list)

    @classmethod
    def from_list(cls, value: list[dict[str, Any]]) -> "Deployment":
        clusters = [
            Cluster.from_dict(x)
            for x in _require_list(value, "deployment")
        ]
        return cls(clusters)

    def to_list(self) -> list[dict[str, Any]]:
        return [x.to_dict() for x in self.clusters]
