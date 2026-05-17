"""Resolve a git ref into an on-disk directory for the diff engine.

Uses ``git worktree add --detach`` rather than ``git show`` so the
parser sees a real file tree — important for systems like GitLab CI
that follow ``include:`` directives across files. The worktree shares
the object store, so this is cheap on disk and fast even on large
repos.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from ..colors import Colors


class GitResolveError(Exception):
    """Raised when a ref cannot be materialized into a worktree.

    The message is user-facing — it lands directly on stderr.
    """


def _git(args, *, cwd: Path) -> subprocess.CompletedProcess:
    """Run a git subcommand. Caller decides how to handle non-zero exit."""
    return subprocess.run(
        ['git', *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )


@contextmanager
def materialize_ref(ref: str, repo_dir: Path) -> Iterator[Path]:
    """Yield a temp directory containing ``ref``'s tree; clean up on exit.

    Resolves ``ref`` in the git repository that contains ``repo_dir``.
    The worktree is added detached so we don't disturb any branches;
    on exit (success OR exception) it's removed and the tempdir is
    cleaned up.

    Raises :class:`GitResolveError` with a user-facing message if git
    is missing, the working directory isn't a git repo, or the ref
    cannot be resolved.
    """
    repo_dir = Path(repo_dir).resolve()

    # Locate the repo first so we get a clean "not a git repo" error
    # rather than a confusing one from ``worktree add`` later.
    proc = _git(['rev-parse', '--show-toplevel'], cwd=repo_dir)
    if proc.returncode != 0:
        # ``rev-parse`` writes its complaint to stderr; surface that
        # verbatim — it's already user-friendly.
        msg = proc.stderr.strip() or "not a git repository"
        raise GitResolveError(f"git: {msg}")

    # Validate the ref independently of ``worktree add`` so the user
    # sees "unknown revision foo", not a worktree-add diagnostic.
    proc = _git(['rev-parse', '--verify', f'{ref}^{{commit}}'], cwd=repo_dir)
    if proc.returncode != 0:
        raise GitResolveError(
            f"git ref {ref!r} not found "
            f"({proc.stderr.strip() or 'unknown revision'})"
        )

    tempdir = Path(tempfile.mkdtemp(prefix='eirmos-base-'))
    print(f"{Colors.DIM}Resolving {ref} into {tempdir}{Colors.RESET}",
          file=sys.stderr)
    proc = _git(
        ['worktree', 'add', '--detach', str(tempdir), ref],
        cwd=repo_dir,
    )
    if proc.returncode != 0:
        shutil.rmtree(tempdir, ignore_errors=True)
        raise GitResolveError(
            f"git worktree add failed: {proc.stderr.strip()}"
        )

    try:
        yield tempdir
    finally:
        # ``worktree remove`` deletes the temp tree and prunes git's
        # internal worktree list. ``--force`` covers the (rare) case of
        # the parser having created untracked files inside it.
        _git(
            ['worktree', 'remove', '--force', str(tempdir)],
            cwd=repo_dir,
        )
        # Defence-in-depth: if ``worktree remove`` failed silently
        # (already pruned, exotic state), make sure the tempdir is
        # gone so we don't leak it.
        shutil.rmtree(tempdir, ignore_errors=True)


def is_git_available() -> bool:
    """Return True if ``git`` is on ``$PATH`` and executable."""
    return shutil.which('git') is not None


__all__ = ["GitResolveError", "materialize_ref", "is_git_available"]
