"""End-to-end tests for the command-line interface."""

import io
import os
import shutil
import tempfile
import textwrap
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from eirmos.cli import find_ci_files, main


EXAMPLES = Path(__file__).parent / 'examples'


class TestFindCiFiles(unittest.TestCase):
    def test_finds_gitlab_files(self):
        # The examples directory contains *.gitlab-ci.yml fixtures
        files = find_ci_files(EXAMPLES)
        names = {p.name for p in files}
        found = any(n.endswith('.gitlab-ci.yml') for n in names)
        self.assertTrue(found, f"No .gitlab-ci.yml found among: {names}")


class TestCliInvocations(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        # Place a .gitlab-ci.yml at the repo root so the CLI can find it.
        Path(self.tmp, '.gitlab-ci.yml').write_text(textwrap.dedent("""\
            stages: [build, test]
            a:
              stage: build
              script: [echo a]
            b:
              stage: test
              needs: [a]
              script: [echo b]
        """))

    def _run(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = main([self.tmp, *args])
        return rc, out.getvalue(), err.getvalue()

    def test_default_tree(self):
        rc, out, _ = self._run('--no-color')
        self.assertEqual(rc, 0)
        self.assertIn('Stage: build', out)
        self.assertIn('Stage: test', out)

    def test_list_jobs(self):
        rc, out, _ = self._run('--list-jobs', '--no-color')
        self.assertEqual(rc, 0)
        self.assertIn('a ', out)
        self.assertIn('b ', out)

    def test_list_stages(self):
        rc, out, _ = self._run('--list-stages', '--no-color')
        self.assertEqual(rc, 0)
        self.assertIn('build', out)
        self.assertIn('test', out)

    def test_format_mermaid(self):
        rc, out, _ = self._run('--format', 'mermaid', '--no-color')
        self.assertEqual(rc, 0)
        self.assertIn('flowchart TD', out)

    def test_output_to_file(self):
        out_path = os.path.join(self.tmp, 'out.dot')
        rc, _, _ = self._run('--format', 'dot', '--output', out_path)
        self.assertEqual(rc, 0)
        contents = Path(out_path).read_text()
        self.assertTrue(contents.startswith('digraph pipeline'))

    def test_missing_path(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = main(['/no/such/dir', '--no-color'])
        self.assertEqual(rc, 1)
        self.assertIn('does not exist', err.getvalue())

    def test_no_ci_files(self):
        empty = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, empty)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = main([empty, '--no-color'])
        self.assertEqual(rc, 1)
        self.assertIn('No supported CI files', err.getvalue())


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
