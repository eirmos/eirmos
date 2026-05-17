"""Command-line entry point.

Kept intentionally thin: argument parsing + parser/formatter
selection. All real logic lives in the dedicated modules.

Parser selection is driven by the
:mod:`eirmos.parsers.registry`, so adding a new CI/CD
system is a matter of registering a :class:`ParserAdapter`.
"""

import argparse
import sys
from pathlib import Path

from .colors import Colors
from .graph import DependencyGraph
from .parsers import detect as detect_adapter, REGISTRY
from .parsers.gitlab import GitLabCIParser
from .formatters.tree import TreeFormatter
from .formatters.mermaid import MermaidFormatter
from .formatters.dot import DotFormatter
from .formatters.summary import SummaryFormatter
from .formatters.variables import VariableFormatter
from .diff import GraphDiff
from .diff.git import GitResolveError, is_git_available, materialize_ref
from .diff.render import render_json, render_markdown, render_text


FORMATTERS = {
    'tree': TreeFormatter,
    'mermaid': MermaidFormatter,
    'dot': DotFormatter,
    'summary': SummaryFormatter,
    'variables': VariableFormatter,
}



def build_arg_parser():
    supported = ', '.join(a.name for a in REGISTRY) or 'none registered'
    arg_parser = argparse.ArgumentParser(
        prog='eirmos',
        description=(
            'CI/CD Pipeline Visualiser - Parse and visualise job dependencies. '
            f'Supported systems: {supported}.'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    arg_parser.add_argument('path', nargs='?', default='.',
                            help='Path to repository root (default: current directory)')
    arg_parser.add_argument('--format', '-f', choices=list(FORMATTERS.keys()),
                            default='tree', help='Output format (default: tree)')
    arg_parser.add_argument('--stage', '-s', default=None,
                            help='Filter output to a specific stage')
    arg_parser.add_argument('--job', '-j', default=None,
                            help='Show detailed dependencies for a specific job')
    arg_parser.add_argument('--no-includes', action='store_true',
                            help='Do not follow local include directives (GitLab only)')
    arg_parser.add_argument('--output', '-o', default=None,
                            help='Output file path (default: stdout)')
    arg_parser.add_argument('--no-color', action='store_true',
                            help='Disable colored output')
    arg_parser.add_argument('--list-stages', action='store_true',
                            help='List all stages and exit')
    arg_parser.add_argument('--list-jobs', action='store_true',
                            help='List all jobs and exit')
    arg_parser.add_argument('--ci', default=None,
                            choices=[a.slug for a in REGISTRY],
                            help='Force a specific CI system instead of auto-detection')
    arg_parser.add_argument('--tui', action='store_true',
                            help='Launch the interactive terminal UI')
    return arg_parser


def _select_ci_file(base_path, forced_slug=None):
    """Return ``(adapter, main_ci_file)`` for ``base_path``.

    If ``forced_slug`` is given, only that adapter is consulted.
    Otherwise, the registry is queried in registration order and the
    first hit wins.
    """
    if forced_slug:
        for adapter in REGISTRY:
            if adapter.slug == forced_slug:
                main = adapter.detect(base_path)
                if main is not None:
                    print(f"{Colors.DIM}Forced CI system: {adapter.name} "
                          f"({main.name}){Colors.RESET}", file=sys.stderr)
                    return adapter, main
        return None, None

    adapter, main_file = detect_adapter(base_path)
    if adapter is not None:
        print(f"{Colors.DIM}Detected {adapter.name}: {main_file.name}"
              f"{Colors.RESET}", file=sys.stderr)
        return adapter, main_file

    return None, None


def find_ci_files(base_path):
    """Return a list of all detected CI configuration files."""
    base_path = Path(base_path).resolve()
    files = []
    for adapter in REGISTRY:
        main = adapter.detect(base_path)
        if main is not None:
            files.append(main)
    return files


_DIFF_FORMATS = {
    'text': render_text,
    'markdown': render_markdown,
    'json': render_json,
}

_DIFF_FAIL_ON_CHOICES = ('cycle', 'critical-path-regression')


def build_diff_arg_parser():
    """Argparser for the ``eirmos diff`` subcommand.

    Per plan Decision 1 (recommended option A), inputs are two directory
    paths — the caller (CI / git worktree) is responsible for laying out
    each ref's config. No git subprocess fragility in eirmos itself.
    """
    p = argparse.ArgumentParser(
        prog='eirmos diff',
        description='Diff two pipeline graphs (base vs. head directory).',
    )
    # Both positionals are optional so ``--base-ref`` can substitute
    # for the base directory. Validation in ``diff_main`` enforces the
    # combinations that actually make sense.
    p.add_argument('base', nargs='?', default=None,
                   help='Directory containing the base CI config '
                        '(omit when using --base-ref)')
    p.add_argument('head', nargs='?', default=None,
                   help='Directory containing the head CI config '
                        "(defaults to '.' when --base-ref is used)")
    p.add_argument('--base-ref', dest='base_ref', default=None, metavar='REF',
                   help=('Resolve the base from a git ref (e.g. origin/develop) '
                         'instead of a directory. Materialized via '
                         '`git worktree add --detach` and cleaned up on exit.'))
    p.add_argument('--format', '-f', choices=list(_DIFF_FORMATS.keys()),
                   default='text', help='Output format (default: text)')
    p.add_argument('--output', '-o', default=None,
                   help='Write output to this file instead of stdout')
    p.add_argument('--no-color', action='store_true',
                   help='Disable colored stderr output')
    p.add_argument('--ci', default=None,
                   choices=[a.slug for a in REGISTRY],
                   help='Force a specific CI system for BOTH sides')
    p.add_argument(
        '--fail-on', action='append', default=[],
        choices=list(_DIFF_FAIL_ON_CHOICES),
        help=('Exit non-zero when the condition is met. May be repeated. '
              'Default: report-only (exit 0).'),
    )
    return p


def _parse_side(label, directory, forced_slug):
    """Parse one side of the diff, returning ``(adapter, parser)``.

    ``adapter`` is ``None`` when no CI config was detected — the caller
    treats that as an empty graph (every job in the *other* side reads as
    added or removed). A *failed* parse is distinct: ``parser.status``
    flips to ``'failed'`` and the diff short-circuits.
    """
    directory = Path(directory).resolve()
    if not directory.exists():
        print(f"ERROR: {label} path '{directory}' does not exist.",
              file=sys.stderr)
        return None, None, True

    adapter, main_file = _select_ci_file(directory, forced_slug=forced_slug)
    if adapter is None or main_file is None:
        return None, None, False

    parser = adapter.parser_class(
        base_path=directory, **adapter.parser_kwargs(argparse.Namespace())
    )
    parser.parse(main_file)
    return adapter, parser, False


def _resolve_diff_dirs(args):
    """Translate parsed args into ``(base_dir, head_dir)`` or an error code.

    Two valid invocations:
      eirmos diff <base> <head>               -> (base, head)
      eirmos diff --base-ref REF [<head>]     -> (None, head); caller
                                                  materializes the ref.
    Anything else is a usage error.
    """
    if args.base_ref:
        if args.head is not None:
            # User wrote ``diff <a> <b> --base-ref X`` — the two
            # positionals can't both mean "head". Reject explicitly
            # rather than silently dropping one.
            print("ERROR: --base-ref is mutually exclusive with the "
                  "base directory positional.", file=sys.stderr)
            return None, None, 1
        # With --base-ref, the (optional) first positional is the head.
        head_dir = args.base or '.'
        return None, head_dir, 0

    if not args.base or not args.head:
        print("ERROR: provide both base and head directories, or use "
              "--base-ref.", file=sys.stderr)
        return None, None, 1
    return args.base, args.head, 0


def _run_diff(args, base_dir, head_dir):
    """Core diff flow: parse both sides, render, return exit code.

    Split out from :func:`diff_main` so the ``--base-ref`` path can wrap
    it inside the worktree context manager without duplicating logic.
    """
    base_adapter, base_parser, base_err = _parse_side(
        'base', base_dir, args.ci)
    head_adapter, head_parser, head_err = _parse_side(
        'head', head_dir, args.ci)
    if base_err or head_err:
        return 1

    base_graph = DependencyGraph(base_parser) if base_parser else None
    head_graph = DependencyGraph(head_parser) if head_parser else None

    base_system = base_adapter.name if base_adapter else None
    head_system = head_adapter.name if head_adapter else None

    delta = GraphDiff.compute(
        base_graph, head_graph,
        base_system=base_system, head_system=head_system,
        base_status=base_parser.status if base_parser else 'empty',
        head_status=head_parser.status if head_parser else 'empty',
    )

    # The "system" we label in the output: prefer the head side (where
    # the PR landed), fall back to base, then None.
    label_system = head_system or base_system
    renderer = _DIFF_FORMATS[args.format]
    output = renderer(delta, system=label_system)

    if args.output:
        with open(args.output, 'w') as f:
            f.write(output)
        print(f"Output written to: {args.output}", file=sys.stderr)
    else:
        print(output, end='')

    # Exit codes (plan §4): default 0. ``--fail-on`` gates turn the
    # command into a CI gate. Repeatable so a project can opt into
    # multiple checks at once.
    for gate in args.fail_on:
        if gate == 'cycle' and delta.cycle_introduced:
            return 2
        if gate == 'critical-path-regression' and delta.critical_path_regressed:
            return 2
    return 0


def diff_main(argv):
    """Entry point for ``eirmos diff``."""
    args = build_diff_arg_parser().parse_args(argv)

    if args.no_color or args.output or not sys.stdout.isatty():
        Colors.disable()

    base_dir, head_dir, rc = _resolve_diff_dirs(args)
    if rc != 0:
        return rc

    if args.base_ref:
        if not is_git_available():
            print("ERROR: git is not installed or not on PATH.",
                  file=sys.stderr)
            return 1
        head_path = Path(head_dir).resolve()
        if not head_path.exists():
            print(f"ERROR: head path '{head_dir}' does not exist.",
                  file=sys.stderr)
            return 1
        try:
            with materialize_ref(args.base_ref, head_path) as base_path:
                return _run_diff(args, str(base_path), head_dir)
        except GitResolveError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

    return _run_diff(args, base_dir, head_dir)


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    # Lightweight pre-dispatch: the diff subcommand has a totally
    # different positional layout (two paths, not one). Forcing it
    # through the main parser would either require a fragile
    # ``required=False`` subparser dance or break the existing
    # ``eirmos <path>`` UX. Pre-dispatch keeps both clean.
    if argv and argv[0] == 'diff':
        return diff_main(argv[1:])
    args = build_arg_parser().parse_args(argv)

    if args.tui:
        from .tui import run_tui
        run_tui(args.path)
        return 0

    if args.no_color or args.output or not sys.stdout.isatty():
        Colors.disable()

    base_path = Path(args.path).resolve()
    if not base_path.exists():
        print(f"ERROR: Path '{args.path}' does not exist.", file=sys.stderr)
        return 1

    adapter, main_ci_file = _select_ci_file(base_path, forced_slug=args.ci)
    if not main_ci_file or adapter is None:
        supported = ', '.join(a.name for a in REGISTRY)
        print(f"ERROR: No supported CI files found ({supported}).", file=sys.stderr)
        return 1

    print(f"{Colors.DIM}Parsing CI files from: {base_path}{Colors.RESET}", file=sys.stderr)

    parser = adapter.parser_class(base_path=base_path, **adapter.parser_kwargs(args))
    parser.parse(main_ci_file)

    print(f"{Colors.DIM}Parsed {len(parser.parsed_files)} files, "
          f"found {len(parser.jobs)} jobs.{Colors.RESET}\n", file=sys.stderr)

    if args.list_stages:
        graph = DependencyGraph(parser)
        for stage in graph.get_ordered_stages():
            count = len(graph.stage_jobs.get(stage, []))
            print(f"{stage} ({count} jobs)")
        return 0

    if args.list_jobs:
        for job_name in sorted(parser.jobs.keys()):
            stage = parser.get_job_stage(job_name)
            print(f"{job_name:<60} [{stage}]")
        return 0

    graph = DependencyGraph(parser)
    formatter = FORMATTERS[args.format](parser, graph)
    output = formatter.render(filter_stage=args.stage, filter_job=args.job)

    if args.output:
        with open(args.output, 'w') as f:
            f.write(output)
        print(f"Output written to: {args.output}", file=sys.stderr)
    else:
        print(output)
    return 0


if __name__ == '__main__':  # pragma: no cover
    sys.exit(main())
