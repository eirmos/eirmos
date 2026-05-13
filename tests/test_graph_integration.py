"""Cross-parser integration smoke tests.

For every (parser, formatter) pair we confirm:

1. The parser produces ≥1 job from its example fixture.
2. ``DependencyGraph(parser).has_cycle()`` is False.
3. Every formatter renders a non-empty string.
4. Every job name appears in the rendered output (catches KeyError /
   missing-stage / attribute-drift bugs in formatters).

This is intentionally a SMOKE test, not a golden-file test. We don't
care about exact whitespace; we care that the contract holds across
all 12 systems.
"""

import unittest
from pathlib import Path

from eirmos.graph import DependencyGraph
from eirmos.formatters.tree import TreeFormatter
from eirmos.formatters.mermaid import MermaidFormatter
from eirmos.formatters.dot import DotFormatter
from eirmos.formatters.summary import SummaryFormatter
from eirmos.formatters.variables import VariableFormatter

from eirmos.parsers.gitlab import GitLabCIParser
from eirmos.parsers.github import GitHubActionsParser
from eirmos.parsers.jenkins import JenkinsParser
from eirmos.parsers.circleci import CircleCIParser
from eirmos.parsers.azure import AzurePipelinesParser
from eirmos.parsers.bitbucket import BitbucketPipelinesParser
from eirmos.parsers.drone import DroneParser, WoodpeckerParser
from eirmos.parsers.travis import TravisCIParser
from eirmos.parsers.appveyor import AppVeyorParser
from eirmos.parsers.buildkite import BuildkiteParser
from eirmos.parsers.codefresh import CodefreshParser
from eirmos.parsers.semaphore import SemaphoreParser


EXAMPLES = Path(__file__).parent / 'examples'


# (parser_class, fixture_path) — one per CI system in the registry.
PARSER_FIXTURES = [
    (GitLabCIParser, EXAMPLES / 'simple.gitlab-ci.yml'),
    (GitHubActionsParser, EXAMPLES / 'github-workflow.yml'),
    (JenkinsParser, EXAMPLES / 'Jenkinsfile'),
    (CircleCIParser, EXAMPLES / 'circleci-config.yml'),
    (AzurePipelinesParser, EXAMPLES / 'azure-pipelines.yml'),
    (BitbucketPipelinesParser, EXAMPLES / 'bitbucket-pipelines.yml'),
    (DroneParser, EXAMPLES / '.drone.yml'),
    (WoodpeckerParser, EXAMPLES / '.woodpecker.yml'),
    (TravisCIParser, EXAMPLES / '.travis.yml'),
    (AppVeyorParser, EXAMPLES / 'appveyor.yml'),
    (BuildkiteParser, EXAMPLES / '.buildkite' / 'pipeline.yml'),
    (CodefreshParser, EXAMPLES / 'codefresh.yml'),
    (SemaphoreParser, EXAMPLES / '.semaphore' / 'semaphore.yml'),
]


FORMATTERS = [
    TreeFormatter,
    MermaidFormatter,
    DotFormatter,
    SummaryFormatter,
    VariableFormatter,
]


class TestGraphAndFormatterIntegration(unittest.TestCase):
    """Parametrised smoke tests across (parser × formatter)."""

    def test_each_parser_produces_jobs(self):
        for parser_cls, fixture in PARSER_FIXTURES:
            with self.subTest(parser=parser_cls.__name__):
                p = parser_cls(base_path=EXAMPLES).parse(fixture)
                self.assertGreater(
                    len(p.jobs), 0,
                    f"{parser_cls.__name__} produced no jobs from {fixture.name}",
                )

    def test_no_cycles(self):
        for parser_cls, fixture in PARSER_FIXTURES:
            with self.subTest(parser=parser_cls.__name__):
                p = parser_cls(base_path=EXAMPLES).parse(fixture)
                g = DependencyGraph(p)
                self.assertFalse(
                    g.has_cycle(),
                    f"{parser_cls.__name__} has a cycle in {fixture.name}",
                )

    def test_formatters_render_non_empty(self):
        for parser_cls, fixture in PARSER_FIXTURES:
            p = parser_cls(base_path=EXAMPLES).parse(fixture)
            g = DependencyGraph(p)
            for formatter_cls in FORMATTERS:
                with self.subTest(parser=parser_cls.__name__,
                                  formatter=formatter_cls.__name__):
                    out = formatter_cls(p, g).render()
                    self.assertIsInstance(out, str)
                    self.assertGreater(
                        len(out.strip()), 0,
                        f"{formatter_cls.__name__} produced empty output "
                        f"for {parser_cls.__name__}",
                    )

    def test_formatters_mention_every_job(self):
        # Formatters that produce a per-job rendering should reference
        # every job name. SummaryFormatter and VariableFormatter
        # summarise globally and may not list every job individually,
        # so we check Tree / Mermaid / Dot only.
        renderers = [TreeFormatter, MermaidFormatter, DotFormatter]
        for parser_cls, fixture in PARSER_FIXTURES:
            p = parser_cls(base_path=EXAMPLES).parse(fixture)
            g = DependencyGraph(p)
            for formatter_cls in renderers:
                out = formatter_cls(p, g).render()
                for job in p.jobs:
                    with self.subTest(parser=parser_cls.__name__,
                                      formatter=formatter_cls.__name__,
                                      job=job):
                        # Mermaid/Dot may sanitize special characters.
                        # We accept either the original name or its
                        # alphanumeric form.
                        sanitized = ''.join(
                            ch if ch.isalnum() or ch == '_' else '_' for ch in job
                        )
                        self.assertTrue(
                            job in out or sanitized in out,
                            f"{formatter_cls.__name__} did not mention "
                            f"{job!r} for {parser_cls.__name__}",
                        )


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
