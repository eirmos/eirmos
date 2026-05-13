"""Tests for the extended registry: 13 adapters + multi-match warning."""

import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from eirmos.parsers import REGISTRY, detect


EXPECTED_ADAPTERS = {
    'GitHub Actions',
    'GitLab CI',
    'CircleCI',
    'Jenkins',
    'Azure Pipelines',
    'Bitbucket Pipelines',
    'Drone CI',
    'Woodpecker CI',
    'Travis CI',
    'AppVeyor',
    'Buildkite',
    'Codefresh',
    'Semaphore',
}


def _write(p: Path, text: str = ""):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


class TestRegistryAdapters(unittest.TestCase):
    def test_all_adapters_registered(self):
        names = {a.name for a in REGISTRY}
        self.assertEqual(names, EXPECTED_ADAPTERS)


class TestSingleSystemDetection(unittest.TestCase):
    """Each system in isolation must be detected, no warning emitted."""

    def _detect_only(self, layout):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        for path, content in layout.items():
            _write(Path(tmp) / path, content)
        buf = io.StringIO()
        with redirect_stderr(buf):
            adapter, main_file = detect(Path(tmp))
        return adapter, main_file, buf.getvalue()

    def test_azure(self):
        a, _, err = self._detect_only({'azure-pipelines.yml': 'jobs: []\n'})
        self.assertEqual(a.name, 'Azure Pipelines')
        self.assertNotIn('WARNING', err)

    def test_bitbucket(self):
        a, _, _ = self._detect_only({'bitbucket-pipelines.yml': 'pipelines: {}\n'})
        self.assertEqual(a.name, 'Bitbucket Pipelines')

    def test_drone(self):
        a, _, _ = self._detect_only({'.drone.yml': 'kind: pipeline\nname: x\nsteps: []\n'})
        self.assertEqual(a.name, 'Drone CI')

    def test_woodpecker(self):
        a, _, _ = self._detect_only({'.woodpecker.yml': 'steps: {}\n'})
        self.assertEqual(a.name, 'Woodpecker CI')

    def test_travis(self):
        a, _, _ = self._detect_only({'.travis.yml': 'language: python\n'})
        self.assertEqual(a.name, 'Travis CI')

    def test_appveyor(self):
        a, _, _ = self._detect_only({'appveyor.yml': 'version: 1\n'})
        self.assertEqual(a.name, 'AppVeyor')

    def test_buildkite(self):
        a, _, _ = self._detect_only({'.buildkite/pipeline.yml': 'steps: []\n'})
        self.assertEqual(a.name, 'Buildkite')

    def test_codefresh(self):
        a, _, _ = self._detect_only({'codefresh.yml': "version: '1.0'\nsteps: {}\n"})
        self.assertEqual(a.name, 'Codefresh')

    def test_semaphore(self):
        a, _, _ = self._detect_only({'.semaphore/semaphore.yml': 'version: v1.0\nname: x\nblocks: []\n'})
        self.assertEqual(a.name, 'Semaphore')


class TestPolyglotMultiMatchWarning(unittest.TestCase):
    """Polyglot repo emits warning and returns first-by-registry-order."""

    def test_warning_on_multi_match(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        # Two systems present at once: GitHub Actions and Travis.
        _write(Path(tmp) / '.github' / 'workflows' / 'ci.yml', 'jobs: {}\n')
        _write(Path(tmp) / '.travis.yml', 'language: python\n')

        buf = io.StringIO()
        with redirect_stderr(buf):
            adapter, _ = detect(Path(tmp))

        # Registry order: GitHub Actions is registered first.
        self.assertEqual(adapter.name, 'GitHub Actions')
        err = buf.getvalue()
        self.assertIn('WARNING', err)
        self.assertIn('GitHub Actions', err)
        self.assertIn('Travis', err)

    def test_no_warning_on_single_match(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        _write(Path(tmp) / 'codefresh.yml', "version: '1.0'\nsteps: {}\n")

        buf = io.StringIO()
        with redirect_stderr(buf):
            detect(Path(tmp))
        self.assertNotIn('WARNING', buf.getvalue())

    def test_no_match_returns_none(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        adapter, main_file = detect(Path(tmp))
        self.assertIsNone(adapter)
        self.assertIsNone(main_file)


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
