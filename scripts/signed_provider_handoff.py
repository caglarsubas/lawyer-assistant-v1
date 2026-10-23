"""Pure prospective relay codec. No serving handler, network or key provisioning."""

from signed_provider_contract import decode, nonce


def metadata_headers(headers):
    if not isinstance(headers, list) or len(headers) != 2:
        raise ValueError("Exact metadata headers required")
    values = {}
    for entry in headers:
        if not isinstance(entry, (tuple, list)) or len(entry) != 2:
            raise ValueError("Malformed metadata header")
        name, value = entry
        key = name.lower() if isinstance(name, str) else None
        if (
            key not in {"authorization", "x-lawyer-identity-challenge"}
            or key in values
            or not isinstance(value, str)
        ):
            raise ValueError("Unknown or duplicate metadata header")
        values[key] = value
    auth = values.get("authorization", "")
    if (
        not auth.startswith("Bearer ")
        or not 8 <= len(auth[7:]) <= 4096
        or any(not 33 <= ord(c) <= 126 for c in auth[7:])
    ):
        raise ValueError("Bounded existing authorization required")
    return {
        "Authorization": auth,
        "X-Lawyer-Identity-Challenge": nonce(values.get("x-lawyer-identity-challenge")),
    }


def preserve_envelope(raw, kind):
    value = decode(raw)
    fields = (
        {"claims", "signature"}
        if kind == "identity"
        else {"response_base64", "provider_binding"}
        if kind == "completion"
        else None
    )
    if fields is None or not isinstance(value, dict) or set(value) != fields:
        raise ValueError("Unsupported signed handoff shape")
    # Opaque byte preservation, not signature verification or permission. The
    # independent recipient must verify freshness, issuer, pin, request and body.
    return raw
