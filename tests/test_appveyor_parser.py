"""Tests for the AppVeyor parser."""

import io
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from eirmos.parsers.appveyor import AppVeyorParser
from eirmos.graph import DependencyGraph


EXAMPLES = Path(__file__).parent / 'examples'


class TestAppVeyorMatrix(unittest.TestCase):
    def setUp(self):
        self.parser = AppVeyorParser(base_path=EXAMPLES)
        self.parser.parse(EXAMPLES / 'appveyor.yml')

    def test_phases_become_stages(self):
        # install / build / test / deploy are all active in the fixture
        for phase in ('install', 'build', 'test', 'deploy'):
            self.assertIn(phase, self.parser.stages)

    def test_matrix_x_phases(self):
        # 2 matrix entries × 4 phases = 8 jobs
        self.assertEqual(len(self.parser.jobs), 8)

    def test_phase_chaining(self):
        # Every build job depends on every install job (cross-product)
        build_jobs = [j for j, c in self.parser.jobs.items() if c['_phase'] == 'build']
        install_jobs = [j for j, c in self.parser.jobs.items() if c['_phase'] == 'install']
        for bj in build_jobs:
            needs = {n['job'] for n in self.parser.get_job_needs(bj)}
            self.assertEqual(needs, set(install_jobs))

    def test_no_cycle(self):
        self.assertFalse(DependencyGraph(self.parser).has_cycle())


class TestAppVeyorEdgeCases(unittest.TestCase):
    def test_missing_file(self):
        p = AppVeyorParser(base_path=EXAMPLES)
        p.parse(EXAMPLES / 'nope.yml')
        self.assertEqual(p.jobs, {})

    def test_no_phases_defaults_to_build_test(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'av.yml'
            f.write_text("version: 1\n")
            p = AppVeyorParser(base_path=d).parse(f)
            self.assertIn('build', p.stages)
            self.assertIn('test', p.stages)

    def test_matrix_truncation_warns(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'av.yml'
            entries = "\n".join(f"    - PYTHON: {i}" for i in range(30))
            f.write_text(
                "environment:\n  matrix:\n" + entries + "\n"
                "build_script:\n  - echo build\n"
            )
            buf = io.StringIO()
            with redirect_stderr(buf):
                p = AppVeyorParser(base_path=d, matrix_limit=10).parse(f)
            # 10 matrix * 1 phase
            self.assertEqual(len(p.jobs), 10)
            self.assertIn("truncated", buf.getvalue())

    def test_image_axis_combines_with_matrix(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'av.yml'
            f.write_text(
                "image:\n  - Visual Studio 2019\n  - Ubuntu\n"
                "environment:\n  matrix:\n    - A: 1\n    - A: 2\n"
                "build_script:\n  - echo build\n"
            )
            p = AppVeyorParser(base_path=d).parse(f)
            # 2 matrix × 2 images = 4 build jobs
            build_jobs = [j for j in p.jobs if p.jobs[j]['_phase'] == 'build']
            self.assertEqual(len(build_jobs), 4)

    def test_unknown_job_safe_defaults(self):
        p = AppVeyorParser(base_path=EXAMPLES)
        self.assertEqual(p.get_job_stage('nope'), 'unknown')
        self.assertEqual(p.get_job_needs('nope'), [])


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
