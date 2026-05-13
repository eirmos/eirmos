"""CI/CD configuration parsers.

Each parser implements a small informal protocol used by the
``DependencyGraph`` and the formatters:

    parser.jobs            : dict[str, dict]
    parser.parsed_files    : set[str]
    parser.file_map        : dict[str, str]
    parser.stages          : list[str]            (optional)
    parser.templates       : dict[str, dict]      (optional)

    parser.get_job_stage(name)        -> str
    parser.get_job_needs(name)        -> list[dict]
    parser.get_job_extends(name)      -> list[str]
    parser.get_job_triggers(name)     -> dict | None
    parser.get_job_rules_summary(name)-> str
    parser.get_job_variables(name)    -> dict       (optional)
    parser.get_global_variables()     -> dict       (optional)

A small abstract base class is provided in :mod:`.base` so new
parsers can be added with confidence that they expose the same
surface. Each concrete parser is paired with a
:class:`~eirmos.parsers.registry.ParserAdapter` describing
its detection rules and instantiation kwargs.
"""

from pathlib import Path

from .base import BasePipelineParser
from .gitlab import GitLabCIParser
from .github import GitHubActionsParser
from .jenkins import JenkinsParser
from .circleci import CircleCIParser
from .azure import AzurePipelinesParser
from .bitbucket import BitbucketPipelinesParser
from .drone import DroneParser, WoodpeckerParser
from .travis import TravisCIParser
from .appveyor import AppVeyorParser
from .buildkite import BuildkiteParser
from .codefresh import CodefreshParser
from .semaphore import SemaphoreParser
from .registry import ParserAdapter, REGISTRY, register_adapter, detect

__all__ = [
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
    "detect",
]


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------
def _detect_github(base_path: Path):
    workflows_dir = base_path / '.github' / 'workflows'
    if workflows_dir.exists():
        files = sorted(
            list(workflows_dir.glob('*.yml')) + list(workflows_dir.glob('*.yaml'))
        )
        if files:
            return files[0]
    return None


def _detect_gitlab(base_path: Path):
    main = base_path / '.gitlab-ci.yml'
    if main.exists():
        return main
    for p in sorted(base_path.glob('**/*.gitlab-ci.yml')):
        return p
    return None


def _detect_circleci(base_path: Path):
    for name in ('config.yml', 'config.yaml'):
        p = base_path / '.circleci' / name
        if p.exists():
            return p
    return None


def _detect_jenkins(base_path: Path):
    for name in JenkinsParser.DEFAULT_FILENAMES:
        p = base_path / name
        if p.exists():
            return p
    return None


def _detect_azure(base_path: Path):
    for name in ('azure-pipelines.yml', 'azure-pipelines.yaml',
                 '.azure-pipelines.yml'):
        p = base_path / name
        if p.exists():
            return p
    az_dir = base_path / '.azure-pipelines'
    if az_dir.exists():
        for p in sorted(list(az_dir.glob('*.yml')) + list(az_dir.glob('*.yaml'))):
            return p
    return None


def _detect_bitbucket(base_path: Path):
    p = base_path / 'bitbucket-pipelines.yml'
    return p if p.exists() else None


def _detect_drone(base_path: Path):
    p = base_path / '.drone.yml'
    return p if p.exists() else None


def _detect_woodpecker(base_path: Path):
    p = base_path / '.woodpecker.yml'
    if p.exists():
        return p
    wp_dir = base_path / '.woodpecker'
    if wp_dir.exists():
        for q in sorted(list(wp_dir.glob('*.yml')) + list(wp_dir.glob('*.yaml'))):
            return q
    return None


def _detect_travis(base_path: Path):
    p = base_path / '.travis.yml'
    return p if p.exists() else None


def _detect_appveyor(base_path: Path):
    for name in ('appveyor.yml', '.appveyor.yml'):
        p = base_path / name
        if p.exists():
            return p
    return None


def _detect_buildkite(base_path: Path):
    bk_dir = base_path / '.buildkite'
    if bk_dir.exists():
        for q in sorted(bk_dir.glob('pipeline*.yml')):
            return q
        for q in sorted(bk_dir.glob('pipeline*.yaml')):
            return q
    return None


def _detect_codefresh(base_path: Path):
    for name in ('codefresh.yml', '.codefresh.yml',
                 'codefresh.yaml', '.codefresh.yaml'):
        p = base_path / name
        if p.exists():
            return p
    return None


def _detect_semaphore(base_path: Path):
    p = base_path / '.semaphore' / 'semaphore.yml'
    return p if p.exists() else None


# ---------------------------------------------------------------------------
# Adapter registrations
#
# Order is intentional: the existing four CI systems (GitHub, GitLab,
# CircleCI, Jenkins) are first to preserve historical behaviour for
# polyglot repos. The new eight follow with well-known filenames; none
# require content-sniffing, so first-match is unambiguous within each
# system. ``detect()`` walks the WHOLE registry and warns when more
# than one matches — see ``registry.detect`` for the rationale.
# ---------------------------------------------------------------------------
register_adapter(ParserAdapter(
    slug="github",
    name="GitHub Actions",
    parser_class=GitHubActionsParser,
    detect=_detect_github,
    parser_kwargs=lambda args: {},
))

register_adapter(ParserAdapter(
    slug="gitlab",
    name="GitLab CI",
    parser_class=GitLabCIParser,
    detect=_detect_gitlab,
    parser_kwargs=lambda args: {
        'follow_includes': not getattr(args, 'no_includes', False),
    },
))

register_adapter(ParserAdapter(
    slug="circleci",
    name="CircleCI",
    parser_class=CircleCIParser,
    detect=_detect_circleci,
    parser_kwargs=lambda args: {},
))

register_adapter(ParserAdapter(
    slug="jenkins",
    name="Jenkins",
    parser_class=JenkinsParser,
    detect=_detect_jenkins,
    parser_kwargs=lambda args: {},
))

register_adapter(ParserAdapter(
    slug="azure",
    name="Azure Pipelines",
    parser_class=AzurePipelinesParser,
    detect=_detect_azure,
    parser_kwargs=lambda args: {},
))

register_adapter(ParserAdapter(
    slug="bitbucket",
    name="Bitbucket Pipelines",
    parser_class=BitbucketPipelinesParser,
    detect=_detect_bitbucket,
    parser_kwargs=lambda args: {},
))

register_adapter(ParserAdapter(
    slug="drone",
    name="Drone CI",
    parser_class=DroneParser,
    detect=_detect_drone,
    parser_kwargs=lambda args: {},
))

register_adapter(ParserAdapter(
    slug="woodpecker",
    name="Woodpecker CI",
    parser_class=WoodpeckerParser,
    detect=_detect_woodpecker,
    parser_kwargs=lambda args: {},
))

register_adapter(ParserAdapter(
    slug="travis",
    name="Travis CI",
    parser_class=TravisCIParser,
    detect=_detect_travis,
    parser_kwargs=lambda args: {},
))

register_adapter(ParserAdapter(
    slug="appveyor",
    name="AppVeyor",
    parser_class=AppVeyorParser,
    detect=_detect_appveyor,
    parser_kwargs=lambda args: {},
))

register_adapter(ParserAdapter(
    slug="buildkite",
    name="Buildkite",
    parser_class=BuildkiteParser,
    detect=_detect_buildkite,
    parser_kwargs=lambda args: {},
))

register_adapter(ParserAdapter(
    slug="codefresh",
    name="Codefresh",
    parser_class=CodefreshParser,
    detect=_detect_codefresh,
    parser_kwargs=lambda args: {},
))

register_adapter(ParserAdapter(
    slug="semaphore",
    name="Semaphore",
    parser_class=SemaphoreParser,
    detect=_detect_semaphore,
    parser_kwargs=lambda args: {},
))
