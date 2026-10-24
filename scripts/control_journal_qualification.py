"""Fresh synthetic control-state cases; no private inputs, real keys or inference."""

import os
import shutil
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from threading import Barrier

import artifact_store as a
import sealed_control_journal as c
from sealed_handoff_qualification import operation

CASES = [("C01_separate_anchor", "aligned"), ("C02_readonly_history", "unchanged"),
         ("C03_atomic_descendant_revocation", "revoked"), ("C04_branch_isolation", "isolated"),
         ("C05_new_descendant", "rejected"), ("C06_prepare_revoked", "rejected"),
         ("C07_seal_revoked", "rejected"), ("C08_reserve_revoked", "rejected"),
         ("C09_consume_revoked", "rejected"), ("C10_repeat_revoke", "unchanged"),
         ("C11_cycle_tamper", "rejected"), ("C12_anchor_rollback", "rejected"),
         ("C13_database_rollback", "rejected"), ("C14_exact_backup_nonce", "preserved"),
         ("C15_stale_backup", "rejected"), ("C16_foreign_journal", "rejected"),
         ("C17_wrong_backup_hash", "rejected"), ("C18_corrupt_anchor", "rejected"),
         ("C19_corrupt_database", "rejected"), ("C20_pending_read", "rejected"),
         ("C21_before_commit_crash", "rolled_back"), ("C22_commit_anchor_gap", "retained"),
         ("C23_after_anchor_crash", "retained"), ("C24_nonce_commit_gap", "burned"),
         ("C25_restore_revoke_race", "blocked"), ("C26_forked_database_race", "single_writer"),
         ("C27_depth_bound", "rejected"), ("C28_count_bound", "rejected"),
         ("C29_hot_journal_read", "rejected"), ("C30_torn_anchor", "rejected"),
         ("C31_missing_anchor", "rejected"), ("C32_colocated_anchor", "rejected")]
BACKUP_CASES = {"C14_exact_backup_nonce", "C15_stale_backup", "C16_foreign_journal", "C17_wrong_backup_hash"}
POLICY = {"schema": "control-journal-qualification-v1", "cases": [{"id": n, "expected": e} for n, e in CASES],
          "max_operations": 512, "max_depth": 32, "max_events": 8192, "max_nonces": 8192, "max_commits": 8192,
          "lock_seconds": 2, "crash_points": ["before_commit", "committed_unanchored", "anchored"],
          "attempts_per_native_case": 1, "native_model_performance_retested": False,
          "real_trust_confirmed": False, "production_activation": False}


def rejected(call):
    try:
        call()
    except (ValueError, OSError, sqlite3.Error):
        return True
    return False


def child_crash(call, checkpoint):
    pid = os.fork()
    if pid == 0:
        def crash(stage):
            if stage == checkpoint:
                os._exit(61)
        try:
            call(crash)
        except BaseException:
            os._exit(62)
        os._exit(63)
    _, status = os.waitpid(pid, 0)
    if not os.WIFEXITED(status) or os.WEXITSTATUS(status) != 61:
        raise ValueError("Frozen crash checkpoint did not execute")


class HotJournal(c.Journal):
    """Fault-only one-page SQLite cache forces a durable hot rollback journal."""

    @contextmanager
    def connect(self, *, readonly=False):
        with super().connect(readonly=readonly) as db:
            if not readonly:
                db.execute("PRAGMA cache_size=1")
            yield db


class Lab:
    def __init__(self, work, anchors, index, proof):
        self.work, self.anchors, self.index, self.proof = Path(work), Path(anchors), index, proof
        self.index_sha = a.digest(a.canonical(index))

    def journal(self, name):
        dbdir, adir = self.work / name, self.anchors / name
        dbdir.mkdir(mode=0o700)
        adir.mkdir(mode=0o700)
        return c.Journal.create(dbdir / "control.sqlite", adir / "anchor.log")

    def add(self, journal, name, *, parent=None, status="sealed"):
        op = operation(name)
        record = journal.begin(op, self.index, self.index_sha, a.digest(name.encode()),
                               purpose="restore" if parent else "import", parent=parent)
        if status != "copying":
            journal._transition(op, "copying", "prepared")
        if status == "sealed":
            journal._transition(op, "prepared", "sealed", self.proof)
        return record

    def open(self, journal, *, checkpoint=None):
        return c.Journal(journal.path, journal.anchor.path, journal.journal_id, checkpoint=checkpoint)

    def hashes(self, journal):
        return a.digest(journal.path.read_bytes()), a.digest(journal.anchor.path.read_bytes())

    def case(self, name):
        if name in BACKUP_CASES:
            raise ValueError("Backup cases require separate read-only phase")
        if name == "C32_colocated_anchor":
            root = self.work / name
            root.mkdir(mode=0o700)
            return "rejected" if rejected(lambda: c.Journal.create(root / "db", root / "anchor")) and not list(root.iterdir()) else "invalid"
        j = self.journal(name)
        root = self.add(j, name + "root")["operation_id"]
        if name == "C01_separate_anchor":
            return "aligned" if j.path.parent != j.anchor.path.parent and self.open(j).get(root)["state"] == "sealed" else "invalid"
        if name == "C02_readonly_history":
            before = self.hashes(j)
            observed = self.open(j).recover(root)
            return "unchanged" if before == self.hashes(j) and observed["events"] == ["copying", "prepared", "sealed"] and not observed["automatic_repair_or_replay"] else "invalid"
        child = self.add(j, name + "child", parent=root)["operation_id"]
        if name in {"C03_atomic_descendant_revocation", "C04_branch_isolation"}:
            leaf = self.add(j, name + "leaf", parent=child, status="prepared")["operation_id"]
            sibling = self.add(j, name + "sibling", parent=root, status="copying")["operation_id"]
            outside = self.add(j, name + "outside")["operation_id"]
            j.reserve_nonce(child, operation(name + "nonce"), a.digest(b"wire"))
            original = j.get(child)
            result = j.revoke(root if name.startswith("C03") else child)
            expected = {root, child, leaf, sibling} if name.startswith("C03") else {child, leaf}
            okay = set(result["affected"]) == expected and all(j.get(n)["state"] == "revoked" for n in expected)
            okay &= j.get(outside)["state"] == "sealed" and j.get(child)["proof"] == original["proof"]
            okay &= j.recover(child)["nonce_counts"] == {"reserved": 1}
            if name.startswith("C04"):
                okay &= j.get(root)["state"] == "sealed" and j.get(sibling)["state"] == "copying"
            return ("revoked" if name.startswith("C03") else "isolated") if okay else "invalid"
        if name in {"C05_new_descendant", "C06_prepare_revoked", "C07_seal_revoked", "C08_reserve_revoked", "C09_consume_revoked", "C10_repeat_revoke"}:
            pending = self.add(j, name + "pending", parent=child, status="copying" if name.startswith("C06") else "prepared")["operation_id"]
            challenge = operation(name + "nonce")
            j.reserve_nonce(child, challenge, a.digest(b"wire"))
            j.revoke(root)
            calls = {"C05_new_descendant": lambda: self.add(j, name + "new", parent=child),
                     "C06_prepare_revoked": lambda: j._transition(pending, "copying", "prepared"),
                     "C07_seal_revoked": lambda: j._transition(pending, "prepared", "sealed", self.proof),
                     "C08_reserve_revoked": lambda: j.reserve_nonce(child, operation(name + "newnonce"), a.digest(b"wire")),
                     "C09_consume_revoked": lambda: j.consume_nonce(child, challenge)}
            if name == "C10_repeat_revoke":
                before = self.hashes(j)
                result = j.revoke(root)
                return "unchanged" if not result["newly_revoked"] and self.hashes(j) == before else "invalid"
            return "rejected" if rejected(calls[name]) else "invalid"
        if name == "C11_cycle_tamper":
            db = sqlite3.connect(j.path)
            row = j.get(root)["record"]
            row.update(purpose="restore", parent_operation=child)
            db.execute("UPDATE operations SET record=? WHERE id=?", (a.canonical(row).decode(), root))
            db.commit()
            db.close()
            return "rejected" if rejected(lambda: self.open(j)) else "invalid"
        if name in {"C12_anchor_rollback", "C13_database_rollback"}:
            saved = j.anchor.path.read_bytes() if name.startswith("C12") else j.path.read_bytes()
            j.reserve_nonce(child, operation(name + "nonce"), a.digest(b"wire"))
            (j.anchor.path if name.startswith("C12") else j.path).write_bytes(saved)
            return "rejected" if rejected(lambda: self.open(j)) else "invalid"
        if name in {"C18_corrupt_anchor", "C19_corrupt_database", "C30_torn_anchor", "C31_missing_anchor"}:
            path = j.path if name.startswith("C19") else j.anchor.path
            if name.startswith("C31"):
                path.unlink()
            elif name.startswith("C30"):
                with path.open("ab") as f:
                    f.write(b'{"torn":')
            else:
                path.write_bytes(b"corrupt-synthetic-control")
            before = path.read_bytes() if path.exists() else None
            refused = rejected(lambda: self.open(j)) and rejected(lambda: c.Journal.reconcile(j.path, j.anchor.path, j.journal_id))
            return "rejected" if refused and (path.read_bytes() if path.exists() else None) == before else "invalid"
        if name in {"C20_pending_read", "C21_before_commit_crash", "C22_commit_anchor_gap", "C23_after_anchor_crash", "C24_nonce_commit_gap", "C29_hot_journal_read"}:
            point = "before_commit" if name in {"C21_before_commit_crash", "C29_hot_journal_read"} else "anchored" if name.startswith("C23") else "committed_unanchored"
            challenge = operation(name + "nonce")
            nonce = name.startswith("C24")
            def interrupted(crash):
                target = HotJournal(j.path, j.anchor.path, j.journal_id, checkpoint=crash) if name == "C29_hot_journal_read" else self.open(j, checkpoint=crash)
                if nonce:
                    target.reserve_nonce(child, challenge, a.digest(b"wire"))
                else:
                    target.revoke(root)
            child_crash(interrupted, point)
            if name in {"C20_pending_read", "C29_hot_journal_read"}:
                before = self.hashes(j)
                refused = rejected(lambda: self.open(j))
                return "rejected" if refused and self.hashes(j) == before else "invalid"
            recovered = c.Journal.reconcile(j.path, j.anchor.path, j.journal_id)
            opened = self.open(j)
            if nonce:
                okay = recovered["action"] == "retained_committed_transaction" and opened.recover(child)["nonce_counts"] == {"reserved": 1}
                return "burned" if okay and rejected(lambda: opened.reserve_nonce(child, challenge, a.digest(b"wire"))) else "invalid"
            desired = "sealed" if point == "before_commit" else "revoked"
            okay = all(opened.get(n)["state"] == desired for n in (root, child))
            okay &= recovered["semantic_mutations_replayed"] == 0
            return ("rolled_back" if point == "before_commit" else "retained") if okay else "invalid"
        if name == "C25_restore_revoke_race":
            barrier = Barrier(2)
            def add():
                barrier.wait()
                return rejected(lambda: self.add(self.open(j), name + "racing", parent=child))
            def revoke():
                barrier.wait()
                self.open(j).revoke(root)
            with ThreadPoolExecutor(max_workers=2) as pool:
                a1, a2 = pool.submit(add), pool.submit(revoke)
                refused, _ = a1.result(), a2.result()
            okay = self.open(j).get(root)["state"] == "revoked"
            if not refused:
                okay &= self.open(j).get(operation(name + "racing"))["state"] == "revoked"
            return "blocked" if okay else "invalid"
        if name == "C26_forked_database_race":
            clone = j.path.parent / "clone.sqlite"
            shutil.copyfile(j.path, clone)
            clone.chmod(0o600)
            barrier = Barrier(2)
            def advance(path, suffix):
                journal = c.Journal(path, j.anchor.path, j.journal_id)
                barrier.wait()
                return not rejected(lambda: journal.reserve_nonce(child, operation(name + suffix), a.digest(b"wire")))
            with ThreadPoolExecutor(max_workers=2) as pool:
                one, two = pool.submit(advance, j.path, "one"), pool.submit(advance, clone, "two")
                wins = [one.result(), two.result()]
            return "single_writer" if sum(wins) == 1 else "invalid"
        if name == "C27_depth_bound":
            current = child
            for depth in range(2, c.MAX_DEPTH):
                current = self.add(j, name + str(depth), parent=current)["operation_id"]
            return "rejected" if rejected(lambda: self.add(j, name + "too-deep", parent=current)) else "invalid"
        if name == "C28_count_bound":
            with j.connect() as db:
                for n in range(c.MAX_OPERATIONS - 2):
                    op = operation(name + str(n))
                    record = {"operation_id": op, "generation_id": operation(name + "gen" + str(n)),
                              "bundle_index_sha256": self.index_sha, "content_sha256": self.index["content_sha256"],
                              "manifest_digest": self.index["manifest"], "volume_binding_sha256": a.digest(op.encode()),
                              "purpose": "import", "parent_operation": None, "production_activation": False}
                    db.execute("INSERT INTO operations VALUES(?,?,?,'copying',NULL)", (op, record["generation_id"], a.canonical(record).decode()))
                    db.execute("INSERT INTO events(operation,event) VALUES(?,'copying')", (op,))
            return "rejected" if rejected(lambda: self.add(j, name + "excess")) else "invalid"
        raise ValueError("Unknown frozen case")

    def prepare_backups(self, destination):
        records = {}
        for name in sorted(BACKUP_CASES):
            j = self.journal(name)
            op = self.add(j, name + "root")["operation_id"]
            nonce = operation(name + "nonce")
            older = destination / (name + "-older.sqlite")
            old = j.backup(older)
            j.reserve_nonce(op, nonce, a.digest(b"wire"))
            j.consume_nonce(op, nonce)
            fresh = destination / (name + "-latest.sqlite")
            latest = j.backup(fresh)
            records[name] = {"journal_id": j.journal_id, "operation": op, "nonce": nonce,
                             "older": old, "latest": latest}
        return records

    def backup_case(self, name, backup_root, packet):
        saved = packet[name]
        path = Path(backup_root) / (name + ("-older.sqlite" if name.startswith("C15") else "-latest.sqlite"))
        approved = saved["older" if name.startswith("C15") else "latest"]["backup_sha256"]
        anchor = self.anchors / name / "anchor.log"
        target = self.work / (name + "-restore")
        target.mkdir(mode=0o700)
        if name.startswith("C17"):
            approved = "f" * 64
        journal_id = operation("foreign-journal") if name.startswith("C16") else saved["journal_id"]
        before = (a.digest(anchor.read_bytes()), a.digest((self.work / name / "control.sqlite").read_bytes()))
        try:
            restored = c.restore_backup(path, target, anchor, approved, journal_id)
        except (ValueError, OSError, sqlite3.Error):
            after = (a.digest(anchor.read_bytes()), a.digest((self.work / name / "control.sqlite").read_bytes()))
            return "rejected" if before == after else "invalid-mutation"
        if name != "C14_exact_backup_nonce":
            return "unexpected-restore"
        j = c.Journal(target / "control.sqlite", anchor, journal_id)
        okay = j.recover(saved["operation"])["nonce_counts"] == {"consumed": 1}
        okay &= rejected(lambda: j.reserve_nonce(saved["operation"], saved["nonce"], a.digest(b"wire")))
        okay &= restored["nonce_or_revocation_reset"] is False
        return "preserved" if okay else "invalid"
