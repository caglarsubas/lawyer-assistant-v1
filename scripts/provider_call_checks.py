"""Bounded caller-side correlation; no assertion about engine/tunnel root cause."""

import hashlib
import math

from provider_job_fixture import DIAGNOSTIC_CODES

STATUSES = {200, 400, 401, 403, 408, 413, 429, 500, 502, 503, 504, "other"}


def correlate(cases, events):
    expected = {hashlib.sha256(c["question"].encode()).hexdigest(): c["id"] for c in cases}
    if len(expected) != len(cases) or len(events) != len(cases):
        raise ValueError("Caller event inventory differs")
    result, sequences = {}, set()
    for event in events:
        if set(event) != {"sequence", "started", "finished", "question_sha256", "http", "diagnostics", "outcome"}:
            raise ValueError("Caller event fields differ")
        identity = expected.get(event["question_sha256"])
        sequence = event["sequence"]
        start, end = event["started"], event["finished"]
        if (identity is None or identity in result or type(sequence) is not int or not 1 <= sequence <= len(cases)
                or sequence in sequences or any(type(v) not in (int, float) or not math.isfinite(v) for v in (start, end))
                or not 0 < start < end or event["outcome"] not in {"returned", "failed"}
                or not isinstance(event["http"], list) or len(event["http"]) > 8
                or not isinstance(event["diagnostics"], dict)
                or any(k not in DIAGNOSTIC_CODES or type(v) is not int or not 1 <= v <= 8 for k, v in event["diagnostics"].items())):
            raise ValueError("Caller event invalid")
        prior = 0
        for row in event["http"]:
            if (set(row) != {"stage", "status", "elapsed_seconds"} or row["stage"] not in {"metadata", "completion"}
                    or type(row["status"]) not in (int, str) or row["status"] not in STATUSES
                    or type(row["elapsed_seconds"]) not in (int, float) or not math.isfinite(row["elapsed_seconds"])
                    or not prior <= row["elapsed_seconds"] <= end - start + .001):
                raise ValueError("Caller HTTP event invalid")
            prior = row["elapsed_seconds"]
        sequences.add(sequence)
        closed = (any(r["stage"] == "completion" and r["status"] == 502 for r in event["http"])
                  and "relay_provider_connection_closed" in event["diagnostics"])
        result[identity] = {"sequence": sequence, "outcome": event["outcome"], "http": event["http"],
                            "diagnostics": event["diagnostics"], "duration_seconds": round(end - start, 6),
                            "completion_502_with_relay_connection_closure": closed}
    return result
