# Architecture

This document describes the internal design of `eirmos`
using ASCII UML-style diagrams: a layered component view, a class
diagram, sequence diagrams for the parse→render flow, and detail
diagrams for the trickier per-system semantics.

If you only want a high-level picture, see the **Layered components**
section. If you want to extend the parser, jump to **Class diagram —
parser hierarchy** and the *"Adding a new CI system"* section in the
top-level [README](../README.md).

---

## 1. Layered components

```
   ┌──────────────────────────────────────────────────────────────┐
   │                         CLI layer                            │
   │  ┌──────────────────────────────────────────────────────┐    │
   │  │  cli.py                                               │   │
   │  │   • argparse                                          │   │
   │  │   • output routing (stdout / --output)                │   │
   │  │   • forced --ci selection                             │   │
   │  └──────────────────────────────────────────────────────┘    │
   └────────────────────────────┬─────────────────────────────────┘
                                │
   ┌────────────────────────────▼─────────────────────────────────┐
   │                      Detection layer                         │
   │  ┌────────────────────────────────────────────────────┐      │
   │  │  parsers/registry.py                               │      │
   │  │   • REGISTRY: List[ParserAdapter]                  │      │
   │  │   • detect(base_path) walks ALL adapters,          │      │
   │  │     warns on multi-match, returns first hit        │      │
   │  └────────────────────────────────────────────────────┘      │
   └────────────────────────────┬─────────────────────────────────┘
                                │  (adapter, main_file)
   ┌────────────────────────────▼─────────────────────────────────┐
   │                       Parsing layer                          │
   │  ┌────────────────────────────────────────────────────┐      │
│  │  parsers/base.py        (BasePipelineParser ABC)   │      │
│  │   • _load_yaml()  ◄── uses _yaml.safe_load() with  │      │
│  │     private _EirmosSafeLoader (not global SafeLoader)│     │
   │  │   • get_job_stage / get_job_needs / ... defaults   │      │
   │  └────────────────────────────────────────────────────┘      │
   │  ┌────────────────────────────────────────────────────┐      │
   │  │  13 concrete parsers (one per CI system)           │      │
   │  │  populate jobs / file_map / parsed_files / stages  │      │
   │  └────────────────────────────────────────────────────┘      │
   └────────────────────────────┬─────────────────────────────────┘
                                │  parser implementing the protocol
   ┌────────────────────────────▼─────────────────────────────────┐
   │                        Graph layer                           │
   │  ┌────────────────────────────────────────────────────┐      │
   │  │  graph.py    (DependencyGraph)                     │      │
   │  │   • edges, stage_jobs, has_cycle, get_roots, ...   │      │
   │  └────────────────────────────────────────────────────┘      │
   └────────────────────────────┬─────────────────────────────────┘
                                │
   ┌────────────────────────────▼─────────────────────────────────┐
   │                     Presentation layer                       │
   │  ┌────────────────────────────────────────────────────┐      │
   │  │  formatters/base.py       (BaseFormatter)          │      │
   │  │  Tree   Mermaid   Dot   Summary   Variables        │      │
   │  └────────────────────────────────────────────────────┘      │
   └──────────────────────────────────────────────────────────────┘
```

**Layer dependency rule:** higher layers depend on lower ones, never
the other way around. Formatters know nothing about which parser
produced the graph (with one tiny exception in `tree.py` for the
title; the rest is purely protocol-driven).

---

## 2. Class diagram — parser hierarchy

```
                ┌────────────────────────────────────┐
                │   <<abstract>>                     │
                │   BasePipelineParser               │
                ├────────────────────────────────────┤
                │  + base_path : Path                │
                │  + jobs : dict[str, dict]          │
                │  + templates : dict[str, dict]     │
                │  + stages : list[str]              │
                │  + parsed_files : set[str]         │
                │  + file_map : dict[str, str]       │
                ├────────────────────────────────────┤
                │  + parse(path) : Self      {abs}   │
                │  + _load_yaml(path) : dict|None    │
                │  + get_job_stage(name) : str       │
                │  + get_job_needs(name) : list      │
                │  + get_job_extends(name) : list    │
                │  + get_job_triggers(name) : dict?  │
                │  + get_job_rules_summary(n) : str  │
                │  + get_job_variables(name) : dict  │
                │  + get_global_variables() : dict   │
                └─────────────────┬──────────────────┘
                                  ▲
                                  │ extends
       ┌──────────────────────────┼─────────────────────────────────┐
       │                          │                                 │
   ┌───┴────────────┐    ┌────────┴────────┐    ┌──────────────────┴─┐
   │  GitLabCI      │    │  GitHubActions  │    │  CircleCI          │
   │   Parser       │    │   Parser        │    │   Parser           │
   ├────────────────┤    ├─────────────────┤    ├────────────────────┤
   │ +follow_       │    │ workflow_name   │    │ workflow_name      │
   │  includes      │    │ overridden in   │    │ defaults to        │
   │ +includes      │    │ parse() from    │    │ "CircleCI"         │
   │ +global_vars   │    │ YAML name:      │    │                    │
   └────────────────┘    └─────────────────┘    └────────────────────┘

   ┌────────────────┐    ┌─────────────────┐    ┌────────────────────┐
   │  Jenkins       │    │  AzurePipelines │    │  Bitbucket         │
   │   Parser       │    │   Parser        │    │   Pipelines Parser │
   ├────────────────┤    ├─────────────────┤    ├────────────────────┤
   │ DEFAULT_       │    │ +_stage_jobs:   │    │ groups: default,   │
   │ FILENAMES      │    │   dict[str,     │    │ branches, custom,  │
   │ regex-based    │    │   list[str]]    │    │ pull-requests, tags│
   │ token walk     │    │ stage→last-jobs │    │ parallel: siblings │
   └────────────────┘    └─────────────────┘    └────────────────────┘

   ┌────────────────┐    ┌─────────────────┐    ┌────────────────────┐
   │  Drone         │    │  Travis         │    │  AppVeyor          │
   │   Parser       │    │   Parser        │    │   Parser           │
   ├────────────────┤    ├─────────────────┤    ├────────────────────┤
   │ multi-doc YAML │    │ +matrix_limit   │    │ +matrix_limit      │
   │ list / map     │    │   (default 200) │    │   (default 200)    │
   │ step forms     │    │ stages-seq /    │    │ phases × matrix    │
   │                │    │ jobs-parallel   │    │ truncation warn    │
   └────────────────┘    └─────────────────┘    └────────────────────┘

   ┌────────────────┐    ┌─────────────────┐    ┌────────────────────┐
   │  Buildkite     │    │  Codefresh      │    │  Semaphore         │
   │   Parser       │    │   Parser        │    │   Parser           │
   ├────────────────┤    ├─────────────────┤    ├────────────────────┤
   │ wait barrier   │    │ when.steps[]    │    │ blocks[]           │
   │ cross-product  │    │ type: parallel  │    │ dependencies[]     │
   │ group flatten  │    │ flattens peers  │    │                    │
   └────────────────┘    └─────────────────┘    └────────────────────┘

                       ┌────────────────────┐
                       │  Woodpecker        │
                       │   Parser           │
                       │  extends Drone     │
                       │  (display only)    │
                       └────────────────────┘
```

### Adapter and registry

```
   ┌────────────────────────────────┐         ┌────────────────────────┐
   │  ParserAdapter                 │         │  REGISTRY              │
   ├────────────────────────────────┤   1..* │  List[ParserAdapter]   │
   │ + name : str                   │ ────────│                        │
   │ + parser_class : Type          │         │  walked by detect()    │
   │ + detect : (Path) → Path?      │         │  in registration order │
   │ + parser_kwargs : (args)→ dict │         └────────────────────────┘
   └────────────────────────────────┘
                  ▲
                  │ uses
   ┌──────────────┴─────────────────┐
   │  detect(base_path)             │
   │   1. iterate REGISTRY          │
   │   2. collect ALL matches       │
   │   3. if >1, warn to stderr     │
   │   4. return first match        │
   └────────────────────────────────┘
```

---

## 3. Class diagram — graph & formatters

```
                 ┌────────────────────────────────────┐
                 │   DependencyGraph                  │
                 ├────────────────────────────────────┤
                 │  + parser : BasePipelineParser     │
                 │  + edges : list[(from, to, type)]  │
                 │  + stage_jobs : dict[str, list]    │
                 ├────────────────────────────────────┤
                 │  + get_predecessors(name)          │
                 │  + get_successors(name)            │
                 │  + get_roots() : list[str]         │
                 │  + get_ordered_stages() : list     │
                 │  + has_cycle() : bool              │
                 └────────────────────────────────────┘
                                  ▲
                                  │ consumed by
                                  │
                 ┌────────────────┴───────────────────┐
                 │  <<abstract>> BaseFormatter        │
                 ├────────────────────────────────────┤
                 │  + parser : BasePipelineParser     │
                 │  + graph : DependencyGraph         │
                 ├────────────────────────────────────┤
                 │  + render(filter_stage=,           │
                 │           filter_job=) {abstract}  │
                 │  + sanitize_id(name) : str         │
                 └─────────────────┬──────────────────┘
                                   │
        ┌──────────────────────────┼─────────────────────────────┐
        │                          │                             │
  ┌─────┴────────┐  ┌──────────────┴───┐  ┌─────────────────┐  ┌─┴──────────────┐
  │ TreeFormatter│  │ MermaidFormatter │  │  DotFormatter   │  │SummaryFormatter│
  └──────────────┘  └──────────────────┘  └─────────────────┘  └────────────────┘
                                                  ┌────────────────┐
                                                  │ VariableFormatter│
                                                  └────────────────┘
```

---

## 4. Sequence diagram — CLI invocation

```
   user            cli.py        registry        adapter        parser            graph        formatter
    │                │              │              │              │                 │             │
    │ cicd-vis path  │              │              │              │                 │             │
    │───────────────►│              │              │              │                 │             │
    │                │ detect(path) │              │              │                 │             │
    │                │─────────────►│              │              │                 │             │
    │                │              │ for adapter  │              │                 │             │
    │                │              │  in REGISTRY:│              │                 │             │
    │                │              │ adapter.detect(path)        │                 │             │
    │                │              │─────────────►│              │                 │             │
    │                │              │ ◄────────────│ Path | None  │                 │             │
    │                │              │ (collect ALL matches)       │                 │             │
    │                │              │ if >1: warn                 │                 │             │
    │                │ ◄────────────│ (adapter, main_file)        │                 │             │
    │                │                                                                            │
    │                │ adapter.parser_class(base_path, **kwargs)                                  │
    │                │────────────────────────────────────────────►│                              │
    │                │ parser.parse(main_file)                     │                              │
    │                │────────────────────────────────────────────►│                              │
    │                │                                              │ _load_yaml(file)            │
    │                │                                              │ build self.jobs / stages    │
    │                │                                              │ build self._needs / file_map│
    │                │ DependencyGraph(parser)                     │                              │
    │                │──────────────────────────────────────────────────────────►│                │
    │                │                                                            │ for each job: │
    │                │                                                            │  parser       │
    │                │                                                            │   .get_job_*  │
    │                │                                                            │ build edges   │
    │                │ FORMATTERS[fmt](parser, graph).render(filters)                              │
    │                │──────────────────────────────────────────────────────────────────────────►│
    │                │                                                                          .render():
    │                │                                                                          query graph
    │                │                                                                          format text
    │                │ ◄────────────────────────────────────────────────────────────────────────│ str
    │ stdout / file  │                                                                            │
    │ ◄──────────────│                                                                            │
```

---

## 5. Detection state machine

```
                ┌─────────────────────┐
                │   detect(base_path) │
                └──────────┬──────────┘
                           │
                           ▼
                ┌─────────────────────┐
                │  matches = []       │
                └──────────┬──────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │ for adapter in REGISTRY│
              │     main_file =        │
              │      adapter.detect()  │
              └──────────┬─────────────┘
                         │
              ┌──────────▼───────────┐
              │  main_file is not    │
              │  None ?              │
              └─┬─────────────────┬──┘
              N │                 │ Y
                │                 ▼
                │     ┌──────────────────────┐
                │     │ matches.append(...)  │
                │     └──────────┬───────────┘
                │                │
                ▼                ▼
              (next adapter, loop continues)
                       │
                       ▼ (loop done)
              ┌────────────────────┐
              │  len(matches)?     │
              └─┬──────┬───────┬───┘
                │      │       │
                0      1       ≥2
                │      │       │
                ▼      ▼       ▼
            ┌─────┐  ┌────┐  ┌──────────────────┐
            │None │  │ ok │  │ stderr WARNING:  │
            │None │  │    │  │ "Detected X, Y;  │
            └─────┘  └────┘  │  using X."       │
                             └────────┬─────────┘
                                      │
                                      ▼
                             ┌──────────────┐
                             │ return       │
                             │ matches[0]   │
                             └──────────────┘
```

---

## 6. Buildkite `wait` barrier — graph construction

```
   YAML in (linear list):
     [ lint, build, wait, unit, integration, wait, deploy_staging,
       deploy_prod (depends_on=deploy_staging) ]

   Two-pass build:

   Pass 1 (register steps, remember waits in linear order)
   ─────────────────────────────────────────────────────────
       index = [
         step(lint), step(build), wait, step(unit), step(integration),
         wait, step(deploy_staging), step(deploy_prod)
       ]

   Pass 2 (compute deps using waits as cross-product barriers)
   ─────────────────────────────────────────────────────────────
     pre_wait  = []           # everything before the most recent wait
     post_wait = []           # everything after the most recent wait

     lint            : explicit?  no  → deps = pre_wait = []
                       post_wait = [lint]
     build           : explicit yes (depends_on: lint)
                       deps = [lint] ; post_wait = [lint, build]
     wait            : pre_wait = pre_wait + post_wait = [lint, build]
                       post_wait = []
     unit            : no explicit → deps = pre_wait = [lint, build]
                       post_wait = [unit]
     integration     : no explicit → deps = [lint, build]
                       post_wait = [unit, integration]
     wait            : pre_wait = [lint, build, unit, integration]
                       post_wait = []
     deploy_staging  : no explicit → deps = pre_wait
                       post_wait = [deploy_staging]
     deploy_prod     : EXPLICIT depends_on: deploy_staging
                       deps = [deploy_staging]   (no cross-product!)

   Resulting graph
   ───────────────
                 ┌─── unit ────┐
       lint ──┬─►│             │──► (next group)
              │  └── integ ────┘
       build ─┘  ┌── deploy_staging ──► deploy_prod
                 └─ via cross-product
```

---

## 7. Codefresh `type: parallel` — graph construction

```
   YAML in:
     steps:
       clone:    type: git-clone
       build:    type: build
                 when: { steps: [{name: clone, on: [success]}] }
       run_tests:                       ◄── parallel WRAPPER, not a job
         type: parallel
         steps:
           unit: type: freestyle
           lint: type: freestyle
       publish:  type: push
                 when: { steps: [{name: unit, on: [success]}] }

   Walk algorithm (depth-first over the steps mapping):

     parent_predecessor = None
     prev_seq = [None]   # last sibling in this scope (sequential fallback)

     clone:        explicit?  no  → deps = []  ; prev_seq = clone
     build:        explicit yes (clone) → deps = [clone] ; prev_seq = build
     run_tests:    type==parallel → DON'T register the wrapper
                   parent_pred = prev_seq = build
                   recurse into children with default_deps = [build]
       unit:       explicit?  no  → deps = [build]
       lint:       explicit?  no  → deps = [build]
                   prev_seq becomes "last child registered" = lint
     publish:      explicit yes (unit) → deps = [unit]

   Resulting graph
   ───────────────
       clone ──► build ──┬──► unit ──► publish
                         └──► lint
```

The parallel wrapper itself is **not** registered as a job —
children appear directly as peers in the graph.

---

## 8. Travis stages — graph construction

```
   YAML in:
     jobs:
       include:
         - { stage: build,  name: compile }
         - { stage: test,   name: unit }
         - { stage: test,   name: integration }
         - { stage: deploy, name: release }

   Group jobs by stage, preserving stage order
   ───────────────────────────────────────────
     order = [build, test, deploy]
     groups = {
       build:  [compile],
       test:   [unit, integration],
       deploy: [release],
     }

   Walk stages in order
   ────────────────────
     prev_stage_jobs = []

     stage build:
       compile  : deps = prev_stage_jobs = []
       prev_stage_jobs = [compile]

     stage test:
       unit         : deps = prev_stage_jobs = [compile]
       integration  : deps = prev_stage_jobs = [compile]
                      (peers — no edge between them)
       prev_stage_jobs = [unit, integration]

     stage deploy:
       release  : deps = prev_stage_jobs = [unit, integration]

   Resulting graph
   ───────────────
                  ┌── unit ──┐
       compile ──►│          │──► release
                  └─ integ ──┘
```

---

## 9. AppVeyor matrix × phases

```
   YAML in:
     environment.matrix: [{PYTHON: 3.10}, {PYTHON: 3.11}]
     image:              [VS2019, Ubuntu]
     install:            [...]
     build_script:       [...]
     test_script:        [...]
     deploy_script:      [...]

   Compute combinations
   ────────────────────
     axes = [matrix(2), images(2)]
     combos = cartesian product = 4
       [ (PYTHON=3.10, VS2019),
         (PYTHON=3.10, Ubuntu),
         (PYTHON=3.11, VS2019),
         (PYTHON=3.11, Ubuntu) ]
     if len(combos) > matrix_limit:
         truncate ; emit yellow warning to stderr

   Lay down jobs per phase
   ───────────────────────
     active_phases = [install, build, test, deploy]   ← from script keys
     prev_phase_jobs = []
     for phase in active_phases:
       current = []
       for combo in combos:
         job = "{phase}[{label}]"
         deps = prev_phase_jobs           ← cross-product chain
         register(job, phase, deps)
         current.append(job)
       prev_phase_jobs = current

   Resulting graph (for 2 combos, 4 phases)
   ────────────────────────────────────────
                 install_A ──┐  ┌── build_A ──┐  ┌── test_A ──┐  ┌── deploy_A
                             │  │             │  │            │  │
       (start) ──►           │  │             │  │            │  │
                             │  │             │  │            │  │
                 install_B ──┘  └── build_B ──┘  └── test_B ──┘  └── deploy_B
       Each job in phase N depends on EVERY job in phase N-1.
```

---

## 10. Azure stage `dependsOn` mapping

```
   YAML in:
     stages:
       - stage: build
         jobs: [compile, package(dependsOn=compile)]
       - stage: test                  ◄── no dependsOn → implicit prev (build)
         jobs: [unit, integration(dependsOn=unit)]
       - stage: deploy
         dependsOn: build             ◄── explicit cross-stage
         jobs: [prod]

   Trick: a stage's dependsOn is a list of STAGE names, but the graph
   needs JOB-level edges. We track the last jobs of each stage in
   _stage_jobs and resolve stage-deps to those jobs.

   Build sequentially, remembering tails
   ─────────────────────────────────────
     stage build:
       compile  : deps = []  (first in stage, no stage-deps)
       package  : deps = [compile]  (explicit dependsOn)
       _stage_jobs[build] = [compile, package]

     stage test:
       implicit prev → stage_dep_stages = [build]
       resolve to last jobs    → stage_dep_jobs = [compile, package]
       unit         : first in stage, no explicit → deps = [compile, package]
       integration  : explicit dependsOn=unit → deps = [unit]
       _stage_jobs[test] = [unit, integration]

     stage deploy:
       explicit dependsOn=[build]
       resolve to last jobs   → stage_dep_jobs = [compile, package]
       prod : first in stage, no explicit → deps = [compile, package]

   Resulting graph
   ───────────────
       compile ──► package ──┬──► unit ──► integration
                             │
                             └──► prod         (cross-stage edge)
```

---

## 11. Where to find what

| Concern                      | File                                                              |
|------------------------------|-------------------------------------------------------------------|
| Add a new CI system          | `eirmos/parsers/<system>.py` + `parsers/__init__.py` registration |
| Shared YAML loading          | `eirmos/_yaml.py` (loader), `eirmos/parsers/base.py` (`_load_yaml`) |
| Detection / multi-match warn | `eirmos/parsers/registry.py`                                      |
| Graph algorithms             | `eirmos/graph.py`                                                 |
| New output format            | `eirmos/formatters/<format>.py` + `cli.FORMATTERS` map            |
| CLI flags                    | `eirmos/cli.py:build_arg_parser`                                  |
| Cross-system smoke tests     | `tests/test_graph_integration.py`                                 |
| Polyglot detection tests     | `tests/test_registry_extended.py`                                 |

---

## 12. Invariants enforced by tests

These are properties that hold for every parser thanks to the
cross-cutting integration tests in `tests/test_graph_integration.py`:

1. The fixture for every parser produces **at least one** job.
2. `DependencyGraph(parser).has_cycle()` is **False** on every fixture.
3. Every formatter produces **non-empty** output for every parser.
4. Tree, Mermaid, and Dot formatters mention **every job name** in
   their output (catches `KeyError` / missing-stage / attribute drift
   bugs).

These invariants run automatically against any new parser added to
the `PARSER_FIXTURES` list — no per-parser smoke tests required.
