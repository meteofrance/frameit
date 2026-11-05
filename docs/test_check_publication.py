"""Compact regression cases for the public documentation boundary."""

import tempfile
import unittest
import zlib
import importlib.util
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from check_publication import check_artifact, check_text


class PublicationBoundaryTests(unittest.TestCase):
    def test_local_links_resolve_relative_encoded_downloads_and_fragments(self):
        from check_publication import check_local_links

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'guide').mkdir()
            (root / 'downloads').mkdir()
            (root / 'downloads/data #1.nc').write_bytes(b'instructional download')
            (root / 'symbol.svg').write_text('<svg/>')
            (root / 'index.html').write_text('''
                <h1 id="top">Native SFX.TG1P1; C0/C1; schema 2.</h1>
                <a href="guide/?highlight=units#native%20levels">Guide</a>
                <a href="downloads/data%20%231.nc" download>Download</a>
                <img src="/symbol.svg"><a href="#top">Top</a>
                <a href="https://example.org/unavailable#id">External</a>
                <a href="//example.org/topic">Remote</a>
                <a href="mailto:author@example.org">Author</a>
            ''')
            (root / 'guide/index.html').write_text('''
                <h1 id="native levels">Levels</h1>
                <a href="../index.html#top">Start</a><a href="?q=native">Search</a>
            ''')
            self.assertEqual(check_local_links(root), [])
            for target in ('downloads/data #1.nc', 'symbol.svg', 'guide/index.html'):
                with self.subTest(target=target):
                    path = root / target
                    content = path.read_bytes()
                    path.unlink()
                    self.assertTrue(check_local_links(root))
                    path.write_bytes(content)
            (root / 'guide/index.html').write_text('<h1 id="different">Levels</h1>')
            self.assertTrue(check_local_links(root))

    def test_local_links_reject_missing_assets_anchors_and_nonportable_paths(self):
        from check_publication import check_local_links

        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root = parent / 'html'
            root.mkdir()
            (parent / 'private.txt').write_text('not a published artifact')
            for link in ('<a href="missing.html">Missing</a>',
                         '<a href="#absent">Absent anchor</a>',
                         '<img src="missing.svg">', '<script src="missing.js"></script>',
                         '<link href="missing.css" rel="stylesheet">', '<img src="">',
                         '<a href="../private.txt">Outside</a>',
                         '<a href="file:///private.txt">Local machine</a>',
                         '<a href="http://[invalid">Malformed URL</a>'):
                with self.subTest(link=link):
                    (root / 'index.html').write_text(link)
                    self.assertTrue(check_local_links(root))

    def test_first_run_and_quick_start_have_different_roles(self):
        source = Path(__file__).parent / 'source/getting_started'
        self.assertTrue((source / 'first_run.rst').is_file())
        first = (source / 'first_run.rst').read_text()
        quick = (source / 'quick_start.rst').read_text()
        self.assertTrue(first.startswith('Your first run\n'))
        self.assertTrue(quick.startswith('Quick start\n'))
        self.assertIn('testing.documentation_example', first)
        self.assertIn('run.name', first)
        self.assertIn('output.directory', first)
        self.assertIn('literalinclude:: ../../../src/frameit/templates/arome-fixed-scalar.yaml', first)
        self.assertNotIn('testing.documentation_example', quick)
        self.assertIn('frameit init mesonh --tracking fixed_box --output region.yaml', quick)
        self.assertIn('frameit run region.yaml', quick)

    def test_schema_upgrade_page_is_not_public_content(self):
        self.assertTrue(check_text(Path('topic.rst'),
                                  'See getting_started/upgrading_to_v2.html'))

    def test_plotting_references_fail_publication(self):
        for text in ('See visualization_tools/rotate_polar_axes.html',
                     'from frameit.viz import setup_geodesic_polar_ax'):
            with self.subTest(text=text):
                self.assertTrue(check_text(Path('topic.rst'), text))

    def test_brand_assets_require_local_valid_font_independent_svg(self):
        from check_publication import check_brand_assets

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            (source / 'conf.py').write_text(
                "html_logo = '_static/logo/wordmark.svg'\n"
                "html_favicon = '_static/logo/symbol.svg'\n")
            self.assertEqual(len(check_brand_assets(source)), 2)
            folder = source / '_static/logo'
            folder.mkdir(parents=True)
            good = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 30 10"><path d="M0 0h10v10z"/></svg>'
            (folder / 'wordmark.svg').write_text(good)
            (folder / 'symbol.svg').write_text(good)
            self.assertEqual(check_brand_assets(source), [])
            for bad in ('<svg', good.replace('<path', '<text>FrameIt</text><path'),
                        good.replace('<path', '<script>alert(1)</script><path'),
                        good.replace('<path', '<path onload="alert(1)"'),
                        good.replace('<path', '<use href="https://example.org/logo.svg"/><path'),
                        good.replace('<path', '<style>@font-face {src:url(font.woff)}</style><path'),
                        good.replace('30 10', '0 10')):
                with self.subTest(bad=bad):
                    (folder / 'wordmark.svg').write_text(bad)
                    self.assertTrue(check_brand_assets(source))
            (folder / 'wordmark.svg').write_text(good)
            artifact = source / 'html'
            self.assertTrue(check_brand_assets(source, artifact))
            (artifact / '_static').mkdir(parents=True)
            for name in ('wordmark.svg', 'symbol.svg'):
                (artifact / '_static' / name).write_text(good)
            self.assertEqual(check_brand_assets(source, artifact), [])

    @unittest.skipUnless(importlib.util.find_spec('fontTools') and shutil.which('fc-match'),
                         'Logo regeneration needs optional FontTools and the exact local typeface')
    def test_outlined_wordmark_preserves_composition_and_source(self):
        root = Path(__file__).resolve().parent
        master = root / 'source/_static/logo/frameit_logo_vector.svg'
        family, font = subprocess.check_output([
            'fc-match', '-f', '%{family}\n%{file}', 'simpletix'], text=True).splitlines()
        if family != 'simpletix':
            self.skipTest('Logo regeneration needs the exact Simpletix face')
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'outlined.svg'
            before = master.read_bytes()
            result = subprocess.run([sys.executable, str(root / 'outline_logo.py'),
                                     '--font', font, '--output', str(destination)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(master.read_bytes(), before)
            for line in destination.read_text().splitlines():
                self.assertEqual(line, line.rstrip())
            svg = ET.parse(destination).getroot()
            self.assertEqual(svg.get('viewBox'), '0 0 2172 724')
            self.assertEqual((svg.get('width'), svg.get('height')), ('2172', '724'))
            self.assertFalse(svg.findall('.//{http://www.w3.org/2000/svg}text'))
            wordmark = svg.find("{http://www.w3.org/2000/svg}g[@id='outlined-wordmark']")
            self.assertIsNotNone(wordmark)
            self.assertEqual(len(wordmark), 7)
            self.assertEqual([p.get('fill').lower() for p in wordmark],
                             ['#00978f'] + ['#021633']*4 + ['#ec7600']*2)
            self.assertTrue(all('rotate(' not in p.get('transform') for p in wordmark))

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
            (root / 'index.html').write_text('<a href="missing.html">Broken</a>')
            self.assertTrue(check_artifact(root))
            (root / 'index.html').write_text('<h1>Current user topics</h1>')
            for name, content in (("fa_epygram_c1.html", "A hidden orphan page"),
                                  ("visualization_tools.html", "A stale plotting page"),
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
