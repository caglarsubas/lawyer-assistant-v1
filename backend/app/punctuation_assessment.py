"""Closed, source-bound completion states for bounded OCR sidecar runs."""

STAGES = {"nomination_raw", "nomination_contrast", "currency_fields"}
INCOMPLETE = {"page_budget", "reader_error", "reader_unavailable", "source_scope_unverified"}


def valid_assessment(value, events=None):
    if (not isinstance(value, dict) or set(value) != {"status", "reason", "stage"}
            or not all(isinstance(value[key], str) for key in value)
            or value["stage"] not in STAGES):
        return False
    status, reason, stage = (value[key] for key in ("status", "reason", "stage"))
    if events is not None and (not isinstance(events, list) or (stage != "currency_fields" and events)):
        return False
    if status == "complete":
        if stage != "currency_fields" or reason not in {"checked", "no_currency_scope"}:
            return False
        if events is not None:
            if not isinstance(events, list) or (reason == "no_currency_scope" and events):
                return False
            if any(not isinstance(event, dict) or event.get("status") != "punctuation_disagreement"
                   for event in events):
                return False
        return True
    return (status == "incomplete" and reason in INCOMPLETE
            and (reason != "source_scope_unverified" or stage == "currency_fields"))
