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


def main(argv=None):
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
