"""One-time invented fixture retention. Never a runtime recovery/provisioning route."""

from dataclasses import asdict

import operator_enrollment_evidence as e
from operator_cold_recovery import KEYS, SCHEMA, ColdPins, identity, inventory
from receipt_provisioning_readiness import fingerprint


def retain(f, selected, target, roots, anchors, package_pin):
    anchors.mkdir(mode=0o700)
    d = selected.adapter.service.reconciler.disposition
    s = d.source.service
    p = s.planner
    stores = {"source": p.source, "journal": p.journal, "candidate": s.readiness.candidate,
              "readiness": s.readiness.reviews.planner.journal, "controls": s.controls.planner.journal,
              "disposition": d.planner.journal}
    if tuple(x.root for x in stores.values()) != roots or f.store.engine.dialect.name != "sqlite":
        e.reject()
    written = set()
    for name, store in stores.items():
        if KEYS[name] not in written:
            e.retain(anchors / KEYS[name], store.key)
            written.add(KEYS[name])
    e.retain(anchors / "handoff.json", e.encode(target.record()))
    e.retain(anchors / "receipt.json", target.receipt_bytes)
    e.retain(anchors / "provenance.json", target.provenance_bytes)
    descriptor = {"schema": SCHEMA, "fixture_scope": "invented_accounts_and_encrypted_metadata_only",
        "stores": {n: {"path": x.root.relative_to(f.root).as_posix(), "identity": list(x.identity),
            "context_id": x.context_id, "scope_sha256": x.scope_sha256, "key_fingerprint": fingerprint(x.key),
            "inventory": inventory(x.root)} for n, x in stores.items()},
        "source_pins": asdict(p.pins), "source_binding": asdict(s.readiness.source.binding),
        "candidate_pins": asdict(s.readiness.candidate_pins), "readiness_binding": asdict(s.readiness.reviews.binding),
        "controls_binding": asdict(s.controls.binding), "disposition_binding": asdict(d.reviews.binding),
        "manifest_sha256": s.manifest_sha256, "profile_id": f.authority.profile_id,
        "profile_sha256": f.authority.marker_sha, "database_identity": list(f.authority.file_identity),
        "firm_id": f.authority.firm_id, "actors": {"preparer": p.preparer, "reviewer": p.reviewer},
        "bindings": dict(f.authority.bindings), "origin": selected.origin, "handoff_sha256": target.sha256,
        "binding_sha256": target.binding_sha256, "receipt_sha256": target.receipt_sha256,
        "provenance_sha256": target.provenance_sha256}
    raw = e.encode(descriptor)
    e.retain(anchors / "controller.json", raw)
    return ColdPins(descriptor_sha256=e.sha(raw), package_manifest_sha256=package_pin, handoff_sha256=target.sha256,
        binding_sha256=target.binding_sha256, profile_sha256=f.authority.marker_sha, profile_id=f.authority.profile_id,
        preparer_id=p.preparer, reviewer_id=p.reviewer, source_id=target.source_id,
        database_identity=f.authority.file_identity, case_identity=identity(f.root), anchors_identity=identity(anchors), origin=selected.origin)
