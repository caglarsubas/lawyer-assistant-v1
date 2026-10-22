"""Opt-in synthetic qualification inside the configured application container.

No Store, database, originals, caller prompts or provider administration are used.
Output is an allowlisted report; credentials and model response bodies never leave
memory. This is a bounded consumer experiment, not a shared-provider benchmark.
"""

import argparse
import hashlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier, Lock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]

from load_metrics import distribution  # noqa: E402

from app.evidence_prompt import measure_prompt  # noqa: E402
from app.provider import Provider, ProviderError  # noqa: E402

MARKER = "lawyer-provider-context-five-callers-v1"
QUESTION = "SENTETİK TEST. İlk kaynaktan yalnızca ilk kısa cümleyi birebir alıntıla; tek claim ve boş summary üret."
TEXT = "SENTETİK TEST: Örnek tutar 100 birimdir."
IDENTITY = ("lawyer-assistant-v1", "org-lawyer", "lawyer-assistant-v1-primary")


class QualificationError(ValueError):
    """Only fixed qualifier codes, never model text, can enter a report."""


def failure_code(error):
    if isinstance(error, QualificationError):
        return str(error)
    if isinstance(error, ProviderError):
        return "provider_rejected_response"
    return "qualification_failed"


def fixture(total_units=None):
    passages = [{"id": "synthetic-first", "text": TEXT}]
    if total_units is not None:
        if type(total_units) is not int or not 3072 <= total_units <= 16385:
            raise ValueError("Unsupported bounded synthetic context")
        # Fixed synthetic ASCII padding; never truncate or select real evidence.
        passages.append({"id": "synthetic-padding", "text": "SYNTHETIC padding."})
        while measure_prompt(QUESTION, passages)["total_upper_bound_units"] < total_units:
            remaining = total_units - measure_prompt(QUESTION, passages)["total_upper_bound_units"]
            room = 6000 - len(passages[-1]["text"].encode())
            if room == 0:
                passages.append({"id": f"synthetic-padding-{len(passages)}", "text": "SYNTHETIC padding."})
                if measure_prompt(QUESTION, passages)["total_upper_bound_units"] > total_units:
                    raise ValueError("Synthetic context cannot meet the exact boundary")
                continue
            passages[-1]["text"] += "x" * min(room, remaining)
        if measure_prompt(QUESTION, passages)["total_upper_bound_units"] != total_units:
            raise ValueError("Synthetic context differs from requested boundary")
    return passages


def validate_quote(content, passages):
    try:
        value = json.loads(content)
    except (ValueError, TypeError, RecursionError):
        raise QualificationError("invalid_json") from None
    if not isinstance(value, dict) or set(value) != {"summary", "claims"}:
        raise QualificationError("invalid_envelope")
    if value["summary"] != "":
        raise QualificationError("nonempty_summary")
    claims = value["claims"]
    if not isinstance(claims, list) or len(claims) != 1:
        raise QualificationError("invalid_cardinality")
    claim = claims[0]
    # Match the product's grounding rule: a complete short source excerpt need
    # not repeat the entire fixture sentence's synthetic label prefix.
    text = claim.get("text") if isinstance(claim, dict) else None
    if (not isinstance(claim, dict) or set(claim) != {"text", "evidence_ids"}
            or claim["evidence_ids"] != [passages[0]["id"]]
            or not isinstance(text, str) or not 8 <= len(text) <= 2000
            or text not in passages[0]["text"] or not text.endswith((".", "!", "?"))):
        raise QualificationError("quote_or_reference_mismatch")


def oversized_guard(settings):
    class NoProbe(Provider):
        calls = 0

        def probe(self):
            self.calls += 1
            raise AssertionError("Over-budget context reached readiness")

    provider = NoProbe(settings)
    try:
        provider.generate(QUESTION, fixture(settings.provider_context_limit + 1))
    except ProviderError as error:
        if str(error) == "Context budget exceeded; reduce selected evidence" and provider.calls == 0:
            return True
    raise ValueError("Over-budget guard did not reject before readiness")


def qualify(settings, expected_model, expected_context, *, provider_type=Provider):
    report = {"schema": MARKER, "status": "failed", "synthetic_only": True,
              "started_at": datetime.now(timezone.utc).isoformat(), "generation_attempts": 0,
              "not_qualified": ["legal correctness or private case approval", "sustained or production capacity",
                                "GPU parallel execution", "end-to-end five-job real-corpus research",
                                "independent fallback, tunnel retention or tokenizer attestation"]}
    stage = "configuration"
    try:
        if ((settings.provider_tenant_id, settings.provider_org_id, settings.provider_key_id) != IDENTITY
                or settings.provider_model != expected_model or settings.provider_context_limit != expected_context
                or type(expected_context) is not int or not 3072 <= expected_context <= 16384):
            raise ValueError("Configured identity or budget differs from declared experiment")
        provider = provider_type(settings)
        probe = provider.probe()
        report["configuration_ready"] = provider.readiness()["configuration_ready"]
        report["transport"] = provider.transport_metadata()
        if not report["configuration_ready"] or probe.get("ready") is not True:
            raise ValueError("Authenticated model metadata unavailable")
        report["model"] = probe["model"]
        report["configured_context_units"] = expected_context
        stage = "oversized_guard"
        report["oversized_rejected_before_readiness"] = oversized_guard(settings)
        stage = "context_boundary"
        passages = fixture(expected_context)
        report["boundary_measurement"] = measure_prompt(QUESTION, passages)
        report["generation_attempts"] += 1
        started = time.monotonic()
        try:
            validate_quote(provider.generate(QUESTION, passages), passages)
            report["boundary_exact_quote_verified"] = True
        except Exception as error:
            report["boundary_exact_quote_verified"] = False
            report["boundary_failure_code"] = failure_code(error)
        report["boundary_seconds"] = round(time.monotonic() - started, 6)
        stage = "five_callers"
        barrier, lock = Barrier(5, timeout=10), Lock()
        counters = {"active": 0, "peak": 0, "attempts": 0}

        def call():
            barrier.wait()
            started = time.monotonic()
            with lock:
                counters["attempts"] += 1
                counters["active"] += 1
                counters["peak"] = max(counters["peak"], counters["active"])
            try:
                passages = fixture()
                validate_quote(provider_type(settings).generate(QUESTION, passages), passages)
                return {"status": "passed", "seconds": round(time.monotonic() - started, 6)}
            except Exception as error:
                # No exception string, upstream URL, prompt or completion is exported.
                return {"status": "failed", "seconds": round(time.monotonic() - started, 6), "failure_code": failure_code(error)}
            finally:
                with lock:
                    counters["active"] -= 1

        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=5) as pool:
            rows = list(pool.map(lambda _: call(), range(5)))
        report.update(generation_attempts=1 + counters["attempts"], caller_counters=counters,
                      five_callers=rows, wave_seconds=round(time.monotonic() - started, 6))
        if (counters != {"active": 0, "peak": 5, "attempts": 5}
                or any(row["status"] != "passed" or row["seconds"] > 120 for row in rows)
                or not report["boundary_exact_quote_verified"]
                or report["boundary_seconds"] > 120):
            raise ValueError("Five callers or per-call budget failed")
        report["caller_seconds"] = distribution([row["seconds"] for row in rows])
        report["status"] = "passed"
    except Exception as error:
        report["failure_stage"] = stage
        report["failure_code"] = failure_code(error)
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-model", required=True)
    parser.add_argument("--expected-context", required=True, type=int)
    parser.add_argument("--execute-synthetic", required=True, action="store_true")
    args = parser.parse_args()
    from app.config import load_settings

    try:
        report = qualify(load_settings(), args.expected_model, args.expected_context)
        # Bind the adapter/envelope/validator actually imported in this runtime.
        root = Path(sys.modules[Provider.__module__].__file__).parent
        report["runtime_code"] = {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                                  for name in ("provider.py", "evidence_prompt.py", "analysis_output_contract.py")}
    except Exception:
        # Settings validation can include sensitive input values in its message.
        report = {"schema": MARKER, "status": "failed", "failure_code": "configuration_or_code_binding_failed"}
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
