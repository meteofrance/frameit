"""Version navigation and publication readiness, exercised through real HTML."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


DOCS = Path(__file__).resolve().parent


class DocumentationVersionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        cls.source = cls.root / 'source'
        cls.source.mkdir()
        (cls.source / 'conf.py').write_text(
            (DOCS / 'source/conf.py').read_text() + '\nextensions = []\n')
        shutil.copytree(DOCS / 'source/_templates', cls.source / '_templates')
        shutil.copytree(DOCS / 'source/_static', cls.source / '_static')
        (cls.source / 'index.rst').write_text(
            'Documentation\n=============\n\n.. toctree::\n\n   guide/topic\n')
        (cls.source / 'guide').mkdir()
        (cls.source / 'guide/topic.rst').write_text('Topic\n=====\n')
        cls.site = cls.root / 'frameit'
        for channel, output in (
            ('main', cls.site), ('develop', cls.site / 'develop'),
            ('', cls.root / 'standalone'),
        ):
            result = cls.build(channel, output)
            if result.returncode:
                raise AssertionError(result.stdout + result.stderr)

    @classmethod
    def build(cls, channel, output):
        return subprocess.run(
            [sys.executable, '-m', 'sphinx', '-q', '-W', '-b', 'html',
             str(cls.source), str(output)],
            env=dict(os.environ, FRAMEIT_DOCS_CHANNEL=channel),
            capture_output=True, text=True,
        )

    def test_channel_navigation_in_real_html(self):
        from check_doc_versions import check_versions

        self.assertEqual(check_versions(self.site), [])
        for prefix in ('', 'develop/'):
            for page in ('index.html', 'guide/topic.html', 'search.html'):
                html = (self.site / prefix / page).read_text()
                self.assertIn('Stable (main)', html)
                self.assertIn('Development (develop)', html)
                self.assertEqual('docs-development-warning' in html, bool(prefix))
                if prefix:
                    self.assertIn('unreleased', html.lower())

    def test_standalone_build_has_no_cross_version_links(self):
        html = (self.root / 'standalone/index.html').read_text()
        self.assertNotIn('data-docs-channel', html)
        self.assertNotIn('docs-development-warning', html)

    def test_invalid_channel_fails(self):
        result = self.build('typo', self.root / 'invalid')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('FRAMEIT_DOCS_CHANNEL', result.stdout + result.stderr)

    def test_incomplete_site_is_rejected(self):
        from check_doc_versions import check_versions

        self.assertTrue(check_versions(self.root / 'absent'))
        for filename in ('develop/index.html', 'objects.inv', 'develop/searchindex.js'):
            with self.subTest(filename=filename):
                path = self.site / filename
                original = path.read_bytes()
                path.unlink()
                try:
                    self.assertTrue(check_versions(self.site))
                finally:
                    path.write_bytes(original)

    def test_wrong_version_links_or_banner_are_rejected(self):
        from check_doc_versions import check_versions

        path = self.site / 'develop/guide/topic.html'
        original = path.read_text()
        for changed in (
            original.replace('../../index.html', '/index.html'),
            original.replace('../../index.html', 'https://example.org/index.html'),
            original.replace('../../index.html', '../../../index.html'),
            original.replace('docs-development-warning', 'missing-warning'),
            original.replace('Development documentation — unreleased.', 'Welcome.'),
            original.replace('aria-current="true"', 'aria-current="false"'),
            original.replace('data-docs-channel="main"', 'data-docs-channel="typo"'),
        ):
            with self.subTest(change=changed[:80]):
                self.assertNotEqual(changed, original)
                path.write_text(changed)
                try:
                    self.assertTrue(check_versions(self.site))
                finally:
                    path.write_text(original)

    def test_development_named_subdirectory_is_checked(self):
        from check_doc_versions import check_versions

        nested = self.site / 'develop/develop'
        nested.mkdir(exist_ok=True)
        page = nested / 'topic.html'
        page.write_text('<h1>Unversioned page</h1>')
        try:
            self.assertTrue(check_versions(self.site))
        finally:
            page.unlink()

    def test_malformed_link_is_reported_without_crashing(self):
        from check_doc_versions import check_versions

        page = self.site / 'develop/guide/topic.html'
        original = page.read_text()
        page.write_text(original.replace('../../index.html', 'https://[invalid'))
        try:
            self.assertTrue(check_versions(self.site))
        finally:
            page.write_text(original)

    def test_cli_rejects_incomplete_artifact(self):
        result = subprocess.run(
            [sys.executable, str(DOCS / 'check_doc_versions.py'), str(self.root / 'absent')],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
