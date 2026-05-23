from enum import StrEnum


class IPAddressType(StrEnum):
    IPv6 = "ipv6"
    IPv4_EPHEMERAL = "ipv4_ephemeral"
    IPv4_RESERVED = "ipv4_reserved"
