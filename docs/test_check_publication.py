"""Compact regression cases for the public documentation boundary."""

import tempfile
import unittest
import zlib
from pathlib import Path

from check_publication import check_artifact, check_text


class PublicationBoundaryTests(unittest.TestCase):
    def test_native_identities_and_scientific_terms_are_not_roadmap_labels(self):
        self.assertEqual(check_text(Path("topic.rst"),
            "Native C0/C1, quintic C2 smoothness, SFX.TG1P1 and SFX.WG1P1; schema 2."), [])
        for text in ("see FA P4 spectral notes", "EPyGrAM C1 qualification",
                     ".. literalinclude:: ../../../src/frameit/testing/catalogs/fa_c1.yaml",
                     ".. include:: ../../development/fa/fa_contracts_history.rst"):
            with self.subTest(text=text):
                self.assertTrue(check_text(Path("topic.rst"), text))

    def test_stale_or_hidden_records_and_inventory_entries_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "_sources").mkdir()
            (root / "_sources/index.rst.txt").write_text("Current user topics\n")
            (root / "index.html").write_text("<h1>Current user topics</h1>")
            (root / "searchindex.js").write_text("Search.setIndex({})")
            header = b"# Sphinx inventory version 2\n# Project: FrameIt\n# Version: 1.1.0\n# zlib\n"
            (root / "objects.inv").write_bytes(
                header + zlib.compress(b"index std:doc 1 index.html -\n"))
            self.assertEqual(check_artifact(root), [])
            for name, content in (("fa_epygram_c1.html", "A hidden orphan page"),
                                  ("_sources/copied.rst.txt", "Frozen developer evidence"),
                                  ("searchindex.js", "user_guide/fa_epygram_c4")):
                with self.subTest(name=name):
                    path = root / name
                    previous = path.read_bytes() if path.exists() else None
                    path.write_text(content)
                    self.assertTrue(check_artifact(root))
                    if previous is None:
                        path.unlink()
                    else:
                        path.write_bytes(previous)
            (root / "objects.inv").write_bytes(header + zlib.compress(
                b"user_guide/fa_epygram_c3 std:doc 1 user_guide/fa_epygram_c3.html -\n"))
            self.assertTrue(check_artifact(root))


if __name__ == "__main__":
    unittest.main()
