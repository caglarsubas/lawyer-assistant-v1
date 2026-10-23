"""Fresh invented identity/response protocol cases, never native acceptance."""

from app.evidence_prompt import canonical

CASES = [
    {"id": "P1901", "mode": "signed_valid", "expected": "bound"},
    {"id": "P1902", "mode": "legacy_metadata", "expected": "identity_unqualified"},
    {"id": "P1903", "mode": "foreign_tenant", "expected": "identity_unqualified"},
    {"id": "P1904", "mode": "wrong_nonce", "expected": "binding_rejected"},
    {"id": "P1905", "mode": "wrong_request", "expected": "binding_rejected"},
    {"id": "P1906", "mode": "altered_payload", "expected": "binding_rejected"},
    {"id": "P1907", "mode": "legacy_completion", "expected": "binding_rejected"},
    {"id": "P1908", "mode": "signed_empty", "expected": "bound"},
]
SUITE_CANONICAL = canonical(CASES)
