"""Tests for the Jenkins and CircleCI parsers and the adapter registry."""

import shutil
import tempfile
import unittest
from pathlib import Path

from eirmos.parsers.jenkins import JenkinsParser
from eirmos.parsers.circleci import CircleCIParser
from eirmos.parsers import REGISTRY, detect


EXAMPLES = Path(__file__).parent / 'examples'


class TestJenkinsParser(unittest.TestCase):
    def setUp(self):
        self.parser = JenkinsParser(base_path=EXAMPLES)
        self.parser.parse(EXAMPLES / 'Jenkinsfile')

    def test_stages_discovered(self):
        self.assertEqual(
            set(self.parser.jobs.keys()),
            {'Build', 'Test', 'Unit', 'Lint', 'Deploy'},
        )

    def test_sequential_needs(self):
        # Test follows Build, Deploy follows Test
        self.assertEqual(self.parser.get_job_needs('Test'),
                         [{'job': 'Build', 'optional': False}])
        self.assertEqual(self.parser.get_job_needs('Deploy'),
                         [{'job': 'Test', 'optional': False}])

    def test_parallel_siblings_share_predecessor(self):
        # Unit and Lint live inside `parallel { ... }` nested in stage 'Test',
        # so they depend on their enclosing top-level stage and not on each
        # other. ``Deploy`` then comes after ``Test`` in declaration order.
        unit_needs = self.parser.get_job_needs('Unit')
        lint_needs = self.parser.get_job_needs('Lint')
        self.assertEqual(unit_needs, lint_needs,
                         "parallel siblings should share the same predecessor")
        self.assertEqual(len(unit_needs), 1)
        self.assertIn(unit_needs[0]['job'], {'Test', 'Build'})


class TestCircleCIParser(unittest.TestCase):
    def setUp(self):
        self.parser = CircleCIParser(base_path=EXAMPLES)
        self.parser.parse(EXAMPLES / 'circleci-config.yml')

    def test_jobs_discovered(self):
        self.assertEqual(set(self.parser.jobs.keys()), {'build', 'test', 'deploy'})

    def test_requires_translated_to_needs(self):
        self.assertEqual(self.parser.get_job_needs('build'), [])
        self.assertEqual(self.parser.get_job_needs('test'),
                         [{'job': 'build', 'optional': False}])
        self.assertEqual(self.parser.get_job_needs('deploy'),
                         [{'job': 'test', 'optional': False}])

    def test_stage_is_workflow_name(self):
        self.assertEqual(self.parser.get_job_stage('build'), 'ci')


class TestRegistryDetection(unittest.TestCase):
    def test_jenkins_detection(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        Path(tmp, 'Jenkinsfile').write_text('pipeline { stages { stage("X") {} } }')
        adapter, main_file = detect(Path(tmp))
        self.assertIsNotNone(adapter)
        self.assertEqual(adapter.name, 'Jenkins')
        self.assertEqual(main_file.name, 'Jenkinsfile')

    def test_circleci_detection(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        cfg_dir = Path(tmp, '.circleci')
        cfg_dir.mkdir()
        (cfg_dir / 'config.yml').write_text('version: 2.1\njobs: {}\n')
        adapter, main_file = detect(Path(tmp))
        self.assertIsNotNone(adapter)
        self.assertEqual(adapter.name, 'CircleCI')

    def test_registry_lists_existing_systems(self):
        names = {a.name for a in REGISTRY}
        # Originals must remain (extended set is verified in test_registry_extended.py)
        self.assertTrue(
            {'GitHub Actions', 'GitLab CI', 'CircleCI', 'Jenkins'}.issubset(names),
        )


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
