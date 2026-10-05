"""The restore boundary must reject dangerous or destructive archive shapes."""

import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from volume_archive import invalidate_restored_publication, require_empty, safe_member


class RestoreBoundaryTests(unittest.TestCase):
    def test_restore_invalidates_old_publication_epoch_but_retains_reviews(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            epoch = target / "publication-epoch"
            epoch.write_text("historical-permission-epoch")
            records = target / "release-authorizations"
            records.mkdir()
            saved = records / "review.json"
            saved.write_text("retained private review")
            with patch("volume_archive.ROOTS", {"documents": target}):
                invalidate_restored_publication()
                invalidate_restored_publication()
            self.assertFalse(epoch.exists())
            self.assertEqual(saved.read_text(), "retained private review")

    def test_restore_refuses_symlinked_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            actual = target / "retain"
            actual.write_text("retain")
            (target / "publication-epoch").symlink_to(actual)
            with patch("volume_archive.ROOTS", {"documents": target}), self.assertRaises(ValueError):
                invalidate_restored_publication()
            self.assertEqual(actual.read_text(), "retain")

    def test_rejects_traversal_and_unknown_volume(self):
        for name in ("/etc/shadow", "documents/../../etc/shadow", "unexpected/file", ""):
            with self.subTest(name=name), self.assertRaises(ValueError):
                safe_member(tarfile.TarInfo(name))

    def test_rejects_links_and_devices(self):
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE, tarfile.FIFOTYPE):
            member = tarfile.TarInfo("documents/payload")
            member.type = kind
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                safe_member(member)

    def test_accepts_regular_document_and_bounded_manifest(self):
        safe_member(tarfile.TarInfo("documents/original.encrypted"))
        safe_member(tarfile.TarInfo("public_sources/package/manifest.json"))
        manifest = tarfile.TarInfo("manifest.json")
        manifest.size = 65537
        with self.assertRaises(ValueError):
            safe_member(manifest)

    def test_does_not_overwrite_nonempty_target(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            with patch("volume_archive.ROOTS", {"documents": target}):
                require_empty()
                original = target / "existing.txt"
                original.write_text("retain me")
                with self.assertRaises(ValueError):
                    require_empty()
                self.assertEqual(original.read_text(), "retain me")

    def test_empty_graph_scaffolding_is_allowed_but_a_release_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            (target / 'publication.lock').touch()
            (target / '.install.lock').touch()
            (target / 'releases').mkdir()
            with patch('volume_archive.ROOTS', {'graphs': target}):
                require_empty()
                (target / 'releases' / 'existing').mkdir()
                with self.assertRaises(ValueError):
                    require_empty()

    def test_nonempty_or_symlinked_graph_lock_is_not_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            lock = target / 'publication.lock'
            lock.write_text('existing data')
            with patch('volume_archive.ROOTS', {'graphs': target}):
                with self.assertRaises(ValueError):
                    require_empty()
                lock.unlink()
                lock.symlink_to('/dev/null')
                with self.assertRaises(ValueError):
                    require_empty()


if __name__ == "__main__":
    unittest.main()
