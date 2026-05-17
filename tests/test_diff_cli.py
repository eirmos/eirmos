"""End-to-end tests for the ``eirmos diff`` CLI subcommand."""

import io
import json
import os
import shutil
import tempfile
import textwrap
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from eirmos.cli import main


def _ci(stages, jobs):
    """Render a minimal .gitlab-ci.yml fixture body."""
    lines = ['stages: [' + ', '.join(stages) + ']']
    for name, cfg in jobs.items():
        lines.append(f'{name}:')
        lines.append(f'  stage: {cfg["stage"]}')
        if 'needs' in cfg:
            needs = ', '.join(cfg['needs'])
            lines.append(f'  needs: [{needs}]')
        lines.append(f'  script: [echo {name}]')
    return '\n'.join(lines) + '\n'


class _DiffHarness(unittest.TestCase):
    """Two writable temp dirs and a ``run`` helper. One file per side."""

    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.head = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.base)
        self.addCleanup(shutil.rmtree, self.head)

    def _write(self, directory, body, name='.gitlab-ci.yml'):
        Path(directory, name).write_text(body)

    def _run(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = main(['diff', self.base, self.head, '--no-color', *args])
        return rc, out.getvalue(), err.getvalue()


class TestDiffCliBasic(_DiffHarness):
    def test_identical_graphs_report_no_changes(self):
        body = _ci(['build'], {'a': {'stage': 'build'}})
        self._write(self.base, body)
        self._write(self.head, body)
        rc, out, _ = self._run()
        self.assertEqual(rc, 0)
        self.assertIn('No pipeline changes', out)

    def test_added_job_shows_in_text(self):
        self._write(self.base, _ci(['build'], {'a': {'stage': 'build'}}))
        self._write(self.head, _ci(['build'], {
            'a': {'stage': 'build'},
            'b': {'stage': 'build', 'needs': ['a']},
        }))
        rc, out, _ = self._run()
        self.assertEqual(rc, 0)
        self.assertIn('+ b', out)
        self.assertIn('a -> b', out)

    def test_markdown_format(self):
        self._write(self.base, _ci(['build'], {'a': {'stage': 'build'}}))
        self._write(self.head, _ci(['build'], {
            'a': {'stage': 'build'},
            'b': {'stage': 'build', 'needs': ['a']},
        }))
        rc, out, _ = self._run('--format', 'markdown')
        self.assertEqual(rc, 0)
        self.assertIn('### Pipeline graph changes', out)
        self.assertIn('`b`', out)

    def test_json_format_is_valid_json(self):
        self._write(self.base, _ci(['build'], {'a': {'stage': 'build'}}))
        self._write(self.head, _ci(['build'], {
            'a': {'stage': 'build'},
            'b': {'stage': 'build', 'needs': ['a']},
        }))
        rc, out, _ = self._run('--format', 'json')
        self.assertEqual(rc, 0)
        payload = json.loads(out)
        self.assertEqual(payload['nodes_added'], ['b'])
        self.assertIn('system', payload)

    def test_output_to_file(self):
        self._write(self.base, _ci(['build'], {'a': {'stage': 'build'}}))
        self._write(self.head, _ci(['build'], {'a': {'stage': 'test'}}))
        out_path = os.path.join(self.base, 'out.txt')
        rc, _, _ = self._run('--format', 'text', '--output', out_path)
        self.assertEqual(rc, 0)
        body = Path(out_path).read_text()
        self.assertIn('build -> test', body)


class TestDiffCliFailOn(_DiffHarness):
    def test_fail_on_cycle_triggers(self):
        # head introduces a cycle (a needs b, b needs a)
        self._write(self.base, _ci(['x'], {'a': {'stage': 'x'}}))
        self._write(self.head, textwrap.dedent("""\
            stages: [x]
            a:
              stage: x
              needs: [b]
              script: [echo a]
            b:
              stage: x
              needs: [a]
              script: [echo b]
        """))
        rc, _, _ = self._run('--fail-on', 'cycle')
        self.assertEqual(rc, 2)

    def test_fail_on_cycle_passes_when_no_cycle(self):
        self._write(self.base, _ci(['x'], {'a': {'stage': 'x'}}))
        self._write(self.head, _ci(['x'], {
            'a': {'stage': 'x'},
            'b': {'stage': 'x', 'needs': ['a']},
        }))
        rc, _, _ = self._run('--fail-on', 'cycle')
        self.assertEqual(rc, 0)

    def test_fail_on_critical_path_regression(self):
        self._write(self.base, _ci(['x'], {
            'a': {'stage': 'x'},
            'b': {'stage': 'x', 'needs': ['a']},
        }))
        self._write(self.head, _ci(['x'], {
            'a': {'stage': 'x'},
            'b': {'stage': 'x', 'needs': ['a']},
            'c': {'stage': 'x', 'needs': ['b']},
        }))
        rc, _, _ = self._run('--fail-on', 'critical-path-regression')
        self.assertEqual(rc, 2)

    def test_default_exits_zero_even_with_cycle(self):
        # Default is report-only — non-zero exit is opt-in.
        self._write(self.base, _ci(['x'], {'a': {'stage': 'x'}}))
        self._write(self.head, textwrap.dedent("""\
            stages: [x]
            a:
              stage: x
              needs: [b]
              script: [echo a]
            b:
              stage: x
              needs: [a]
              script: [echo b]
        """))
        rc, _, _ = self._run()
        self.assertEqual(rc, 0)


class TestDiffCliEdgeCases(_DiffHarness):
    def test_base_has_no_ci_config(self):
        # base directory left empty; head has a config.
        self._write(self.head, _ci(['x'], {
            'a': {'stage': 'x'},
            'b': {'stage': 'x', 'needs': ['a']},
        }))
        rc, out, _ = self._run()
        self.assertEqual(rc, 0)
        # Everything in head reads as added.
        self.assertIn('+ a', out)
        self.assertIn('+ b', out)

    def test_head_has_no_ci_config(self):
        self._write(self.base, _ci(['x'], {
            'a': {'stage': 'x'},
            'b': {'stage': 'x', 'needs': ['a']},
        }))
        rc, out, _ = self._run()
        self.assertEqual(rc, 0)
        self.assertIn('- a', out)
        self.assertIn('- b', out)

    def test_parse_failure_is_not_silent_deletion(self):
        # base has 3 jobs; head has a malformed YAML.
        # Naive diffing would render this as "everything deleted" —
        # the CRITICAL GAP from plan §5. Verify we instead surface
        # the parse failure clearly.
        self._write(self.base, _ci(['x'], {
            'a': {'stage': 'x'},
            'b': {'stage': 'x'},
            'c': {'stage': 'x'},
        }))
        Path(self.head, '.gitlab-ci.yml').write_text(
            "key: value\n  bad: : indentation\n"
        )
        rc, out, _ = self._run()
        self.assertEqual(rc, 0)
        self.assertIn('parse failed', out.lower())
        # Critically, the body must NOT list "- a / - b / - c".
        self.assertNotIn('- a', out)
        self.assertNotIn('- b', out)

    def test_ci_system_change(self):
        # base = GitLab CI, head = GitHub Actions workflow.
        self._write(self.base, _ci(['build'], {'a': {'stage': 'build'}}))
        workflows = Path(self.head, '.github', 'workflows')
        workflows.mkdir(parents=True)
        (workflows / 'ci.yml').write_text(textwrap.dedent("""\
            name: ci
            on: [push]
            jobs:
              build:
                runs-on: ubuntu-latest
                steps:
                  - run: echo hi
        """))
        rc, out, _ = self._run()
        self.assertEqual(rc, 0)
        self.assertIn('CI system changed', out)

    def test_missing_base_directory(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = main(['diff', '/no/such/dir', self.head, '--no-color'])
        self.assertEqual(rc, 1)
        self.assertIn('does not exist', err.getvalue())


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
