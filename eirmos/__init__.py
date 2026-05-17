"""CI/CD pipeline visualiser.

A small library + CLI for parsing CI/CD pipeline definitions and
rendering them in various formats (tree, mermaid, dot, summary).

Supported systems: GitLab CI, GitHub Actions, Jenkins, CircleCI,
Azure Pipelines, Bitbucket Pipelines, Drone CI, Woodpecker CI,
Travis CI, AppVeyor, Buildkite, Codefresh, Semaphore.

The package is organised in clear architectural layers:

    parsers/    - read pipeline definition files and produce a domain model
    graph.py    - build a dependency graph from a parser
    formatters/ - render graphs to text/diagram formats
    cli.py      - thin command-line entry point
    colors.py   - ANSI color helpers (presentation only)

New CI systems can be supported by implementing
:class:`eirmos.parsers.base.BasePipelineParser` and
registering a :class:`eirmos.parsers.registry.ParserAdapter`.
"""

from .colors import Colors
from .parsers.gitlab import GitLabCIParser
from .parsers.github import GitHubActionsParser
from .parsers.jenkins import JenkinsParser
from .parsers.circleci import CircleCIParser
from .parsers.azure import AzurePipelinesParser
from .parsers.bitbucket import BitbucketPipelinesParser
from .parsers.drone import DroneParser, WoodpeckerParser
from .parsers.travis import TravisCIParser
from .parsers.appveyor import AppVeyorParser
from .parsers.buildkite import BuildkiteParser
from .parsers.codefresh import CodefreshParser
from .parsers.semaphore import SemaphoreParser
from .parsers.base import BasePipelineParser
from .parsers.registry import ParserAdapter, REGISTRY, register_adapter
from .graph import DependencyGraph
from .diff import GraphDelta, GraphDiff
from .formatters.tree import TreeFormatter
from .formatters.mermaid import MermaidFormatter
from .formatters.dot import DotFormatter
from .formatters.summary import SummaryFormatter
from .formatters.variables import VariableFormatter
from .tui import EirmosTUI, run_tui

__all__ = [
    "Colors",
    "BasePipelineParser",
    "GitLabCIParser",
    "GitHubActionsParser",
    "JenkinsParser",
    "CircleCIParser",
    "AzurePipelinesParser",
    "BitbucketPipelinesParser",
    "DroneParser",
    "WoodpeckerParser",
    "TravisCIParser",
    "AppVeyorParser",
    "BuildkiteParser",
    "CodefreshParser",
    "SemaphoreParser",
    "ParserAdapter",
    "REGISTRY",
    "register_adapter",
    "DependencyGraph",
    "GraphDelta",
    "GraphDiff",
    "TreeFormatter",
    "MermaidFormatter",
    "DotFormatter",
    "SummaryFormatter",
    "VariableFormatter",
    "EirmosTUI",
    "run_tui",
]
