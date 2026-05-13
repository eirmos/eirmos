"""Tests for the Buildkite parser."""

import tempfile
import unittest
from pathlib import Path

from eirmos.parsers.buildkite import BuildkiteParser
from eirmos.graph import DependencyGraph


EXAMPLES = Path(__file__).parent / 'examples'


class TestBuildkiteWaitBarrier(unittest.TestCase):
    def setUp(self):
        self.parser = BuildkiteParser(base_path=EXAMPLES)
        self.parser.parse(EXAMPLES / '.buildkite' / 'pipeline.yml')

    def test_jobs_discovered(self):
        self.assertEqual(
            set(self.parser.jobs.keys()),
            {'lint', 'build', 'unit', 'integration',
             'deploy_staging', 'deploy_prod'},
        )

    def test_explicit_depends_on(self):
        self.assertEqual(self.parser.get_job_needs('build'),
                         [{'job': 'lint', 'optional': False}])

    def test_wait_cross_product_implicit_deps(self):
        # After the first wait, unit and integration depend on
        # everything before the wait (lint + build).
        unit_needs = {n['job'] for n in self.parser.get_job_needs('unit')}
        integ_needs = {n['job'] for n in self.parser.get_job_needs('integration')}
        self.assertEqual(unit_needs, {'lint', 'build'})
        self.assertEqual(integ_needs, {'lint', 'build'})

    def test_explicit_depends_on_after_wait_no_double_add(self):
        # deploy_prod has explicit depends_on: deploy_staging — must NOT
        # also pick up cross-product edges from the second wait.
        needs = {n['job'] for n in self.parser.get_job_needs('deploy_prod')}
        self.assertEqual(needs, {'deploy_staging'})

    def test_group_flattened(self):
        # The `group:` wrapper is dropped; deploy_staging and deploy_prod
        # appear as top-level steps after group flattening.
        self.assertIn('deploy_staging', self.parser.jobs)
        self.assertIn('deploy_prod', self.parser.jobs)

    def test_deploy_staging_implicit_cross_product(self):
        # deploy_staging is the first step after the second wait, no explicit
        # depends_on → cross-product of everything before wait #2.
        needs = {n['job'] for n in self.parser.get_job_needs('deploy_staging')}
        self.assertEqual(needs, {'lint', 'build', 'unit', 'integration'})

    def test_no_cycle(self):
        self.assertFalse(DependencyGraph(self.parser).has_cycle())


class TestBuildkiteEdgeCases(unittest.TestCase):
    def test_missing_file(self):
        p = BuildkiteParser(base_path=EXAMPLES)
        p.parse(EXAMPLES / 'nope.yml')
        self.assertEqual(p.jobs, {})

    def test_empty_steps(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'p.yml'
            f.write_text("steps: []\n")
            p = BuildkiteParser(base_path=d).parse(f)
            self.assertEqual(p.jobs, {})

    def test_single_step(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'p.yml'
            f.write_text("steps:\n  - key: only\n    command: echo\n")
            p = BuildkiteParser(base_path=d).parse(f)
            self.assertEqual(set(p.jobs.keys()), {'only'})

    def test_cycle_via_explicit_depends_on(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'p.yml'
            f.write_text(
                "steps:\n"
                "  - key: a\n    command: echo a\n    depends_on: b\n"
                "  - key: b\n    command: echo b\n    depends_on: a\n"
            )
            p = BuildkiteParser(base_path=d).parse(f)
            self.assertTrue(DependencyGraph(p).has_cycle())

    def test_unknown_job_safe_defaults(self):
        p = BuildkiteParser(base_path=EXAMPLES)
        self.assertEqual(p.get_job_stage('nope'), 'unknown')
        self.assertEqual(p.get_job_needs('nope'), [])


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
