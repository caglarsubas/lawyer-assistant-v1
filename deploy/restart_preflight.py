"""Pure, conservative restart ordering from nonsecret Docker endpoint metadata."""

import ipaddress
import json

MAX_CONTAINERS = 128
MAX_NETWORKS = 32
MAX_METADATA_BYTES = 512 * 1024
ROLES = frozenset({"provider-relay", "api", "web", "postgres", "opensearch", "fuseki",
                   "scanner", "extractor"})


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Ambiguous restart endpoint metadata")
        result[key] = value
    return result


def _address(value, family):
    if value == "":
        return None
    try:
        if not isinstance(value, str):
            raise ValueError
        address = ipaddress.ip_address(value)
        if (address.version != family or address.is_unspecified or address.is_multicast
                or address.is_loopback or "%" in value):
            raise ValueError
        return str(address)
    except ValueError:
        raise ValueError("Cannot verify restart endpoint address") from None


def plan_restarts(container_ids, metadata):
    """Return dependency layers, or reject before any container is stopped.

    All explicitly requested IPv4/IPv6 endpoints precede dynamic allocators on
    the same network/family. Keep relay/backing/API/web startup constraints too.
    A cycle requires operator topology remediation, never a guessed start order.
    No addresses, identifiers or raw metadata enter exception messages.
    """
    if (len(container_ids) > MAX_CONTAINERS or not all(isinstance(c, str) and c for c in container_ids)
            or len(set(container_ids)) != len(container_ids)):
        raise ValueError("Cannot verify running-container restart set")
    if not isinstance(metadata, str) or len(metadata.encode()) > MAX_METADATA_BYTES:
        raise ValueError("Restart endpoint metadata exceeds its bound")
    records = {}
    try:
        for line in metadata.splitlines():
            item = json.loads(line, object_pairs_hook=_unique)
            if (not isinstance(item, dict) or set(item) != {"id", "role", "running", "networks"}
                    or not isinstance(item["id"], str) or item["id"] in records
                    or item["role"] not in ROLES or item["running"] is not True
                    or not isinstance(item["networks"], dict) or len(item["networks"]) > MAX_NETWORKS):
                raise ValueError
            records[item["id"]] = item
    except (ValueError, TypeError, RecursionError):
        raise ValueError("Cannot verify complete running-container endpoint metadata") from None
    if set(records) != set(container_ids):
        raise ValueError("Cannot verify complete running-container endpoint metadata")

    dependencies = {c: set() for c in container_ids}
    rank = {c: {"provider-relay": 0, "api": 2, "web": 3}.get(records[c]["role"], 1)
            for c in container_ids}
    for later in container_ids:
        dependencies[later].update(c for c in container_ids if rank[c] < rank[later])

    allocators, reserved = {}, {}
    for ident, record in records.items():
        networks = set()
        for endpoint in record["networks"].values():
            if not isinstance(endpoint, dict):
                raise ValueError("Cannot verify restart network metadata")
            network = endpoint.get("NetworkID")
            if not isinstance(network, str) or not network or network in networks:
                raise ValueError("Cannot verify restart network identity")
            networks.add(network)
            ipam = endpoint.get("IPAMConfig")
            if ipam is None:
                ipam = {}
            if (not isinstance(ipam, dict) or set(ipam) - {"IPv4Address", "IPv6Address", "LinkLocalIPs"}
                    or ipam.get("LinkLocalIPs")):
                raise ValueError("Cannot verify explicit restart endpoint configuration")
            for family, current_key, requested_key in ((4, "IPAddress", "IPv4Address"),
                                                        (6, "GlobalIPv6Address", "IPv6Address")):
                current = _address(endpoint.get(current_key), family)
                requested = _address(ipam.get(requested_key, ""), family)
                if requested and current != requested:
                    raise ValueError("Explicit restart address does not match the running endpoint")
                if not current:
                    continue
                key = network, family
                static, dynamic = allocators.setdefault(key, (set(), set()))
                if requested:
                    reservation = key, requested
                    if reservation in reserved:
                        raise ValueError("Conflicting explicit restart address requests")
                    reserved[reservation] = ident
                    static.add(ident)
                else:
                    dynamic.add(ident)
    for static, dynamic in allocators.values():
        for ident in dynamic:
            dependencies[ident].update(static - {ident})

    remaining = set(container_ids)
    groups = []
    while remaining:
        ready = [c for c in container_ids if c in remaining and not dependencies[c] & remaining]
        if not ready:
            raise ValueError("Unsafe restart plan: address reservations conflict with startup dependencies")
        groups.append(ready)
        remaining.difference_update(ready)
    return groups
