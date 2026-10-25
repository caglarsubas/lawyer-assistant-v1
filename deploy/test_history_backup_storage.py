import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from review_history_backup import (  # noqa: E402
    MAX_CIPHER,
    MAX_PLAIN,
    HistoryVault,
    decode_snapshot,
    read_blob,
)


class HistoryStorageContracts(unittest.TestCase):
    def test_unsafe_links_permissions_and_oversized_blobs_are_refused(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name).resolve()
            root.chmod(0o700)
            path = root / "invented.bundle"
            path.write_bytes(b"invented encrypted bytes")
            path.chmod(0o600)
            self.assertEqual(read_blob(path), b"invented encrypted bytes")
            linked = root / "linked.bundle"
            linked.symlink_to(path)
            with self.assertRaises(OSError):
                read_blob(linked)
            linked.unlink()
            os.link(path, linked)
            with self.assertRaises(ValueError):
                read_blob(path)
            linked.unlink()
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                read_blob(path)
            path.chmod(0o600)
            with path.open("r+b") as stream:
                stream.truncate(MAX_CIPHER + 1)
            with self.assertRaises(ValueError):
                read_blob(path)

    def test_duplicate_noncanonical_and_oversized_snapshots_are_refused(self):
        for raw in (b'{"schema":"a","schema":"b"}', b'{"schema": "unknown"}', b"x" * (MAX_PLAIN + 1)):
            with self.subTest(bytes=len(raw)), self.assertRaises(ValueError):
                decode_snapshot(raw)

    def test_untrusted_journal_is_refused_before_any_key_or_storage_access(self):
        with self.assertRaises(ValueError):
            HistoryVault(object(), "/absent", "/absent", "/absent", "/absent")


if __name__ == "__main__":
    unittest.main()
