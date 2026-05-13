"""Tests for output formatters.

We disable colors before importing so the rendered strings are
deterministic across environments.
"""

import unittest
from pathlib import Path

from eirmos import (
    Colors,
    DependencyGraph,
    DotFormatter,
    GitLabCIParser,
    MermaidFormatter,
    SummaryFormatter,
    TreeFormatter,
    VariableFormatter,
)


Colors.disable()
EXAMPLES = Path(__file__).parent / 'examples'


def _build():
    parser = GitLabCIParser(base_path='.', follow_includes=False)
    parser.parse(EXAMPLES / 'with_templates.gitlab-ci.yml')
    return parser, DependencyGraph(parser)


class TestTreeFormatter(unittest.TestCase):
    def test_renders_all_jobs_and_stages(self):
        parser, graph = _build()
        out = TreeFormatter(parser, graph).render()
        self.assertIn('Stage: build', out)
        self.assertIn('Stage: test', out)
        self.assertIn('Stage: deploy', out)
        for job in parser.jobs:
            self.assertIn(job, out)

    def test_filter_by_stage(self):
        parser, graph = _build()
        out = TreeFormatter(parser, graph).render(filter_stage='build')
        self.assertIn('build', out)
        self.assertNotIn('Stage: test', out)
        self.assertNotIn('Stage: deploy', out)

    def test_job_detail_unknown(self):
        parser, graph = _build()
        out = TreeFormatter(parser, graph).render(filter_job='no_such_job')
        self.assertIn("not found", out)

    def test_job_detail_known(self):
        parser, graph = _build()
        out = TreeFormatter(parser, graph).render(filter_job='deploy_eu')
        self.assertIn('Job: deploy_eu', out)
        self.assertIn('Dependencies', out)
        self.assertIn('integration_tests', out)


class TestMermaidFormatter(unittest.TestCase):
    def test_basic_structure(self):
        parser, graph = _build()
        out = MermaidFormatter(parser, graph).render()
        self.assertIn('flowchart TD', out)
        self.assertTrue(out.startswith('```mermaid'))
        self.assertTrue(out.rstrip().endswith('```'))

    def test_includes_needs_edges(self):
        parser, graph = _build()
        out = MermaidFormatter(parser, graph).render()
        self.assertIn('build --> unit_tests', out)
        # optional edge uses dotted arrow
        self.assertIn('-.->', out)


class TestDotFormatter(unittest.TestCase):
    def test_dot_renders(self):
        parser, graph = _build()
        out = DotFormatter(parser, graph).render()
        self.assertTrue(out.startswith('digraph pipeline'))
        self.assertIn('subgraph cluster_build', out)
        self.assertIn('build -> unit_tests', out)
        # optional dependency
        self.assertIn('style=dashed', out)


class TestSummaryFormatter(unittest.TestCase):
    def test_summary_contains_stats_and_stages(self):
        parser, graph = _build()
        out = SummaryFormatter(parser, graph).render()
        self.assertIn('Statistics', out)
        self.assertIn(f"Total jobs:      {len(parser.jobs)}", out)
        self.assertIn('Stages:', out)


class TestVariableFormatter(unittest.TestCase):
    def test_variables_render(self):
        parser, graph = _build()
        out = VariableFormatter(parser, graph).render()
        self.assertIn('GLOBAL_VAR', out)
        self.assertIn('Variable Usage Matrix', out)


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
