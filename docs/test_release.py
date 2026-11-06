"""Source-checkout release gates; build only tiny synthetic distribution inputs."""

from datetime import date
from importlib.metadata import PackageNotFoundError
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import unittest
from unittest.mock import patch
import zipfile

import yaml


ROOT = Path(__file__).resolve().parents[1]


class ReleaseTests(unittest.TestCase):
    def test_candidate_metadata_and_source_fallback_agree(self):
        from frameit._version import get_frameit_version

        project = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']
        citation = yaml.safe_load((ROOT / 'CITATION.cff').read_text())
        self.assertEqual(project['version'], '2.0.0rc1')
        self.assertEqual(citation['version'], project['version'])
        self.assertEqual(citation['date-released'], date(2026, 11, 6))
        self.assertEqual(project['requires-python'], '>=3.13,<3.14')
        with patch('frameit._version.version', side_effect=PackageNotFoundError('frameit')):
            self.assertEqual(get_frameit_version(), project['version'])

    def test_distributions_keep_runtime_assets_but_exclude_private_payloads_and_indexes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('pyproject.toml', 'README.md', 'LICENSE', 'MANIFEST.in',
                         'CITATION.cff', 'CHANGELOG.md'):
                if (ROOT / name).exists():
                    shutil.copyfile(ROOT / name, root / name)
            package = root / 'src/frameit'
            package.mkdir(parents=True)
            (package / '__init__.py').write_text('')
            for relative in ('templates/arome.yaml', 'presets/AROME/model_name_map.yaml',
                             'testing/catalogs/science.yaml', 'testing/recipes/ci.yaml',
                             'testing/ci_dataset/manifest.json',
                             'testing/documentation_example.py', 'testing/datasets.py'):
                path = package / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / 'src/frameit' / relative, path)
            private = package / 'testing/ci_dataset/MNH'
            private.mkdir(parents=True)
            for suffix in ('.nc', '.grib', '.grib.5b7b6.idx'):
                (private / ('private' + suffix)).write_bytes(b'synthetic private-payload marker')
            stale = root / 'src/frameit.egg-info/SOURCES.txt'
            stale.parent.mkdir()
            stale.write_text('\n'.join(str(p.relative_to(root)) for p in private.iterdir()))
            result = subprocess.run([sys.executable, '-c',
                "from setuptools.build_meta import build_sdist, build_wheel; "
                "build_sdist('dist'); build_wheel('dist')"], cwd=root,
                capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            with zipfile.ZipFile(next((root / 'dist').glob('*.whl'))) as wheel:
                wheel_names = wheel.namelist()
            with tarfile.open(next((root / 'dist').glob('*.tar.gz'))) as source:
                source_names = source.getnames()
            for name, names in (('wheel', wheel_names), ('sdist', source_names)):
                with self.subTest(artifact=name):
                    self.assertFalse([p for p in names if p.endswith(('.nc', '.grib', '.idx'))])
                    for asset in ('templates/arome.yaml', 'presets/AROME/model_name_map.yaml',
                                  'testing/catalogs/science.yaml', 'testing/recipes/ci.yaml',
                                  'testing/ci_dataset/manifest.json',
                                  'testing/documentation_example.py', 'testing/datasets.py',
                                  'LICENSE'):
                        self.assertTrue(any(p.endswith(asset) for p in names), asset)
            for asset in ('CITATION.cff', 'CHANGELOG.md'):
                self.assertTrue(any(p.endswith('/' + asset) for p in source_names), asset)


if __name__ == '__main__':
    unittest.main()
