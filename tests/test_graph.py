"""Tests for :class:`DependencyGraph`."""

import unittest
from pathlib import Path

from eirmos import (
    DependencyGraph,
    GitHubActionsParser,
    GitLabCIParser,
)


EXAMPLES = Path(__file__).parent / 'examples'


class TestDependencyGraphSimple(unittest.TestCase):
    def setUp(self):
        self.parser = GitLabCIParser(follow_includes=False)
        self.parser.parse(EXAMPLES / 'simple.gitlab-ci.yml')
        self.graph = DependencyGraph(self.parser)

    def test_roots(self):
        self.assertEqual(self.graph.get_roots(), ['job1'])

    def test_successors_and_predecessors(self):
        self.assertEqual(self.graph.get_successors('job1'), [('job2', 'needs')])
        self.assertEqual(self.graph.get_predecessors('job3'), [('job2', 'needs')])

    def test_stage_jobs_grouping(self):
        self.assertEqual(self.graph.stage_jobs['build'], ['job1'])
        self.assertEqual(self.graph.stage_jobs['test'], ['job2'])
        self.assertEqual(self.graph.stage_jobs['deploy'], ['job3'])

    def test_ordered_stages_uses_declared_order(self):
        self.assertEqual(self.graph.get_ordered_stages(), ['build', 'test', 'deploy'])

    def test_no_cycle_in_simple(self):
        self.assertFalse(self.graph.has_cycle())


class TestDependencyGraphCycles(unittest.TestCase):
    def test_detects_cycle(self):
        parser = GitLabCIParser(follow_includes=False)
        parser.parse(EXAMPLES / 'cycle.gitlab-ci.yml')
        graph = DependencyGraph(parser)
        self.assertTrue(graph.has_cycle())


class TestDependencyGraphTriggersAndExtends(unittest.TestCase):
    def setUp(self):
        self.parser = GitLabCIParser(follow_includes=False)
        self.parser.parse(EXAMPLES / 'with_templates.gitlab-ci.yml')
        self.graph = DependencyGraph(self.parser)

    def test_trigger_edge_added(self):
        triggers = [e for e in self.graph.edges if e[2] == 'trigger']
        self.assertEqual(len(triggers), 1)
        src, dst, _ = triggers[0]
        self.assertEqual(src, 'trigger_child')
        self.assertTrue(dst.startswith('[child:'))

    def test_optional_needs_edge_type(self):
        edges = [e for e in self.graph.edges
                 if e[1] == 'integration_tests' and e[0] == 'unit_tests']
        self.assertEqual(edges[0][2], 'needs-optional')

    def test_extends_edge_only_for_jobs(self):
        # Templates start with '.', should not become extends edges
        extends_edges = [e for e in self.graph.edges if e[2] == 'extends']
        for src, _, _ in extends_edges:
            self.assertFalse(src.startswith('.'))


class TestDependencyGraphGitHub(unittest.TestCase):
    def test_github_actions(self):
        parser = GitHubActionsParser()
        parser.parse(EXAMPLES / 'github-workflow.yml')
        graph = DependencyGraph(parser)
        self.assertEqual(graph.get_roots(), ['build'])
        self.assertEqual(set(graph.get_successors('build')),
                         {('test', 'needs'), ('deploy', 'needs')})


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
