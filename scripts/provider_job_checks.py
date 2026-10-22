"""Independent frozen-source checks for disposable real-model research products."""

import hashlib

from app.evidence_prompt import measure_prompt

WORKLOADS = ("short-txt-v1", "mixed-formats-v1", "quote-selection-v1", "quote-volume-v1")
QUESTION = "SYNTHETIC payment odeme evidence"

REJECTION_CODES = {'Review state changed': 'product_review_state_changed', 'Source version not retained': 'product_source_version_not_retained', 'Actual provider use not established': 'product_actual_provider_use_not_established', 'Ambiguous context selection': 'product_ambiguous_context_selection', 'Evidence inventory differs': 'product_evidence_inventory_differs', 'Invalid source span': 'product_invalid_source_span', 'Evidence differs from frozen original passage': 'product_evidence_differs_from_frozen_original_passage', 'Source identity differs': 'product_source_identity_differs', 'Evidence hash differs': 'product_evidence_hash_differs', 'Excerpt boundaries differ': 'product_excerpt_boundaries_differ', 'Measured context exceeds declared budget': 'product_measured_context_exceeds_declared_budget', 'Prompt seal differs': 'product_prompt_seal_differs', 'Coverage counts differ': 'product_coverage_counts_differ', 'Document coverage differs': 'product_document_coverage_differs', 'Claim grounding failed': 'product_claim_grounding_failed', 'Legal coverage limitation lost': 'product_legal_coverage_limitation_lost'}

class ProductRejected(ValueError):
    def __init__(self, message):
        self.code = REJECTION_CODES.get(message, "product_unverified")
        super().__init__(self.code)


def check(condition, message):
    if not condition:
        raise ProductRejected(message)


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def verify_product(product, sources, context_limit, *, question=QUESTION, require_claims=True):
    """Reject mismatched source versions, spans, budgets or unsupported quotations."""
    check(product["status"] == "needs_review", "Review state changed")
    check(product["snapshots"]["sources"] == {d["id"]: d["revision"] for d in sources}, "Source version not retained")
    check(product["snapshots"]["provider"] in {"local-provider-validated-quotes", "approved-laptop-tunnel-validated-quotes"},
          "Actual provider use not established")
    originals = {p["id"]: (d, p) for d in sources for p in d["passages"]}
    evidence = {p["id"]: p for p in product["evidence"]}
    manifest = product["context_pack"]
    records = {p["passage_id"]: p for p in manifest["selected"]}
    check(len(evidence) == len(product["evidence"]) == len(records) == len(manifest["selected"]) > 0,
          "Ambiguous context selection")
    check(set(records) == set(evidence), "Evidence inventory differs")
    for identity, excerpt in evidence.items():
        source, original = originals[identity]
        record = records[identity]
        start, end = record["excerpt_start"], record["excerpt_end"]
        check(type(start) is int and type(end) is int and 0 <= start < end <= len(original["text"]), "Invalid source span")
        check(excerpt["text"] == original["text"][start:end], "Evidence differs from frozen original passage")
        check(record["document_id"] == source["id"] == excerpt["document_id"]
              and record["document_revision"] == source["revision"]
              and record["document_sha256"] == source["sha256"], "Source identity differs")
        check(record["original_text_sha256"] == original["text_sha256"] == digest(original["text"])
              and record["excerpt_text_sha256"] == digest(excerpt["text"])
              and record["full_passage_length"] == len(original["text"]), "Evidence hash differs")
        check((excerpt["excerpt_start"], excerpt["excerpt_end"], excerpt["full_passage_length"]) ==
              (start, end, len(original["text"])), "Excerpt boundaries differ")
    measured = measure_prompt(question, product["evidence"])
    check(manifest["prompt"] == measured and measured["total_upper_bound_units"] <= context_limit,
          "Measured context exceeds declared budget")
    check(product["snapshots"]["context_pack"]["messages_sha256"] == measured["messages_sha256"], "Prompt seal differs")
    inventory = manifest["inventory"]
    check(inventory["input_passages"] == len(originals) and inventory["selected_passages"] == len(evidence)
          and inventory["omitted_passages"] == len(originals) - len(evidence), "Coverage counts differ")
    check(inventory["selected_documents"] == len({p["document_id"] for p in records.values()}), "Document coverage differs")
    check((bool(product["claims"]) or require_claims is False) and all(c["review_status"] == "pending" and c["evidence_ids"] and all(
        ref in evidence and c["text"] in evidence[ref]["text"] for ref in c["evidence_ids"])
        for c in product["claims"]), "Claim grounding failed")
    check("legal_corpus_unqualified" in product["critical_gaps"] and bool(product["coverage"]["gaps"]),
          "Legal coverage limitation lost")
    return {"context_units": measured["total_upper_bound_units"], **{k: inventory[k] for k in
            ("input_passages", "selected_passages", "omitted_passages", "shortened_passages", "selected_documents")}}
