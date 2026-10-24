"""Disposable metadata qualification worker, never a runtime installer."""

import json
import os
import sqlite3
import sys
from pathlib import Path

import artifact_store as a
import control_journal_qualification as q
import sealed_handoff_qualification as fixture
import sealed_volume as v


def observe(work, anchors, name):
    database, anchor = work / name / "control.sqlite", anchors / name / "anchor.log"
    result = {"database_sha256": a.digest(database.read_bytes()) if database.exists() else None,
              "anchor_sha256": a.digest(anchor.read_bytes()) if anchor.exists() else None}
    if database.exists():
        db = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            db.execute("PRAGMA query_only=ON")
            result["operation_states"] = dict(db.execute("SELECT state,count(*) FROM operations GROUP BY state"))
            result["nonce_states"] = dict(db.execute("SELECT state,count(*) FROM nonces GROUP BY state"))
            result["history_events"] = db.execute("SELECT count(*) FROM events").fetchone()[0]
            result["audit_commits"] = db.execute("SELECT count(*) FROM audit").fetchone()[0]
            result["readable_without_repair"] = True
        except sqlite3.Error:
            result["readable_without_repair"] = False
        finally:
            db.close()
    result["restore_published"] = (work / (name + "-restore") / "control.sqlite").exists()
    return result


def main(mode):
    if mode == "prepare":
        uid, gid = int(sys.argv[2]), int(sys.argv[3])
        roots = [Path("/" + name) for name in ("fixtures", "work", "anchors", "backups")]
        if any(list(p.iterdir()) for p in roots):
            raise ValueError("Fresh volume roots required")
        info = fixture.make_bundle(Path("/fixtures/bundle"))
        for root in roots:
            for parent, _, files in os.walk(root, topdown=False):
                for name in files:
                    p = Path(parent) / name
                    p.chmod(0o600)
                    os.chown(p, uid, gid)
                os.chmod(parent, 0o700)
                os.chown(parent, uid, gid)
        mountinfo = Path("/proc/self/mountinfo").read_text().splitlines()
        filesystems = {p.name: next(line.split(" - ", 1)[1].split()[0] for line in mountinfo if line.split()[4] == str(p)) for p in roots}
        print(json.dumps({"info": info, "filesystems": filesystems, "synthetic_only": True, "tensor_count": 0}))
        return
    work, anchors, backups = Path("/work"), Path("/anchors"), Path("/backups")
    index = a.strict_json(v.small(Path("/fixtures/bundle/index.json"), readonly=True))
    proof = a.supervised_verify(Path("/fixtures/bundle/store"), index["manifest"], strategy="windowed-pinned")
    lab = q.Lab(work, anchors, index, proof)
    rows = []
    packet = None
    if mode == "control":
        for name, expected in q.CASES:
            if name not in q.BACKUP_CASES:
                observed = lab.case(name)
                rows.append({"id": name, "expected": expected, "observed": observed, "evidence": observe(work, anchors, name)})
        packet = lab.prepare_backups(backups)
        v.write_new(Path("/work/backup-packet.json"), a.canonical(packet))
    elif mode == "restore":
        packet = a.strict_json(v.small(Path("/work/backup-packet.json")))
        for name, expected in q.CASES:
            if name in q.BACKUP_CASES:
                observed = lab.backup_case(name, backups, packet)
                evidence = observe(work, anchors, name)
                if evidence["restore_published"]:
                    db = sqlite3.connect((work / (name + "-restore") / "control.sqlite").resolve().as_uri() + "?mode=ro", uri=True)
                    try:
                        evidence["restored_nonce_states"] = dict(db.execute("SELECT state,count(*) FROM nonces GROUP BY state"))
                    finally:
                        db.close()
                rows.append({"id": name, "expected": expected, "observed": observed, "evidence": evidence})
    else:
        raise ValueError("Unknown disposable phase")
    if any(r["expected"] != r["observed"] for r in rows):
        v.write_new(Path("/work/failed-" + mode + ".json"), a.canonical(rows))
        raise ValueError("Frozen native case failed")
    print(json.dumps({"cases": rows, "fixture_verification": proof, "backup_packet": packet,
                      "private_inputs": False, "provider_requests": 0, "inference_calls": 0,
                      "real_keys_or_trust": False, "production_activation": False}))


if __name__ == "__main__":
    main(sys.argv[1])
