import unittest
import os
import sys
from eirmos import GitLabCIParser, GitHubActionsParser, DependencyGraph, TreeFormatter

class TestGitLabCIParser(unittest.TestCase):
    def test_simple_pipeline(self):
        parser = GitLabCIParser(follow_includes=False)
        parser.parse('tests/examples/simple.gitlab-ci.yml')
        
        jobs = parser.jobs
        self.assertIn('job1', jobs)
        self.assertIn('job2', jobs)
        self.assertIn('job3', jobs)
        
        self.assertEqual(parser.get_job_stage('job1'), 'build')
        self.assertEqual(parser.get_job_stage('job2'), 'test')
        self.assertEqual(parser.get_job_stage('job3'), 'deploy')
        
        self.assertEqual(parser.get_job_needs('job2'), [{'job': 'job1', 'optional': False}])
        self.assertEqual(parser.get_job_needs('job3'), [{'job': 'job2', 'optional': False}])

    def test_complex_pipeline_with_includes(self):
        # We need to make sure the parser can find the included file relative to the project root
        parser = GitLabCIParser(base_path='.', follow_includes=True)
        parser.parse('tests/examples/complex.gitlab-ci.yml')
        
        jobs = parser.jobs
        self.assertIn('build_job', jobs)
        self.assertIn('test_job', jobs)
        self.assertIn('notify_job', jobs) # From include
        
        self.assertEqual(parser.get_job_stage('notify_job'), 'notify')
        self.assertEqual(parser.get_job_needs('test_job'), [{'job': 'build_job', 'optional': False}])
        self.assertEqual(parser.get_job_needs('notify_job'), [{'job': 'test_job', 'optional': False}])

    def test_dependency_graph(self):
        parser = GitLabCIParser(follow_includes=False)
        parser.parse('tests/examples/simple.gitlab-ci.yml')
        graph = DependencyGraph(parser)
        
        self.assertEqual(graph.get_roots(), ['job1'])
        self.assertEqual(graph.get_successors('job1'), [('job2', 'needs')])
        self.assertEqual(graph.get_successors('job2'), [('job3', 'needs')])
        self.assertEqual(graph.get_predecessors('job3'), [('job2', 'needs')])

class TestGitHubActionsParser(unittest.TestCase):
    def test_github_workflow(self):
        parser = GitHubActionsParser()
        parser.parse('tests/examples/github-workflow.yml')
        
        self.assertIn('build', parser.jobs)
        self.assertIn('test', parser.jobs)
        self.assertIn('deploy', parser.jobs)
        
        self.assertEqual(parser.get_job_needs('test'), [{'job': 'build', 'optional': False}])
        self.assertEqual(parser.get_job_needs('deploy'), [
            {'job': 'build', 'optional': False},
            {'job': 'test', 'optional': False}
        ])
        
    def test_github_dependency_graph(self):
        parser = GitHubActionsParser()
        parser.parse('tests/examples/github-workflow.yml')
        graph = DependencyGraph(parser)
        
        self.assertEqual(graph.get_roots(), ['build'])
        self.assertEqual(len(graph.get_successors('build')), 2) # test and deploy
        self.assertIn(('test', 'needs'), graph.get_successors('build'))
        self.assertIn(('deploy', 'needs'), graph.get_successors('build'))
        self.assertEqual(graph.get_predecessors('test'), [('build', 'needs')])

if __name__ == '__main__':
    unittest.main()
