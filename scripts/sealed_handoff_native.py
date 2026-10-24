"""Disposable native fixture worker. Not a provider route or runtime installer.

An external controller must freeze the candidate, create and guard new ext4
volumes, remove writers before mounting readers read-only, and supply approvals
and volume bindings independently. No trust material is read from a bundle.
"""

import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import artifact_store as a
import sealed_handoff_qualification as q
import sealed_relay_handoff as relay
import sealed_volume as v
from signed_provider_contract import decode, sha


def save(path, value):
    v.write_new(Path(path), a.canonical(value))


def output(value):
    print(json.dumps(value), flush=True)


def reject_case(name, call):
    try:
        call()
    except (ValueError, OSError):
        return {"id": name, "expected": "rejected", "observed": "rejected"}
    return {"id": name, "expected": "rejected", "observed": "unexpected-success"}


def main(mode):
    if mode == "prepare":
        uid, gid = int(sys.argv[2]), int(sys.argv[3])
        for mount in ("source", "bundle", "imported", "restored", "control", "targets", "scratch"):
            path = Path("/" + mount)
            if list(path.iterdir()):
                raise ValueError("Fresh empty volume required")
        source = Path("/source")
        large = q.write_large(source / "new-model")
        index = q.make_store(source / "model", large=large)
        approvals = q.prepare_small(source / "bundles")
        for mount in ("source", "bundle", "imported", "restored", "control", "targets", "scratch"):
            root = Path("/" + mount)
            for parent, _, files in os.walk(root, topdown=False, followlinks=False):
                for name in files:
                    path = Path(parent) / name
                    if not path.is_symlink() and path.lstat().st_uid == 0:
                        path.chmod(0o600)
                    os.chown(path, uid, gid, follow_symlinks=False)
                os.chmod(parent, 0o700)
                os.chown(parent, uid, gid)
        mountinfo = Path("/proc/self/mountinfo").read_text().splitlines()
        filesystems = {name: next(line.split(" - ", 1)[1].split()[0] for line in mountinfo
                                 if line.split()[4] == "/" + name)
                       for name in ("source", "bundle", "imported", "restored", "control", "targets", "scratch")}
        output({"model_index": index, "small_approvals": approvals, "tensor_count": 0, "filesystems": filesystems,
                "fresh_seed": q.POLICY["fresh_seed"], "bytes_written": large["size"], "fsynced": True})
        return

    packet = json.loads(Path("/controller/operator-packet.json").read_text())
    if mode == "export":
        journal = v.Journal.create(Path("/control/control.sqlite"))
        result = v.export_bundle(Path("/source/model"), Path("/bundle"), packet["model_index"]["manifest"])
        rows = q.run_transfer_cases(Path("/source/bundles"), Path("/targets"), journal,
                                    packet["small_approvals"], packet["binding_prefix"])
        small_op = q.operation("T01_import")
        small_binding = sha((packet["binding_prefix"] + "T01_import").encode())
        rows.append(reject_case("S01_writable_seal", lambda: v.seal(Path("/targets/T01_import"), journal, small_op, small_binding)))
        replay = Path("/targets/replay")
        replay.mkdir(mode=0o700)
        rows.append(reject_case("S02_operation_replay", lambda: v.import_bundle(
            Path("/source/bundles/T01_import"), replay, journal, small_op,
            packet["small_approvals"]["T01_import"]["bundle_index_sha256"], small_binding)))
        nonce_root = Path("/targets/nonce-case")
        nonce_root.mkdir(mode=0o700)
        v.import_bundle(Path("/source/bundles/T01_import"), nonce_root, journal, q.operation("nonce-crash"),
                        packet["small_approvals"]["T01_import"]["bundle_index_sha256"], sha(b"fixture-nonce-volume"))
        save("/control/transfer-cases.json", rows)
        save("/control/export-result.json", result)
        output({"export": result, "cases": rows})
        return

    journal = v.Journal(Path("/control/control.sqlite"))
    if mode in {"copy-crash", "rename-crash"}:
        root = Path("/scratch") / mode
        root.mkdir(mode=0o700)

        def crash(stage):
            if stage == ("copied_blob" if mode == "copy-crash" else "renamed"):
                os._exit(37 if mode == "copy-crash" else 38)

        v.import_bundle(Path("/source/bundles/T01_import"), root, journal, q.operation(mode),
                        packet["small_approvals"]["T01_import"]["bundle_index_sha256"], sha(mode.encode()), checkpoint=crash)
        raise AssertionError("Declared crash did not occur")

    if mode == "recovery":
        before = sha(Path("/control/control.sqlite").read_bytes())
        rows = []
        for name, case in (("copy-crash", "S03_copy_crash"), ("rename-crash", "S04_rename_crash")):
            state = journal.recover(q.operation(name))
            orphan = bool(list((Path("/scratch") / name).glob("snapshot-*")))
            okay = state["state"] == "copying" and state["events"] == ["copying"] and orphan == (name == "rename-crash")
            rows.append({"id": case, "expected": "quarantined", "observed": "quarantined" if okay else "invalid",
                         "complete_orphan_present": orphan, "automatic_repair_or_replay": state["automatic_repair_or_replay"]})
        output({"cases": rows, "control_bytes_unchanged": before == sha(Path("/control/control.sqlite").read_bytes())})
        return

    if mode == "import":
        result = v.import_bundle(Path("/bundle/bundle"), Path("/imported"), journal, packet["import_operation"],
                                 packet["approved_index_sha256"], packet["import_binding"])
        save("/control/import-result.json", result)
        output(result)
        return

    if mode == "nonce-crash":
        frame = json.loads(Path("/control/nonce-frame.json").read_text())
        expected, keys = q.public_receiver(frame["context"])

        def crash(stage):
            if stage == "reserved_nonce":
                os._exit(39)

        relay.consume(relay.unb64(frame["wire_base64"]), Path("/targets/nonce-case"), journal, expected,
                      key_for=keys.get, resolve_pin=lambda: decode(expected.pin_bytes),
                      clock=lambda: frame["context"]["now"], checkpoint=crash)
        raise AssertionError("Declared nonce crash did not occur")

    if mode == "sign":
        imported = v.seal(Path("/imported"), journal, packet["import_operation"], packet["import_binding"])
        fixture = q.SigningFixture(journal, packet["import_operation"], packet["import_binding"], imported["record"]["manifest_digest"])
        wire = fixture.issue(Path("/imported"))
        forwarded = relay.relay_bytes(wire)
        result = fixture.consume(forwarded, Path("/imported"))
        frame = {"context": fixture.public_context(), "wire_base64": relay.b64(wire), "wire_sha256": sha(wire), "record": imported["record"]}
        save("/control/import-frame.json", frame)
        small_binding = sha((packet["binding_prefix"] + "T01_import").encode())
        small = v.seal(Path("/targets/T01_import"), journal, q.operation("T01_import"), small_binding)
        cases = q.run_handoff_cases(Path("/targets/T01_import"), journal, q.operation("T01_import"), small_binding, small["record"]["manifest_digest"])
        nonce = v.seal(Path("/targets/nonce-case"), journal, q.operation("nonce-crash"), sha(b"fixture-nonce-volume"))
        nf = q.SigningFixture(journal, q.operation("nonce-crash"), sha(b"fixture-nonce-volume"), nonce["record"]["manifest_digest"])
        nw = nf.issue(Path("/targets/nonce-case"))
        save("/control/nonce-frame.json", {"context": nf.public_context(), "wire_base64": relay.b64(nw), "record": nonce["record"]})
        child = subprocess.run([sys.executable, __file__, "nonce-crash"], capture_output=True, timeout=10, check=False)
        if child.returncode != 39 or child.stdout or child.stderr:
            raise ValueError("Nonce crash did not match frozen checkpoint")
        reopened = v.Journal(Path("/control/control.sqlite"))
        nonce_state = reopened.recover(q.operation("nonce-crash"))
        replay = reject_case("S05_nonce_crash", lambda: nf.consume(nw, Path("/targets/nonce-case")))
        replay.update(expected="burned", observed="burned" if replay["observed"] == "rejected" and nonce_state["nonce_counts"] == {"reserved": 1} else "invalid")
        cases["cases"].append(replay)
        save("/control/signed-cases.json", cases)
        output({"import_seal": imported, "handoff": result, "opaque_exact_bytes": wire == forwarded,
                "frame": frame, "cases": cases, "forbidden_execution_resolver_calls": fixture.calls.count("forbidden_execution_resolver")})
        return

    if mode == "restore":
        result = v.import_bundle(Path("/bundle/bundle"), Path("/restored"), journal, packet["restore_operation"],
                                 packet["approved_index_sha256"], packet["restore_binding"], purpose="restore", parent=packet["import_operation"])
        denied = Path("/scratch/revoked-restore")
        denied.mkdir(mode=0o700)
        row = reject_case("S08_revoked_parent_restore", lambda: v.import_bundle(
            Path("/source/bundles/T01_import"), denied, journal, q.operation("revoked-restore"),
            packet["small_approvals"]["T01_import"]["bundle_index_sha256"], sha(b"revoked-restore"),
            purpose="restore", parent=q.operation("T01_import")))
        output({"restore": result, "cases": [row]})
        return

    if mode == "final":
        restored = v.seal(Path("/restored"), journal, packet["restore_operation"], packet["restore_binding"])
        prior = journal.get(packet["import_operation"])
        same = restored["record"]["content_sha256"] == prior["record"]["content_sha256"]
        fresh = restored["record"]["generation_id"] != prior["record"]["generation_id"]
        parent = restored["record"]["parent_operation"] == packet["import_operation"]
        row = {"id": "S06_restore_generation", "expected": "verified", "observed": "verified" if same and fresh and parent else "invalid"}
        frame = json.loads(Path("/control/import-frame.json").read_text())
        expected, keys = q.public_receiver(frame["context"])
        expected = replace(expected, operation_id=packet["restore_operation"], volume_binding_sha256=packet["restore_binding"])
        denied = reject_case("S07_prior_handoff_restore", lambda: relay.consume(
            relay.unb64(frame["wire_base64"]), Path("/restored"), journal, expected, key_for=keys.get,
            resolve_pin=lambda: decode(expected.pin_bytes), clock=lambda: frame["context"]["now"]))
        fixture = q.SigningFixture(journal, packet["restore_operation"], packet["restore_binding"], restored["record"]["manifest_digest"])
        raw = fixture.issue(Path("/restored"))
        result = fixture.consume(relay.relay_bytes(raw), Path("/restored"))
        retained = {"context": fixture.public_context(), "wire_base64": relay.b64(raw), "wire_sha256": sha(raw), "record": restored["record"]}
        output({"restore_seal": restored, "cases": [row, denied], "frame": retained, "handoff": result,
                "generation_fresh": fresh, "content_exact": same, "parent_retained": parent,
                "forbidden_execution_resolver_calls": fixture.calls.count("forbidden_execution_resolver")})
        return
    raise ValueError("Unknown disposable phase")


if __name__ == "__main__":
    main(sys.argv[1])
