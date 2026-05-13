"""Tests for the Bitbucket Pipelines parser."""

import tempfile
import unittest
from pathlib import Path

from eirmos.parsers.bitbucket import BitbucketPipelinesParser
from eirmos.graph import DependencyGraph


EXAMPLES = Path(__file__).parent / 'examples'


class TestBitbucketParser(unittest.TestCase):
    def setUp(self):
        self.parser = BitbucketPipelinesParser(base_path=EXAMPLES)
        self.parser.parse(EXAMPLES / 'bitbucket-pipelines.yml')

    def test_default_steps_discovered(self):
        names = set(self.parser.jobs.keys())
        self.assertIn('lint', names)
        self.assertIn('build', names)
        self.assertIn('unit', names)
        self.assertIn('integration', names)
        self.assertIn('deploy', names)

    def test_branches_and_custom_pipelines(self):
        self.assertIn('release', self.parser.jobs)
        self.assertIn('nightly-build', self.parser.jobs)
        self.assertEqual(self.parser.get_job_stage('release'), 'branches:main')
        self.assertEqual(self.parser.get_job_stage('nightly-build'),
                         'custom:nightly')

    def test_sequential_steps(self):
        self.assertEqual(self.parser.get_job_needs('build'),
                         [{'job': 'lint', 'optional': False}])

    def test_parallel_siblings_share_predecessor(self):
        unit_needs = self.parser.get_job_needs('unit')
        integration_needs = self.parser.get_job_needs('integration')
        self.assertEqual(unit_needs, integration_needs)
        self.assertEqual(unit_needs, [{'job': 'build', 'optional': False}])

    def test_post_parallel_step_chains_to_last_sibling(self):
        # deploy follows the parallel block; we chain to the last sibling.
        deploy_needs = [n['job'] for n in self.parser.get_job_needs('deploy')]
        self.assertIn(deploy_needs[0], {'unit', 'integration'})

    def test_no_cycle(self):
        self.assertFalse(DependencyGraph(self.parser).has_cycle())


class TestBitbucketEdgeCases(unittest.TestCase):
    def test_missing_file(self):
        p = BitbucketPipelinesParser(base_path=EXAMPLES)
        p.parse(EXAMPLES / 'nope.yml')
        self.assertEqual(p.jobs, {})

    def test_empty_pipeline(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'bitbucket-pipelines.yml'
            f.write_text("pipelines: {}\n")
            p = BitbucketPipelinesParser(base_path=d).parse(f)
            self.assertEqual(p.jobs, {})

    def test_parallel_with_steps_dict_form(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'bb.yml'
            f.write_text(
                "pipelines:\n"
                "  default:\n"
                "    - parallel:\n"
                "        fail-fast: true\n"
                "        steps:\n"
                "          - step: {name: a, script: [echo a]}\n"
                "          - step: {name: b, script: [echo b]}\n"
            )
            p = BitbucketPipelinesParser(base_path=d).parse(f)
            self.assertEqual(set(p.jobs.keys()), {'a', 'b'})

    def test_unknown_job_safe_defaults(self):
        p = BitbucketPipelinesParser(base_path=EXAMPLES)
        self.assertEqual(p.get_job_stage('nope'), 'unknown')
        self.assertEqual(p.get_job_needs('nope'), [])


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
