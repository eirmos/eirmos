# Changelog

All notable changes to **eirmos** are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [SemVer](https://semver.org/).


## [0.6.0] — 2026-05-13

Public release of the codebase 

## [0.5.2] — 2026-05-10

Update versions and documentation

## [0.5.1] — 2026-05-10

Update the `ci` flag to lowercase values of the CI/CD providers.

## [0.4.0] — 2026-05-10

First public release on PyPI. `eirmos` parses CI/CD pipeline
definitions across 13 systems and renders the job-dependency graph
as a terminal tree, Mermaid diagram, Graphviz dot, or text summary —
fully local, no telemetry, no cloud account.

### Added — supported CI systems

13 parsers, each with system-specific dependency semantics:

- **GitHub Actions** — `.github/workflows/*.yml`, `jobs[].needs`
- **GitLab CI** — `.gitlab-ci.yml` with `include:`, `extends:`, `needs:`, `rules:`, `trigger:`
- **Jenkins** — declarative `Jenkinsfile`: sequential `stage(...)`, `parallel { ... }`
- **CircleCI** — `.circleci/config.yml`, workflow `jobs[].requires`
- **Azure Pipelines** — `stages[].dependsOn`, `jobs[].dependsOn`, implicit prev-stage
- **Bitbucket Pipelines** — sequential steps, `parallel:` siblings
- **Drone CI** — `depends_on` (string/list), sequential fallback
- **Woodpecker CI** — same model as Drone
- **Travis CI** — `jobs.include[].stage`; stages sequential, jobs-within parallel
- **AppVeyor** — phases × matrix (capped at `matrix_limit`, default 200)
- **Buildkite** — `key`/`depends_on`, `wait` cross-product barriers, `group:` flattening
- **Codefresh** — `when.steps[]`, `type: parallel` flattening
- **Semaphore** — `blocks[].dependencies`

Polyglot repos auto-detect all matching systems and pick the first per
registry order; override with `--ci <slug>` (e.g. `--ci github`,
`--ci gitlab`, `--ci buildkite`).

### Added — output formats

| `--format` | Use |
|---|---|
| `tree` *(default)* | Coloured terminal tree grouped by stage |
| `mermaid` | Inline-renderable diagrams for GitHub / GitLab / docs |
| `dot` | Graphviz source for high-res SVG/PNG |
| `summary` | Job counts, edge counts, roots |
| `variables` | Global + per-job variables (where supported) |

### Added — CLI

- Auto-detect with `eirmos <path>`
- `--ci <slug>` to force a parser (slugs: `github`, `gitlab`, `circleci`,
  `jenkins`, `azure`, `bitbucket`, `drone`, `woodpecker`, `travis`,
  `appveyor`, `buildkite`, `codefresh`, `semaphore`)
- `--stage <name>` / `--job <name>` filters
- `--list-stages` / `--list-jobs` inventory
- `--no-includes` to skip GitLab `include:` resolution
- `--no-color` for non-TTY output

### Added — distribution

- Published to PyPI as `eirmos` (installable via `uv tool install`,
  `uvx`, `pipx`, or `pip`)
- Single-file zipapp `eirmos.pyz` attached to each GitHub Release
- Console script entry point: `eirmos = eirmos.cli:main`

### Added — CI / release automation

- `ci.yml` — unittest matrix on Python 3.9–3.12, 90% coverage gate,
  build smoke test that installs the freshly built wheel and runs the CLI
- `release.yml` — on GitHub Release published, verifies the tag matches
  `pyproject.toml`, builds sdist + wheel with `uv build`, publishes to
  PyPI via Trusted Publishing (OIDC, no API token), and attaches the
  artifacts to the GitHub Release page

### Notes

- Requires Python ≥ 3.9
- Single runtime dependency: `PyYAML ≥ 6.0`
- 172 unit tests, ≥90% line coverage gate enforced in CI

