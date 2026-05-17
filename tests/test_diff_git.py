"""Tests for the ``--base-ref`` git resolver path of ``eirmos diff``.

Each test creates a tiny throwaway git repo so the worktree codepath
runs end-to-end. ``unittest`` skip semantics let the suite still pass
on machines without git on ``$PATH`` — that's a real CI matrix case.
"""

import io
import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from eirmos.cli import main
from eirmos.diff.git import (
    GitResolveError,
    is_git_available,
    materialize_ref,
)


_GIT_REQUIRED = unittest.skipUnless(is_git_available(),
                                    "git not available on PATH")


def _git(repo, *args):
    """Run a git command inside ``repo`` and assert success."""
    subprocess.run(['git', *args], cwd=str(repo), check=True,
                   capture_output=True)


def _make_repo(base_body, head_body):
    """Initialise a git repo: ``main`` has ``base_body``; ``feature`` has ``head_body``.

    Returns the repo path. Caller is responsible for cleanup.
    """
    repo = Path(tempfile.mkdtemp(prefix='eirmos-test-repo-'))
    _git(repo, 'init', '-q', '-b', 'main')
    _git(repo, 'config', 'user.email', 't@e')
    _git(repo, 'config', 'user.name', 't')
    (repo / '.gitlab-ci.yml').write_text(base_body)
    _git(repo, 'add', '.')
    _git(repo, 'commit', '-q', '-m', 'base')

    _git(repo, 'checkout', '-q', '-b', 'feature')
    (repo / '.gitlab-ci.yml').write_text(head_body)
    _git(repo, 'add', '.')
    _git(repo, 'commit', '-q', '-m', 'head')
    return repo


@_GIT_REQUIRED
class TestMaterializeRef(unittest.TestCase):
    """Direct tests of the context-manager API."""

    def setUp(self):
        body = "stages: [x]\na:\n  stage: x\n  script: [echo a]\n"
        self.repo = _make_repo(body, body + "b:\n  stage: x\n  script: [echo b]\n")
        self.addCleanup(shutil.rmtree, self.repo, ignore_errors=True)

    def test_yields_directory_with_ref_contents(self):
        with materialize_ref('main', self.repo) as base:
            self.assertTrue((base / '.gitlab-ci.yml').exists())
            # ``main`` only has job ``a``; ``b`` should be absent.
            text = (base / '.gitlab-ci.yml').read_text()
            self.assertIn('a:', text)
            self.assertNotIn('b:', text)

    def test_cleans_up_on_normal_exit(self):
        with materialize_ref('main', self.repo) as base:
            base_path = base
            self.assertTrue(base_path.exists())
        # Once the ``with`` block exits, the tempdir is gone AND the
        # worktree list is pruned — otherwise we'd litter ``git
        # worktree list`` on every diff.
        self.assertFalse(base_path.exists())
        out = subprocess.run(['git', 'worktree', 'list', '--porcelain'],
                             cwd=str(self.repo), capture_output=True, text=True)
        self.assertNotIn(str(base_path), out.stdout)

    def test_cleans_up_on_exception(self):
        try:
            with materialize_ref('main', self.repo) as base:
                base_path = base
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        self.assertFalse(base_path.exists())

    def test_unknown_ref_raises(self):
        with self.assertRaises(GitResolveError) as ctx:
            with materialize_ref('does-not-exist', self.repo):
                pass  # pragma: no cover
        self.assertIn('does-not-exist', str(ctx.exception))

    def test_not_a_git_repo_raises(self):
        non_repo = Path(tempfile.mkdtemp(prefix='eirmos-test-nogit-'))
        self.addCleanup(shutil.rmtree, non_repo, ignore_errors=True)
        with self.assertRaises(GitResolveError):
            with materialize_ref('main', non_repo):
                pass  # pragma: no cover


@_GIT_REQUIRED
class TestDiffCliBaseRef(unittest.TestCase):
    """End-to-end CLI tests through ``main(['diff', '--base-ref', ...])``."""

    def setUp(self):
        base_body = textwrap.dedent("""\
            stages: [build, release]
            lint:
              stage: build
              script: [echo lint]
            build:
              stage: build
              needs: [lint]
              script: [echo build]
            ship:
              stage: release
              needs: [build]
              script: [echo ship]
        """)
        head_body = textwrap.dedent("""\
            stages: [build, test, release]
            lint:
              stage: build
              script: [echo lint]
            build:
              stage: build
              needs: [lint]
              script: [echo build]
            sign:
              stage: test
              needs: [build]
              script: [echo sign]
            ship:
              stage: release
              needs: [sign]
              script: [echo ship]
        """)
        self.repo = _make_repo(base_body, head_body)
        self.addCleanup(shutil.rmtree, self.repo, ignore_errors=True)

    def _run(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = main(['diff', *args, '--no-color'])
        return rc, out.getvalue(), err.getvalue()

    def test_diff_against_main(self):
        rc, out, _ = self._run('--base-ref', 'main', str(self.repo))
        self.assertEqual(rc, 0)
        self.assertIn('+ sign', out)
        # The structural change worth catching: edge re-routing.
        self.assertIn('build -> sign', out)
        self.assertIn('sign -> ship', out)
        self.assertIn('build -> ship', out)  # removed

    def test_head_defaults_to_cwd(self):
        # When no head positional is given, cwd is used. We can't ``cd``
        # the test process safely, so we lean on os.chdir / restoration.
        old = os.getcwd()
        os.chdir(str(self.repo))
        try:
            rc, out, _ = self._run('--base-ref', 'main')
        finally:
            os.chdir(old)
        self.assertEqual(rc, 0)
        self.assertIn('+ sign', out)

    def test_unknown_ref_returns_error(self):
        rc, _, err = self._run('--base-ref', 'no-such-ref', str(self.repo))
        self.assertEqual(rc, 1)
        self.assertIn('no-such-ref', err)

    def test_non_git_head_returns_error(self):
        non_repo = tempfile.mkdtemp(prefix='eirmos-test-nogit-')
        self.addCleanup(shutil.rmtree, non_repo, ignore_errors=True)
        rc, _, err = self._run('--base-ref', 'main', non_repo)
        self.assertEqual(rc, 1)
        # Either "not a git repository" (from rev-parse) or similar.
        self.assertTrue('git' in err.lower())

    def test_mutual_exclusion_with_positional_base(self):
        # User wrote two positionals AND --base-ref — reject loudly.
        rc, _, err = self._run('/tmp/anywhere', str(self.repo),
                               '--base-ref', 'main')
        self.assertEqual(rc, 1)
        self.assertIn('mutually exclusive', err)

    def test_missing_both_dirs_and_ref_errors(self):
        rc, _, err = self._run()
        self.assertEqual(rc, 1)
        self.assertIn('--base-ref', err)


class TestDiffCliUsageWithoutGit(unittest.TestCase):
    """The argparse usage rules don't require git to test."""

    def test_help_mentions_base_ref(self):
        # ``--help`` exits 0 via SystemExit. We catch and assert.
        out = io.StringIO()
        with redirect_stdout(out):
            try:
                main(['diff', '--help'])
            except SystemExit:
                pass
        self.assertIn('--base-ref', out.getvalue())


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
