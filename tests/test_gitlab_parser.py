"""Detailed tests for :class:`GitLabCIParser`."""

import os
import tempfile
import textwrap
import unittest
from pathlib import Path

from eirmos import GitLabCIParser


EXAMPLES = Path(__file__).parent / 'examples'


class TestGitLabCIParserBasics(unittest.TestCase):
    def setUp(self):
        self.parser = GitLabCIParser(follow_includes=False)
        self.parser.parse(EXAMPLES / 'simple.gitlab-ci.yml')

    def test_jobs_discovered(self):
        self.assertEqual(set(self.parser.jobs), {'job1', 'job2', 'job3'})

    def test_stages_in_declared_order(self):
        self.assertEqual(self.parser.stages, ['build', 'test', 'deploy'])

    def test_file_map_records_source(self):
        for job in self.parser.jobs:
            self.assertIn(job, self.parser.file_map)

    def test_default_stage_is_test_when_not_specified(self):
        # Job without explicit stage should fall back to GitLab default 'test'
        with tempfile.TemporaryDirectory() as tmp:
            ci = Path(tmp) / '.gitlab-ci.yml'
            ci.write_text("nostage:\n  script: [echo hi]\n")
            parser = GitLabCIParser(base_path=tmp, follow_includes=False)
            parser.parse(ci)
            self.assertEqual(parser.get_job_stage('nostage'), 'test')

    def test_unknown_job_returns_unknown_stage(self):
        self.assertEqual(self.parser.get_job_stage('does_not_exist'), 'unknown')

    def test_unknown_job_has_no_needs(self):
        self.assertEqual(self.parser.get_job_needs('missing'), [])
        self.assertEqual(self.parser.get_job_extends('missing'), [])
        self.assertIsNone(self.parser.get_job_triggers('missing'))


class TestGitLabCIParserAdvanced(unittest.TestCase):
    def setUp(self):
        self.parser = GitLabCIParser(base_path='.', follow_includes=False)
        self.parser.parse(EXAMPLES / 'with_templates.gitlab-ci.yml')

    def test_templates_collected(self):
        self.assertIn('.base', self.parser.templates)
        self.assertIn('.deploy_template', self.parser.templates)
        # Templates must not appear in jobs
        self.assertNotIn('.base', self.parser.jobs)

    def test_global_variables(self):
        gvars = self.parser.get_global_variables()
        self.assertEqual(gvars.get('GLOBAL_VAR'), 'global-value')
        self.assertEqual(gvars.get('REGION'), 'eu-west-1')

    def test_extends_string_and_chain(self):
        self.assertEqual(self.parser.get_job_extends('deploy_eu'), ['.deploy_template'])

    def test_stage_inherited_from_template(self):
        # deploy_eu has no explicit stage, inherits from .deploy_template
        self.assertEqual(self.parser.get_job_stage('deploy_eu'), 'deploy')

    def test_optional_needs(self):
        needs = self.parser.get_job_needs('integration_tests')
        self.assertEqual(needs[0], {'job': 'build', 'optional': False, 'artifacts': True})
        self.assertEqual(needs[1]['job'], 'unit_tests')
        self.assertTrue(needs[1]['optional'])

    def test_variables_inherited_and_overridden(self):
        # deploy_eu inherits BASE_VAR (from .base via .deploy_template chain at one level)
        # and overrides DEPLOY_VAR
        variables = self.parser.get_job_variables('deploy_eu')
        # Direct extends only walks one level (matching original semantics)
        self.assertEqual(variables.get('DEPLOY_VAR'), 'deploy-eu')

    def test_trigger_child_pipeline(self):
        trig = self.parser.get_job_triggers('trigger_child')
        self.assertEqual(trig, {'type': 'child', 'include': 'child-pipeline.yml'})

    def test_rules_summary_detects_custom_build(self):
        summary = self.parser.get_job_rules_summary('deploy_eu')
        self.assertIn('CB:release', summary)

    def test_rules_summary_no_rules_is_always(self):
        self.assertEqual(self.parser.get_job_rules_summary('build'), 'always')


class TestGitLabCIParserIncludes(unittest.TestCase):
    def test_follows_local_includes(self):
        parser = GitLabCIParser(base_path='.', follow_includes=True)
        parser.parse(EXAMPLES / 'complex.gitlab-ci.yml')
        self.assertIn('notify_job', parser.jobs)
        # Two files were parsed
        self.assertEqual(len(parser.parsed_files), 2)

    def test_disabling_includes(self):
        parser = GitLabCIParser(base_path='.', follow_includes=False)
        parser.parse(EXAMPLES / 'complex.gitlab-ci.yml')
        self.assertNotIn('notify_job', parser.jobs)

    def test_missing_include_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            ci = Path(tmp) / '.gitlab-ci.yml'
            ci.write_text(textwrap.dedent("""\
                include:
                  - local: 'does/not/exist.yml'
                jobx:
                  script: [echo x]
            """))
            parser = GitLabCIParser(base_path=tmp, follow_includes=True)
            parser.parse(ci)
            self.assertIn('jobx', parser.jobs)

    def test_remote_project_include_is_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            ci = Path(tmp) / '.gitlab-ci.yml'
            ci.write_text(textwrap.dedent("""\
                include:
                  - project: 'group/proj'
                    file: '/ci.yml'
                  - component: 'gitlab.com/comp@1.0'
                jobx:
                  script: [echo x]
            """))
            parser = GitLabCIParser(base_path=tmp, follow_includes=True)
            parser.parse(ci)
            kinds = {i['type'] for i in parser.includes}
            self.assertEqual(kinds, {'project', 'component'})


class TestGitLabCIParserMalformed(unittest.TestCase):
    def test_invalid_yaml_does_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / '.gitlab-ci.yml'
            bad.write_text("::: not yaml :::\n  -")
            parser = GitLabCIParser(base_path=tmp, follow_includes=False)
            parser.parse(bad)  # must not raise
            self.assertEqual(parser.jobs, {})

    def test_non_dict_top_level_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / '.gitlab-ci.yml'
            bad.write_text("- one\n- two\n")
            parser = GitLabCIParser(base_path=tmp, follow_includes=False)
            parser.parse(bad)
            self.assertEqual(parser.jobs, {})

    def test_reserved_keys_not_treated_as_jobs(self):
        with tempfile.TemporaryDirectory() as tmp:
            ci = Path(tmp) / '.gitlab-ci.yml'
            ci.write_text(textwrap.dedent("""\
                workflow:
                  rules:
                    - if: '$CI_COMMIT_BRANCH'
                default:
                  image: alpine
                real_job:
                  script: [echo hi]
            """))
            parser = GitLabCIParser(base_path=tmp, follow_includes=False)
            parser.parse(ci)
            self.assertEqual(set(parser.jobs), {'real_job'})


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
