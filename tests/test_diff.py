"""Unit tests for :mod:`eirmos.diff` — the pure GraphDiff engine."""

import json
import unittest

from eirmos import DependencyGraph, GraphDelta, GraphDiff
from eirmos.diff.render import render_json, render_markdown, render_text


class _FakeParser:
    """Minimal parser stub.

    The diff engine never reads YAML — it only needs the parser
    protocol (``jobs`` dict + ``get_job_stage``). A stub keeps the
    tests fast and pin-pointed to diff behavior, not parser quirks.
    """

    def __init__(self, jobs, stages=None, optional_edges=None,
                 extra_edges=None):
        # jobs: {name: {'stage': str, 'needs': [str, ...]}}
        self.jobs = {name: dict(cfg) for name, cfg in jobs.items()}
        self.stages = list(stages or [])
        self.templates = {}
        self.parsed_files = set()
        self.file_map = {}
        self.parse_errors = []
        self._optional = set(optional_edges or [])
        self._extra = list(extra_edges or [])

    @property
    def status(self):
        if self.parse_errors:
            return 'failed'
        if not self.jobs:
            return 'empty'
        return 'ok'

    def get_job_stage(self, name):
        return self.jobs.get(name, {}).get('stage', 'unknown')

    def get_job_needs(self, name):
        needs = self.jobs.get(name, {}).get('needs', [])
        return [
            {'job': n, 'optional': (name, n) in self._optional}
            for n in needs
        ]

    def get_job_extends(self, name):
        return self.jobs.get(name, {}).get('extends', [])

    def get_job_triggers(self, name):
        return self.jobs.get(name, {}).get('trigger')


def _graph(parser):
    g = DependencyGraph(parser)
    # ``extra_edges`` lets a test inject edges with arbitrary types
    # (e.g. 'trigger', 'extends') that aren't naturally produced by the
    # fake parser shape — used to verify edge add/remove for those.
    for src, dst, etype in parser._extra:
        g.edges.append((src, dst, etype))
    return g


class TestGraphDiffNodes(unittest.TestCase):
    def test_added_and_removed_nodes(self):
        base = _graph(_FakeParser({'a': {'stage': 'build'},
                                   'b': {'stage': 'test'}}))
        head = _graph(_FakeParser({'a': {'stage': 'build'},
                                   'c': {'stage': 'deploy'}}))
        d = GraphDiff.compute(base, head)
        self.assertEqual(d.nodes_added, ['c'])
        self.assertEqual(d.nodes_removed, ['b'])

    def test_stage_change_only(self):
        base = _graph(_FakeParser({'a': {'stage': 'build'}}))
        head = _graph(_FakeParser({'a': {'stage': 'test'}}))
        d = GraphDiff.compute(base, head)
        self.assertEqual(d.nodes_stage_changed, [('a', 'build', 'test')])
        self.assertEqual(d.nodes_added, [])
        self.assertEqual(d.nodes_removed, [])

    def test_no_changes(self):
        base = _graph(_FakeParser({'a': {'stage': 'build'}}))
        head = _graph(_FakeParser({'a': {'stage': 'build'}}))
        d = GraphDiff.compute(base, head)
        self.assertFalse(d.has_changes)


class TestGraphDiffEdges(unittest.TestCase):
    def test_edge_added_and_removed(self):
        # base: a -> b. head: a -> b -> c. New job AND new edge.
        base = _graph(_FakeParser({
            'a': {'stage': 'build'},
            'b': {'stage': 'test', 'needs': ['a']},
        }))
        head = _graph(_FakeParser({
            'a': {'stage': 'build'},
            'b': {'stage': 'test', 'needs': ['a']},
            'c': {'stage': 'deploy', 'needs': ['b']},
        }))
        d = GraphDiff.compute(base, head)
        self.assertIn(('b', 'c', 'needs'), d.edges_added)
        self.assertEqual(d.edges_removed, [])

    def test_rerouted_edge_shown_as_remove_plus_add(self):
        # base: build -> deploy. head: build -> sign -> deploy.
        base = _graph(_FakeParser({
            'build': {'stage': 'build'},
            'deploy': {'stage': 'deploy', 'needs': ['build']},
        }))
        head = _graph(_FakeParser({
            'build': {'stage': 'build'},
            'sign': {'stage': 'test', 'needs': ['build']},
            'deploy': {'stage': 'deploy', 'needs': ['sign']},
        }))
        d = GraphDiff.compute(base, head)
        self.assertIn(('build', 'deploy', 'needs'), d.edges_removed)
        self.assertIn(('build', 'sign', 'needs'), d.edges_added)
        self.assertIn(('sign', 'deploy', 'needs'), d.edges_added)


class TestGraphDiffCycleAndCriticalPath(unittest.TestCase):
    def test_cycle_introduced(self):
        base = _graph(_FakeParser({
            'a': {'stage': 'x'},
            'b': {'stage': 'x', 'needs': ['a']},
        }))
        head = _graph(_FakeParser({
            'a': {'stage': 'x', 'needs': ['b']},
            'b': {'stage': 'x', 'needs': ['a']},
        }))
        d = GraphDiff.compute(base, head)
        self.assertTrue(d.cycle_introduced)
        # Critical path is undefined when either side has a cycle.
        self.assertIsNone(d.critical_path)

    def test_critical_path_growth(self):
        base = _graph(_FakeParser({
            'lint': {'stage': 'build'},
            'build': {'stage': 'build', 'needs': ['lint']},
            'deploy': {'stage': 'deploy', 'needs': ['build']},
        }))
        head = _graph(_FakeParser({
            'lint': {'stage': 'build'},
            'build': {'stage': 'build', 'needs': ['lint']},
            'sign': {'stage': 'test', 'needs': ['build']},
            'deploy': {'stage': 'deploy', 'needs': ['sign']},
        }))
        d = GraphDiff.compute(base, head)
        self.assertEqual(d.critical_path, (3, 4))
        self.assertTrue(d.critical_path_regressed)

    def test_critical_path_unchanged_when_jobs_added_in_parallel(self):
        base = _graph(_FakeParser({
            'a': {'stage': 'x'},
            'b': {'stage': 'x', 'needs': ['a']},
        }))
        head = _graph(_FakeParser({
            'a': {'stage': 'x'},
            'b': {'stage': 'x', 'needs': ['a']},
            'c': {'stage': 'x', 'needs': ['a']},  # parallel branch
        }))
        d = GraphDiff.compute(base, head)
        self.assertEqual(d.critical_path, (2, 2))
        self.assertFalse(d.critical_path_regressed)


class TestIsolatedAdded(unittest.TestCase):
    def test_added_orphan_is_flagged(self):
        base = _graph(_FakeParser({'a': {'stage': 'x'}}))
        head = _graph(_FakeParser({
            'a': {'stage': 'x'},
            'orphan': {'stage': 'x'},  # no needs, nothing needs it
        }))
        d = GraphDiff.compute(base, head)
        self.assertEqual(d.isolated_added, ['orphan'])

    def test_added_wired_job_is_not_flagged(self):
        base = _graph(_FakeParser({'a': {'stage': 'x'}}))
        head = _graph(_FakeParser({
            'a': {'stage': 'x'},
            'b': {'stage': 'x', 'needs': ['a']},
        }))
        d = GraphDiff.compute(base, head)
        self.assertEqual(d.isolated_added, [])


class TestDiffEdgeCases(unittest.TestCase):
    def test_base_empty_all_added(self):
        head = _graph(_FakeParser({'a': {'stage': 'x'}, 'b': {'stage': 'x'}}))
        d = GraphDiff.compute(None, head)
        self.assertEqual(d.nodes_added, ['a', 'b'])
        self.assertEqual(d.nodes_removed, [])

    def test_head_empty_all_removed(self):
        base = _graph(_FakeParser({'a': {'stage': 'x'}, 'b': {'stage': 'x'}}))
        d = GraphDiff.compute(base, None)
        self.assertEqual(d.nodes_removed, ['a', 'b'])
        self.assertEqual(d.nodes_added, [])

    def test_ci_system_changed_short_circuits(self):
        base = _graph(_FakeParser({'a': {'stage': 'x'}}))
        head = _graph(_FakeParser({'b': {'stage': 'x'}}))
        d = GraphDiff.compute(
            base, head,
            base_system='GitLab CI', head_system='GitHub Actions',
        )
        # CRUCIAL: no structural diff attempted. The renderer relies
        # on this to print the migration notice instead of a misleading
        # "all jobs deleted" delta.
        self.assertEqual(d.ci_system_changed, ('GitLab CI', 'GitHub Actions'))
        self.assertEqual(d.nodes_added, [])
        self.assertEqual(d.nodes_removed, [])

    def test_parse_failure_short_circuits(self):
        # A YAML typo in head must NOT render as "every job deleted" —
        # this is the CRITICAL GAP called out in plan §5.
        base = _graph(_FakeParser({'a': {'stage': 'x'}, 'b': {'stage': 'x'}}))
        head = _graph(_FakeParser({}))  # would naively read as empty
        d = GraphDiff.compute(base, head, head_status='failed')
        self.assertEqual(d.head_status, 'failed')
        self.assertEqual(d.nodes_removed, [])


class TestRendering(unittest.TestCase):
    def _typical_delta(self):
        base = _graph(_FakeParser({
            'lint': {'stage': 'build'},
            'build': {'stage': 'build', 'needs': ['lint']},
            'deploy': {'stage': 'deploy', 'needs': ['build']},
        }))
        head = _graph(_FakeParser({
            'lint': {'stage': 'build'},
            'build': {'stage': 'build', 'needs': ['lint']},
            'sign': {'stage': 'test', 'needs': ['build']},
            'deploy': {'stage': 'deploy', 'needs': ['sign']},
        }))
        return GraphDiff.compute(base, head)

    def test_render_text_no_changes(self):
        same = _graph(_FakeParser({'a': {'stage': 'x'}}))
        out = render_text(GraphDiff.compute(same, same))
        self.assertIn('No pipeline changes', out)

    def test_render_markdown_includes_critical_path(self):
        out = render_markdown(self._typical_delta(),
                              system='GitHub Actions')
        self.assertIn('### Pipeline graph changes', out)
        self.assertIn('critical path', out)
        self.assertIn('3', out)
        self.assertIn('4', out)

    def test_render_markdown_flags_cycle(self):
        base = _graph(_FakeParser({'a': {'stage': 'x'}}))
        head = _graph(_FakeParser({
            'a': {'stage': 'x', 'needs': ['b']},
            'b': {'stage': 'x', 'needs': ['a']},
        }))
        out = render_markdown(GraphDiff.compute(base, head))
        self.assertIn('cycle introduced', out)

    def test_render_markdown_parse_failure_does_not_show_deletions(self):
        d = GraphDelta(head_status='failed', nodes_removed=['a', 'b', 'c'])
        # Hand-constructed delta: structurally we'd see "removed",
        # but the renderer must hide that behind a clear parse-failure
        # message so PR readers aren't misled.
        out = render_markdown(d)
        self.assertIn('parse failed', out)
        self.assertNotIn('− job', out)

    def test_render_json_round_trips(self):
        out = render_json(self._typical_delta(), system='GitHub Actions')
        payload = json.loads(out)
        self.assertEqual(payload['system'], 'GitHub Actions')
        self.assertIn('critical_path', payload)
        self.assertEqual(payload['critical_path']['head'], 4)
        self.assertTrue(payload['has_changes'])

    def test_render_json_migration_notice(self):
        d = GraphDelta(ci_system_changed=('GitLab CI', 'GitHub Actions'))
        payload = json.loads(render_json(d))
        self.assertEqual(payload['ci_system_changed']['from'], 'GitLab CI')
        self.assertEqual(payload['ci_system_changed']['to'], 'GitHub Actions')


class TestRenderingBranches(unittest.TestCase):
    """Exhaustive coverage of every rendering branch.

    These cases drive lines that the more narrative tests above don't
    reach — particularly the migration / parse-failure / no-changes
    short-circuits in both renderers and the isolated-job tail.
    """

    def test_markdown_ci_system_changed(self):
        d = GraphDelta(ci_system_changed=('GitLab CI', 'GitHub Actions'))
        out = render_markdown(d, system='GitHub Actions')
        self.assertIn('CI system changed', out)
        self.assertIn('GitLab CI', out)
        self.assertIn('GitHub Actions', out)
        # Migration short-circuits — no structural body.
        self.assertNotIn('+ job', out)

    def test_markdown_no_changes(self):
        out = render_markdown(GraphDelta())
        self.assertIn('No pipeline changes', out)

    def test_markdown_parse_failed_base_only(self):
        # Drive the base-side ``failed`` branch in the renderer — the
        # earlier head-only test only exercises the other arm.
        d = GraphDelta(base_status='failed')
        out = render_markdown(d)
        self.assertIn('parse failed on base', out)

    def test_markdown_full_structural_delta(self):
        # One delta that exercises every structural rendering branch
        # in render_markdown: added, removed, stage change, isolated.
        d = GraphDelta(
            nodes_added=['scan', 'orphan'],
            nodes_removed=['deprecated'],
            nodes_stage_changed=[('build', 'build', 'compile')],
            edges_added=[('a', 'scan', 'needs')],
            edges_removed=[('a', 'deprecated', 'needs')],
            isolated_added=['orphan'],
            critical_path=(2, 3),
        )
        out = render_markdown(d)
        self.assertIn('+ job** `scan`', out)
        self.assertIn('− job** `deprecated`', out)
        self.assertIn('~ stage** `build`', out)
        self.assertIn('+ edge** `a` → `scan`', out)
        self.assertIn('− edge** `a` → `deprecated`', out)
        self.assertIn('critical path', out)
        self.assertIn('`orphan` has no edges', out)

    def test_text_ci_system_changed(self):
        d = GraphDelta(ci_system_changed=('GitLab CI', 'GitHub Actions'))
        out = render_text(d, system='GitHub Actions')
        self.assertIn('CI system changed', out)
        self.assertIn('GitLab CI -> GitHub Actions', out)
        self.assertIn('not comparable', out)

    def test_text_parse_failed_base_only(self):
        d = GraphDelta(base_status='failed')
        out = render_text(d)
        self.assertIn('parse failed on base', out)

    def test_text_parse_failed_both_sides(self):
        d = GraphDelta(base_status='failed', head_status='failed')
        out = render_text(d)
        self.assertIn('base, head', out)

    def test_text_full_structural_delta(self):
        d = GraphDelta(
            nodes_added=['scan', 'orphan'],
            nodes_removed=['deprecated'],
            nodes_stage_changed=[('build', 'build', 'compile')],
            edges_added=[('a', 'scan', 'needs')],
            edges_removed=[('a', 'deprecated', 'needs')],
            cycle_introduced=True,
            critical_path=(2, 3),
            isolated_added=['orphan'],
        )
        out = render_text(d)
        # Each branch contributes a labelled section header — checking
        # the headers is enough to confirm every branch executed.
        self.assertIn('Added jobs:', out)
        self.assertIn('Removed jobs:', out)
        self.assertIn('Stage changes:', out)
        self.assertIn('Added edges:', out)
        self.assertIn('Removed edges:', out)
        self.assertIn('cycle introduced', out)
        self.assertIn('Critical path: 2 -> 3', out)
        self.assertIn('Isolated added jobs', out)
        self.assertIn('! orphan', out)

    def test_json_includes_stage_changes_and_isolated(self):
        d = GraphDelta(
            nodes_stage_changed=[('build', 'build', 'compile')],
            isolated_added=['orphan'],
            nodes_added=['orphan'],
        )
        payload = json.loads(render_json(d))
        self.assertEqual(
            payload['nodes_stage_changed'],
            [{'job': 'build', 'from': 'build', 'to': 'compile'}],
        )
        self.assertEqual(payload['isolated_added'], ['orphan'])
        self.assertIsNone(payload['critical_path'])
        self.assertIsNone(payload['ci_system_changed'])


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
