"""Tests for the Drone CI / Woodpecker CI parser."""

import tempfile
import unittest
from pathlib import Path

from eirmos.parsers.drone import DroneParser, WoodpeckerParser
from eirmos.graph import DependencyGraph


EXAMPLES = Path(__file__).parent / 'examples'


class TestDroneListForm(unittest.TestCase):
    def setUp(self):
        self.parser = DroneParser(base_path=EXAMPLES)
        self.parser.parse(EXAMPLES / '.drone.yml')

    def test_steps_discovered(self):
        self.assertEqual(set(self.parser.jobs.keys()),
                         {'clone', 'build', 'test', 'lint'})

    def test_explicit_depends_on_list(self):
        self.assertEqual(self.parser.get_job_needs('build'),
                         [{'job': 'clone', 'optional': False}])

    def test_explicit_depends_on_string(self):
        # lint uses string form (depends_on: clone)
        self.assertEqual(self.parser.get_job_needs('lint'),
                         [{'job': 'clone', 'optional': False}])

    def test_no_cycle(self):
        self.assertFalse(DependencyGraph(self.parser).has_cycle())


class TestWoodpeckerMapForm(unittest.TestCase):
    def setUp(self):
        self.parser = WoodpeckerParser(base_path=EXAMPLES)
        self.parser.parse(EXAMPLES / '.woodpecker.yml')

    def test_steps_discovered(self):
        self.assertEqual(set(self.parser.jobs.keys()),
                         {'build', 'test', 'publish'})

    def test_sequential_fallback(self):
        # build has no depends_on → first step, no deps
        self.assertEqual(self.parser.get_job_needs('build'), [])
        # test has no depends_on → falls back to previous (build)
        self.assertEqual(self.parser.get_job_needs('test'),
                         [{'job': 'build', 'optional': False}])

    def test_explicit_depends_on(self):
        self.assertEqual(self.parser.get_job_needs('publish'),
                         [{'job': 'test', 'optional': False}])


class TestDroneEdgeCases(unittest.TestCase):
    def test_missing_file(self):
        p = DroneParser(base_path=EXAMPLES)
        p.parse(EXAMPLES / 'nope.yml')
        self.assertEqual(p.jobs, {})

    def test_empty_steps(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'd.yml'
            f.write_text("kind: pipeline\nname: x\nsteps: []\n")
            p = DroneParser(base_path=d).parse(f)
            self.assertEqual(p.jobs, {})

    def test_single_step(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'd.yml'
            f.write_text(
                "kind: pipeline\nname: x\nsteps:\n  - name: only\n    image: alpine\n"
            )
            p = DroneParser(base_path=d).parse(f)
            self.assertEqual(set(p.jobs.keys()), {'only'})
            self.assertEqual(p.get_job_needs('only'), [])

    def test_cycle_fixture(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'd.yml'
            f.write_text(
                "kind: pipeline\nname: x\nsteps:\n"
                "  - name: a\n    image: alpine\n    depends_on: [b]\n"
                "  - name: b\n    image: alpine\n    depends_on: [a]\n"
            )
            p = DroneParser(base_path=d).parse(f)
            self.assertTrue(DependencyGraph(p).has_cycle())

    def test_multi_doc_yaml(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'd.yml'
            f.write_text(
                "kind: pipeline\nname: a\nsteps:\n  - name: s1\n    image: alpine\n"
                "---\n"
                "kind: pipeline\nname: b\nsteps:\n  - name: s2\n    image: alpine\n"
            )
            p = DroneParser(base_path=d).parse(f)
            self.assertEqual(set(p.jobs.keys()), {'s1', 's2'})

    def test_unknown_job_safe_defaults(self):
        p = DroneParser(base_path=EXAMPLES)
        self.assertEqual(p.get_job_stage('nope'), 'unknown')
        self.assertEqual(p.get_job_needs('nope'), [])

    def test_legacy_pipeline_key(self):
        # Older Drone configs used `pipeline:` instead of `steps:`.
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'd.yml'
            f.write_text(
                "pipeline:\n  build:\n    image: alpine\n    commands: [echo b]\n"
            )
            p = DroneParser(base_path=d).parse(f)
            self.assertEqual(set(p.jobs.keys()), {'build'})

    def test_non_dict_step_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'd.yml'
            f.write_text(
                "kind: pipeline\nname: x\nsteps:\n"
                "  - name: ok\n    image: alpine\n"
                "  - just-a-string\n"
            )
            p = DroneParser(base_path=d).parse(f)
            self.assertEqual(set(p.jobs.keys()), {'ok'})

    def test_non_dict_value_in_map_form_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'd.yml'
            f.write_text(
                "steps:\n  ok: {image: alpine}\n  bogus: not-a-dict\n"
            )
            p = DroneParser(base_path=d).parse(f)
            self.assertEqual(set(p.jobs.keys()), {'ok'})

    def test_steps_unexpected_type(self):
        # ``steps:`` is a string — not list, not dict — must not crash.
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'd.yml'
            f.write_text("steps: 'not-a-list'\n")
            p = DroneParser(base_path=d).parse(f)
            self.assertEqual(p.jobs, {})

    def test_depends_on_unexpected_type(self):
        # depends_on is an int — must not crash, treated as no deps.
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'd.yml'
            f.write_text(
                "steps:\n  a: {image: alpine}\n"
                "  b: {image: alpine, depends_on: 42}\n"
            )
            p = DroneParser(base_path=d).parse(f)
            self.assertEqual(p.get_job_needs('b'), [])

    def test_duplicate_step_name_disambiguated(self):
        # Two pipelines (multi-doc) with the same step name → second
        # gets a `#2` suffix.
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'd.yml'
            f.write_text(
                "kind: pipeline\nname: a\nsteps:\n  - name: build\n    image: alpine\n"
                "---\n"
                "kind: pipeline\nname: b\nsteps:\n  - name: build\n    image: alpine\n"
            )
            p = DroneParser(base_path=d).parse(f)
            self.assertIn('build', p.jobs)
            self.assertIn('build#2', p.jobs)

    def test_multi_doc_with_non_dict_doc(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'd.yml'
            f.write_text(
                "- not-a-dict\n"
                "---\n"
                "kind: pipeline\nname: x\nsteps:\n  - name: ok\n    image: alpine\n"
            )
            p = DroneParser(base_path=d).parse(f)
            self.assertEqual(set(p.jobs.keys()), {'ok'})


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
