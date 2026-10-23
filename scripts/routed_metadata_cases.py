"""Fresh invented diagnostics, frozen before first execution; no private case material."""
import json

CASES = (
    ("D2001", "legacy_ok", "metadata_accepted_identity_unqualified"),
    ("D2002", "relay_connection_closed", "http_status_rejected"),
    ("D2003", "foreign_error_code", "http_status_rejected"),
    ("D2004", "redirect", "http_status_rejected"),
    ("D2005", "read_timeout", "http_transport_rejected"),
    ("D2006", "invalid_json", "metadata_json_rejected"),
    ("D2007", "foreign_route", "transport_metadata_rejected"),
    ("D2008", "absent_model", "configured_model_unresolved"),
    ("D2009", "small_context", "local_model_metadata_rejected"),
    ("D2010", "oversized", "metadata_budget_exceeded"),
    ("D2011", "encoded", "encoded_metadata_rejected"),
    ("D2012", "changed_config", "configuration_changed"),
)
SUITE_CANONICAL = json.dumps(CASES, separators=(",", ":"))
