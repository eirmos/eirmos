"""Tests for the Semaphore parser."""

import tempfile
import unittest
from pathlib import Path

from eirmos.parsers.semaphore import SemaphoreParser
from eirmos.graph import DependencyGraph


EXAMPLES = Path(__file__).parent / 'examples'


class TestSemaphoreParser(unittest.TestCase):
    def setUp(self):
        self.parser = SemaphoreParser(base_path=EXAMPLES)
        self.parser.parse(EXAMPLES / '.semaphore' / 'semaphore.yml')

    def test_blocks_discovered(self):
        self.assertEqual(set(self.parser.jobs.keys()),
                         {'build', 'test', 'deploy'})

    def test_dependencies(self):
        self.assertEqual(self.parser.get_job_needs('build'), [])
        self.assertEqual(self.parser.get_job_needs('test'),
                         [{'job': 'build', 'optional': False}])
        self.assertEqual(self.parser.get_job_needs('deploy'),
                         [{'job': 'test', 'optional': False}])

    def test_workflow_name(self):
        self.assertEqual(self.parser.workflow_name, 'example pipeline')

    def test_no_cycle(self):
        self.assertFalse(DependencyGraph(self.parser).has_cycle())


class TestSemaphoreEdgeCases(unittest.TestCase):
    def test_missing_file(self):
        p = SemaphoreParser(base_path=EXAMPLES)
        p.parse(EXAMPLES / 'nope.yml')
        self.assertEqual(p.jobs, {})

    def test_empty_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 's.yml'
            f.write_text("version: v1.0\nname: x\nblocks: []\n")
            p = SemaphoreParser(base_path=d).parse(f)
            self.assertEqual(p.jobs, {})

    def test_single_block(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 's.yml'
            f.write_text(
                "version: v1.0\nname: x\nblocks:\n  - name: only\n    task: {jobs: []}\n"
            )
            p = SemaphoreParser(base_path=d).parse(f)
            self.assertEqual(set(p.jobs.keys()), {'only'})
            self.assertEqual(p.get_job_needs('only'), [])

    def test_cycle_via_dependencies(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 's.yml'
            f.write_text(
                "version: v1.0\nname: x\nblocks:\n"
                "  - name: a\n    dependencies: [b]\n    task: {jobs: []}\n"
                "  - name: b\n    dependencies: [a]\n    task: {jobs: []}\n"
            )
            p = SemaphoreParser(base_path=d).parse(f)
            self.assertTrue(DependencyGraph(p).has_cycle())

    def test_unknown_job_safe_defaults(self):
        p = SemaphoreParser(base_path=EXAMPLES)
        self.assertEqual(p.get_job_stage('nope'), 'unknown')
        self.assertEqual(p.get_job_needs('nope'), [])


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
