# eirmos

> **Explore the mental graph of your CI/CD pipelines.**

*eirmos* (from Greek **ειρμός**, *coherent train of thought*) parses
and visualises CI/CD pipeline dependencies across **13 systems** —
GitHub Actions, GitLab CI, Jenkins, CircleCI, Azure Pipelines, Bitbucket
Pipelines, Drone CI, Woodpecker CI, Travis CI, AppVeyor, Buildkite,
Codefresh, and Semaphore.

Point it at a repo and get a job-dependency graph rendered as a
terminal tree, Mermaid diagram, Graphviz dot, or text summary.
Everything runs on your machine — no telemetry, no remote upload, no
cloud account.

```
┌─────────────────────────────────────────────────────────────────┐
│  repo path  ─►  detect()  ─►  parse  ─►  DependencyGraph        │
│                                                ▲                │
│                                                │                │
│                                       Tree / Mermaid / Dot      │
│                                       Summary / Variables       │
└─────────────────────────────────────────────────────────────────┘
```

## Supported systems

| System | Detection | Dependency model |
|---|---|---|
| GitHub Actions | `.github/workflows/*.yml` | `jobs[].needs` |
| GitLab CI | `.gitlab-ci.yml` (+ includes) | `needs:`, `extends:`, `rules:`, `trigger:` |
| Jenkins | `Jenkinsfile` (declarative DSL) | sequential `stage(...)`, `parallel { ... }` |
| CircleCI | `.circleci/config.yml` | workflow `jobs: requires:` |
| Azure Pipelines | `azure-pipelines.yml`, `.azure-pipelines/*.yml` | `stages[].dependsOn`, `jobs[].dependsOn`, implicit prev-stage |
| Bitbucket Pipelines | `bitbucket-pipelines.yml` | sequential steps; `parallel:` siblings |
| Drone CI | `.drone.yml` | `depends_on` (string/list); sequential fallback |
| Woodpecker CI | `.woodpecker.yml`, `.woodpecker/*.yml` | same model as Drone |
| Travis CI | `.travis.yml` | `jobs.include[].stage`; stages sequential, jobs-within parallel |
| AppVeyor | `appveyor.yml`, `.appveyor.yml` | phases × matrix (capped) |
| Buildkite | `.buildkite/pipeline*.yml` | `key`/`depends_on`; `wait` barriers; `group:` flatten |
| Codefresh | `codefresh.yml`, `.codefresh.yml` | `when.steps[]`; `type: parallel` flattening |
| Semaphore | `.semaphore/semaphore.yml` | `blocks[].dependencies` |

> Polyglot repos (e.g. mid-migration from Travis to GitHub Actions) are
> auto-detected: `eirmos` will print a warning naming all
> matched systems and use the first per registry order. Override with
> `--ci github`.

## Install

Pick the path that matches your environment:

```bash
# Recommended: uv tool (isolated, fast, no virtualenv juggling)
uv tool install eirmos

# One-shot, no install (uv ≥0.5)
uvx eirmos .

# Classic pipx (also isolated)
pipx install eirmos

# Single-file zipapp — runs anywhere with Python ≥3.9, no install
curl -L -o eirmos.pyz https://github.com/<you>/<repo>/releases/latest/download/eirmos.pyz
chmod +x eirmos.pyz
./eirmos.pyz .

# Plain pip (last resort, pollutes site-packages)
pip install eirmos

# From source for development
git clone https://github.com/<you>/<repo>
cd <repo>
pip install -e ".[dev]"
make test          # 172 tests
make coverage      # ≥90% gate
make pyz           # build the single-file zipapp
```

## CLI

```bash
# Auto-detect and render as a terminal tree
eirmos .

# Explicit path
eirmos /path/to/repo

# Force a CI system instead of auto-detection
# Slugs: github, gitlab, circleci, jenkins, azure, bitbucket, drone,
#        woodpecker, travis, appveyor, buildkite, codefresh, semaphore
eirmos --ci buildkite .

# Mermaid output (paste into GitHub / docs)
eirmos --format mermaid . > pipeline.mmd

# Graphviz dot for high-res rendering
eirmos --format dot . | dot -Tsvg -o pipeline.svg

# Filter to a single stage / job
eirmos --stage test .
eirmos --job deploy_prod .

# Inventory views
eirmos --list-stages .
eirmos --list-jobs   .

# Skip GitLab includes
eirmos --no-includes .
```

## Library usage

Every parser implements the same protocol; you can use them directly:

```python
from pathlib import Path
from eirmos import (
    BuildkiteParser, DependencyGraph, MermaidFormatter,
)

parser = BuildkiteParser(base_path="my-repo").parse(
    Path("my-repo/.buildkite/pipeline.yml")
)
graph = DependencyGraph(parser)
print(MermaidFormatter(parser, graph).render())
```

Auto-detect at runtime:

```python
from pathlib import Path
from eirmos.parsers import detect
from eirmos import DependencyGraph, TreeFormatter

adapter, main_file = detect(Path("my-repo"))
parser = adapter.parser_class(base_path="my-repo").parse(main_file)
graph = DependencyGraph(parser)
print(TreeFormatter(parser, graph).render())
```

## Output formats

| `--format` | Use case |
|---|---|
| `tree` | Default. Coloured terminal tree grouped by stage. |
| `mermaid` | GitHub / GitLab / docs (renders inline). |
| `dot` | Graphviz; pipe into `dot -Tsvg` for high-res. |
| `summary` | Statistics only (job counts, edge counts, roots). |
| `variables` | Lists global + per-job variables (where supported). |

## Non-obvious per-system semantics

These are the bits that aren't immediately obvious from the YAML —
worth knowing when you read a generated graph.

### Buildkite — `wait` is a cross-product barrier

```
                wait
   step_a ──┐  ┌──► step_d
   step_b ──┤  ├──► step_e
   step_c ──┘  └──► step_f
```

Every step *after* a `wait` implicitly depends on every step *before*
the same `wait`. If a post-wait step already declares `depends_on`,
the explicit list wins (no double-add).

### Codefresh — `type: parallel` flattens to peers

```
   prev_step ──► [parallel block] ──► next_step
                  ├── child_1
                  ├── child_2     (peers, no edges between them)
                  └── child_3
```

Children of a `type: parallel` block are exposed as peer jobs. Each
inherits the parallel block's predecessor (computed from `when.steps`
of the parent block, or sequential fallback).

### Travis — stages sequential, jobs-in-stage parallel

```
   stage:  build           ── compile  ◄──┐
                                            ├── (predecessor of every "test" job)
   stage:  test            ── unit     ◄──┤
                            ── integ    ◄──┘    (peers, no edge)
   stage:  deploy          ── release  ◄── unit AND integ
```

### AppVeyor — phases × matrix, capped

Phases run sequentially: `init → install → before_build → build →
after_build → before_test → test → after_test → deploy → after_deploy`.
For each combination in `environment.matrix` × `image`, every active
phase produces one job. Combinations are capped at `matrix_limit`
(default `200`) — passes that cap and the parser emits a warning.

### Azure — implicit prev-stage default

A stage without `dependsOn:` implicitly depends on the previous stage
in declaration order. Stage-level `dependsOn` is mapped to the *last
jobs* of the predecessor stage so cross-stage edges always connect to
real nodes.

### Polyglot detection

`detect()` walks the entire registry. If two or more adapters match
the same repo, a yellow warning is printed naming all matches and the
first one (per registry order) is used. Override with `--ci`.

## Architecture

The codebase is organised in clear layers:

```
                   ┌───────────────────────────────────┐
                   │   cli.py  (argparse + glue)       │
                   └───────┬───────────────────────────┘
                           │
            ┌──────────────▼──────────────┐
            │   parsers/registry.detect() │
            │   first-match + multi warn  │
            └──────────────┬──────────────┘
                           │  ParserAdapter
        ┌──────────────────▼─────────────────────┐
        │  parsers/  (BasePipelineParser)        │
        │  GitHub  GitLab  CircleCI  Jenkins     │
        │  Azure   Bitbucket  Drone  Woodpecker  │
        │  Travis  AppVeyor  Buildkite           │
        │  Codefresh  Semaphore                  │
        └──────────────────┬─────────────────────┘
                           │  jobs / file_map / get_job_*
                           ▼
                ┌──────────────────────┐
                │   graph.py           │
                │   DependencyGraph    │
                └──────────┬───────────┘
                           │  edges / roots / has_cycle
                           ▼
        ┌──────────────────────────────────────┐
        │  formatters/  (BaseFormatter)        │
        │  Tree  Mermaid  Dot  Summary  Vars   │
        └──────────────────────────────────────┘
```

A deeper write-up with class and sequence diagrams lives in
[`docs/architecture.md`](docs/architecture.md).

## Adding a new CI system

1. Implement `BasePipelineParser` in `eirmos/parsers/<system>.py`.
   Populate `self.jobs`, `self.file_map`, `self.parsed_files`, and
   override `get_job_stage` / `get_job_needs`.
2. Reuse the shared YAML loader: `content = self._load_yaml(path)`.
3. Register a `ParserAdapter` in `parsers/__init__.py` with a `detect()`
   helper that returns the main pipeline file (or `None`).
4. Add a fixture in `tests/examples/` and a `tests/test_<system>_parser.py`
   covering happy path, malformed YAML, missing file, cycle, empty, and
   single-job cases.
5. Add the parser to `eirmos/__init__.py` exports.

The cross-cutting test in `tests/test_graph_integration.py` will
automatically smoke-test the new parser through every formatter once
it's added to the `PARSER_FIXTURES` list.

## Development

```bash
# Run the full suite (172 tests)
python -m unittest discover -s tests

# Coverage gate (≥90%)
python -m coverage run --source=eirmos -m unittest discover -s tests
python -m coverage report -m --fail-under=90
```


