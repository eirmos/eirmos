"""Tests for the Codefresh parser."""

import tempfile
import unittest
from pathlib import Path

from eirmos.parsers.codefresh import CodefreshParser
from eirmos.graph import DependencyGraph


EXAMPLES = Path(__file__).parent / 'examples'


class TestCodefreshParser(unittest.TestCase):
    def setUp(self):
        self.parser = CodefreshParser(base_path=EXAMPLES)
        self.parser.parse(EXAMPLES / 'codefresh.yml')

    def test_jobs_discovered(self):
        self.assertEqual(set(self.parser.jobs.keys()),
                         {'clone', 'build', 'unit', 'lint', 'publish'})

    def test_when_steps_creates_explicit_dep(self):
        # build has when.steps[].name == 'clone'
        self.assertEqual(self.parser.get_job_needs('build'),
                         [{'job': 'clone', 'optional': False}])

    def test_parallel_children_share_parent_predecessor(self):
        # parallel block follows `build`; unit and lint inherit it.
        unit_needs = {n['job'] for n in self.parser.get_job_needs('unit')}
        lint_needs = {n['job'] for n in self.parser.get_job_needs('lint')}
        self.assertEqual(unit_needs, lint_needs)
        self.assertEqual(unit_needs, {'build'})

    def test_post_parallel_step_with_explicit_when(self):
        # publish has explicit when.steps[name=unit]
        self.assertEqual(self.parser.get_job_needs('publish'),
                         [{'job': 'unit', 'optional': False}])

    def test_rules_summary_lists_on_triggers(self):
        # build has on: [success]
        self.assertEqual(self.parser.get_job_rules_summary('build'), 'success')

    def test_no_cycle(self):
        self.assertFalse(DependencyGraph(self.parser).has_cycle())


class TestCodefreshEdgeCases(unittest.TestCase):
    def test_missing_file(self):
        p = CodefreshParser(base_path=EXAMPLES)
        p.parse(EXAMPLES / 'nope.yml')
        self.assertEqual(p.jobs, {})

    def test_empty_steps(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'cf.yml'
            f.write_text("version: '1.0'\nsteps: {}\n")
            p = CodefreshParser(base_path=d).parse(f)
            self.assertEqual(p.jobs, {})

    def test_parallel_without_explicit_when_fallback_sequential(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'cf.yml'
            f.write_text(
                "version: '1.0'\nsteps:\n"
                "  prep:\n    type: freestyle\n    image: alpine\n"
                "  par:\n    type: parallel\n    steps:\n"
                "      a:\n        type: freestyle\n        image: alpine\n"
                "      b:\n        type: freestyle\n        image: alpine\n"
            )
            p = CodefreshParser(base_path=d).parse(f)
            # Both children inherit prep as predecessor (sequential fallback)
            for child in ('a', 'b'):
                needs = [n['job'] for n in p.get_job_needs(child)]
                self.assertEqual(needs, ['prep'])

    def test_unknown_job_safe_defaults(self):
        p = CodefreshParser(base_path=EXAMPLES)
        self.assertEqual(p.get_job_stage('nope'), 'unknown')
        self.assertEqual(p.get_job_needs('nope'), [])
        self.assertEqual(p.get_job_rules_summary('nope'), '')

    def test_cycle_via_when(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'cf.yml'
            f.write_text(
                "version: '1.0'\nsteps:\n"
                "  a:\n    type: freestyle\n    image: alpine\n"
                "    when:\n      steps:\n        - name: b\n          on: [success]\n"
                "  b:\n    type: freestyle\n    image: alpine\n"
                "    when:\n      steps:\n        - name: a\n          on: [success]\n"
            )
            p = CodefreshParser(base_path=d).parse(f)
            self.assertTrue(DependencyGraph(p).has_cycle())


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
