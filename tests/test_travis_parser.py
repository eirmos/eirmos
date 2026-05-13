"""Tests for the Travis CI parser."""

import io
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from eirmos.parsers.travis import TravisCIParser
from eirmos.graph import DependencyGraph


EXAMPLES = Path(__file__).parent / 'examples'


class TestTravisStages(unittest.TestCase):
    def setUp(self):
        self.parser = TravisCIParser(base_path=EXAMPLES)
        self.parser.parse(EXAMPLES / '.travis.yml')

    def test_jobs_discovered(self):
        self.assertEqual(set(self.parser.jobs.keys()),
                         {'compile', 'unit', 'integration', 'release'})

    def test_jobs_within_stage_share_predecessor(self):
        unit_needs = {n['job'] for n in self.parser.get_job_needs('unit')}
        integration_needs = {n['job'] for n in self.parser.get_job_needs('integration')}
        self.assertEqual(unit_needs, integration_needs)
        self.assertEqual(unit_needs, {'compile'})

    def test_stages_sequential(self):
        # release (deploy stage) depends on previous-stage jobs (unit, integration)
        release_needs = {n['job'] for n in self.parser.get_job_needs('release')}
        self.assertEqual(release_needs, {'unit', 'integration'})

    def test_no_cycle(self):
        self.assertFalse(DependencyGraph(self.parser).has_cycle())


class TestTravisEdgeCases(unittest.TestCase):
    def test_missing_file(self):
        p = TravisCIParser(base_path=EXAMPLES)
        p.parse(EXAMPLES / 'nope.yml')
        self.assertEqual(p.jobs, {})

    def test_no_stage_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 't.yml'
            f.write_text(
                "language: python\n"
                "script: echo hi\n"
            )
            p = TravisCIParser(base_path=d).parse(f)
            # Should produce one job named after the language
            self.assertEqual(set(p.jobs.keys()), {'python'})

    def test_matrix_expansion_within_limit(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 't.yml'
            f.write_text(
                "language: python\n"
                "env:\n"
                "  - A=1\n"
                "  - A=2\n"
                "  - A=3\n"
            )
            p = TravisCIParser(base_path=d, matrix_limit=10).parse(f)
            self.assertEqual(len(p.jobs), 3)

    def test_matrix_truncation_warns(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 't.yml'
            f.write_text(
                "language: python\nenv:\n" + "\n".join(f"  - A={i}" for i in range(20)) + "\n"
            )
            buf = io.StringIO()
            with redirect_stderr(buf):
                p = TravisCIParser(base_path=d, matrix_limit=5).parse(f)
            self.assertEqual(len(p.jobs), 5)
            self.assertIn("truncated", buf.getvalue())

    def test_unknown_job_safe_defaults(self):
        p = TravisCIParser(base_path=EXAMPLES)
        self.assertEqual(p.get_job_stage('nope'), 'unknown')
        self.assertEqual(p.get_job_needs('nope'), [])


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
