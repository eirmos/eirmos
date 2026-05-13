"""Tests for the Azure Pipelines parser."""

import unittest
from pathlib import Path

from eirmos.parsers.azure import AzurePipelinesParser
from eirmos.graph import DependencyGraph


EXAMPLES = Path(__file__).parent / 'examples'


class TestAzureParserMultiStage(unittest.TestCase):
    def setUp(self):
        self.parser = AzurePipelinesParser(base_path=EXAMPLES)
        self.parser.parse(EXAMPLES / 'azure-pipelines.yml')

    def test_jobs_discovered(self):
        self.assertEqual(
            set(self.parser.jobs.keys()),
            {'compile', 'package', 'unit', 'integration', 'prod'},
        )

    def test_implicit_prev_stage(self):
        # `test` stage has no dependsOn → implicitly depends on prev stage `build`.
        # `unit` is the first job of `test`, no explicit deps → inherits the
        # last-jobs of `build` (compile, package).
        needs = {n['job'] for n in self.parser.get_job_needs('unit')}
        self.assertEqual(needs, {'compile', 'package'})

    def test_explicit_stage_dependsOn(self):
        # `deploy` stage dependsOn: build → prod inherits last-jobs of build.
        needs = {n['job'] for n in self.parser.get_job_needs('prod')}
        self.assertEqual(needs, {'compile', 'package'})

    def test_job_dependsOn_string(self):
        # `package` has dependsOn: compile (string form).
        self.assertEqual(self.parser.get_job_needs('package'),
                         [{'job': 'compile', 'optional': False}])

    def test_deployment_job_treated_as_job(self):
        self.assertEqual(self.parser.get_job_stage('prod'), 'deploy')

    def test_no_cycle(self):
        self.assertFalse(DependencyGraph(self.parser).has_cycle())


class TestAzureFlatJobs(unittest.TestCase):
    def test_flat_jobs_sequential(self):
        p = AzurePipelinesParser(base_path=EXAMPLES)
        p.parse(EXAMPLES / 'azure-flat-jobs.yml')
        self.assertEqual(set(p.jobs.keys()), {'lint', 'build', 'test'})
        # `test` has no dependsOn → implicit prev-job (build)
        self.assertEqual(p.get_job_needs('test'),
                         [{'job': 'build', 'optional': False}])
        # `build` has explicit dependsOn: lint
        self.assertEqual(p.get_job_needs('build'),
                         [{'job': 'lint', 'optional': False}])


class TestAzureStepsOnly(unittest.TestCase):
    def test_steps_form_creates_one_job(self):
        p = AzurePipelinesParser(base_path=EXAMPLES)
        p.parse(EXAMPLES / 'azure-steps.yml')
        self.assertEqual(len(p.jobs), 1)


class TestAzureEdgeCases(unittest.TestCase):
    def test_missing_file(self):
        p = AzurePipelinesParser(base_path=EXAMPLES)
        p.parse(EXAMPLES / 'does-not-exist.yml')
        self.assertEqual(p.jobs, {})

    def test_unknown_job_safe_defaults(self):
        p = AzurePipelinesParser(base_path=EXAMPLES)
        self.assertEqual(p.get_job_stage('nope'), 'unknown')
        self.assertEqual(p.get_job_needs('nope'), [])

    def test_dependsOn_list_form(self, tmp_path=None):
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'azure.yml'
            f.write_text(
                "stages:\n"
                "  - stage: a\n"
                "    jobs:\n"
                "      - job: a1\n"
                "        steps: [{script: echo}]\n"
                "  - stage: b\n"
                "    jobs:\n"
                "      - job: b1\n"
                "        dependsOn: [a1]\n"
                "        steps: [{script: echo}]\n"
            )
            p = AzurePipelinesParser(base_path=d).parse(f)
            self.assertEqual(p.get_job_needs('b1'),
                             [{'job': 'a1', 'optional': False}])

    def test_malformed_yaml_returns_empty(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'bad.yml'
            f.write_text("stages: [unterminated\n")
            p = AzurePipelinesParser(base_path=d).parse(f)
            self.assertEqual(p.jobs, {})


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
