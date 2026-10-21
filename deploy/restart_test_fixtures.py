"""Invented nonsecret Docker endpoint metadata for operator contract tests."""

import json


def endpoint(network="synthetic-mesh", address="172.28.0.2", static=False, ipv6="", static6=False):
    ipam = {}
    if static:
        ipam["IPv4Address"] = address
    if static6:
        ipam["IPv6Address"] = ipv6
    return {"NetworkID": network, "IPAddress": address, "GlobalIPv6Address": ipv6,
            "IPAMConfig": ipam or None}


def record(ident, role, networks=None, running=True):
    return {"id": ident, "role": role, "running": running, "networks": networks or {}}


def metadata(records):
    return "\n".join(json.dumps(r) for r in records)


def role_metadata(roles):
    return metadata([record(ident, role) for ident, role in roles.items()])
