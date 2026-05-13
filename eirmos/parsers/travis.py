"""Travis CI parser.

Travis pipelines come in two main shapes:

* ``script: ...`` — single-job, single-stage. Becomes one job named
  after the language (or ``"build"``).
* ``jobs.include: [...]`` — list of jobs, each may name a ``stage:``.

Stages run **sequentially in declaration order**; jobs in the same
stage run **in parallel** and share predecessors with the last job
of the previous stage::

    stage: build         ── job_1 ◄──┐
                                      ├── (predecessor of every "test" job)
    stage: test          ── job_2 ◄──┤
                          ── job_3 ◄──┘   (job_2 and job_3 are peers, no edge)
    stage: deploy        ── job_4 ◄── job_2 OR job_3 (last in stage)

A ``matrix:`` (or ``env:`` matrix) expands to one job per
combination, capped at ``matrix_limit`` (default 200) to keep graphs
tractable.
"""

import itertools
from pathlib import Path

from .base import BasePipelineParser


class TravisCIParser(BasePipelineParser):
    """Parses ``.travis.yml``."""

    def __init__(self, base_path='.', matrix_limit=200):
        super().__init__(base_path=base_path)
        self.workflow_name = "Travis CI"
        self.matrix_limit = matrix_limit
        self._needs = {}
        self._truncated = False

    # ------------------------------------------------------------------
    def parse(self, file_path):
        file_path = Path(file_path).resolve()
        content = self._load_yaml(file_path)
        if content is None:
            return self

        source = str(file_path)
        includes = []
        if isinstance(content.get('jobs'), dict):
            includes = content['jobs'].get('include') or []
        if not includes and isinstance(content.get('matrix'), dict):
            includes = content['matrix'].get('include') or []

        if includes:
            self._parse_includes(includes, source)
        else:
            # Fall back to matrix expansion or single-job
            matrix_jobs = self._expand_matrix(content)
            if matrix_jobs:
                stage = 'test'
                if stage not in self.stages:
                    self.stages.append(stage)
                prev_stage_jobs = []
                for cfg in matrix_jobs:
                    name = cfg.pop('_name')
                    self._register(name, stage, list(prev_stage_jobs), source, cfg)
            else:
                language = content.get('language', 'build')
                self._register(language, 'build', [], source, content)
        return self

    # ------------------------------------------------------------------
    def _parse_includes(self, includes, source):
        # Group jobs by stage, preserving stage order.
        stages_in_order = []
        groups = {}
        unnamed_index = 0
        for entry in includes:
            if not isinstance(entry, dict):
                continue
            stage = entry.get('stage') or 'test'
            if stage not in groups:
                groups[stage] = []
                stages_in_order.append(stage)
            name = entry.get('name')
            if not name:
                unnamed_index += 1
                name = f"{stage}#{unnamed_index}"
            groups[stage].append((name, entry))

        prev_stage_jobs = []
        for stage in stages_in_order:
            if stage not in self.stages:
                self.stages.append(stage)
            current_jobs = []
            for name, entry in groups[stage]:
                stored = name
                suffix = 2
                while stored in self.jobs:
                    stored = f"{name}#{suffix}"
                    suffix += 1
                self._register(stored, stage, list(prev_stage_jobs), source, entry)
                current_jobs.append(stored)
            prev_stage_jobs = current_jobs

    # ------------------------------------------------------------------
    def _expand_matrix(self, content):
        """Expand ``env:`` matrix entries into a list of jobs.

        Travis's ``env:`` may be a list of strings — each string is
        one matrix entry. If ``env: jobs: [...]`` is present we use
        that. Combinations across axes are capped at ``matrix_limit``.
        """
        env = content.get('env')
        envs = []
        if isinstance(env, list):
            envs = env
        elif isinstance(env, dict):
            envs = env.get('jobs') or []

        axes = []
        if envs:
            axes.append(envs)
        for key in ('os', 'python', 'node_js', 'ruby'):
            val = content.get(key)
            if isinstance(val, list) and len(val) > 1:
                axes.append(val)

        if not axes:
            return []

        combos = list(itertools.product(*axes))
        if len(combos) > self.matrix_limit:
            self._truncated = True
            self._warn_truncated(len(combos))
            combos = combos[: self.matrix_limit]

        jobs = []
        for i, combo in enumerate(combos, 1):
            cfg = {'_combo': combo}
            cfg['_name'] = f"job_{i}"
            jobs.append(cfg)
        return jobs

    def _warn_truncated(self, total):
        import sys
        from ..colors import Colors
        print(
            f"  {Colors.YELLOW}WARNING: Travis matrix produced {total} "
            f"jobs; truncated to {self.matrix_limit} (matrix_limit).{Colors.RESET}",
            file=sys.stderr,
        )

    def _register(self, name, stage, deps, source, cfg):
        if name in self.jobs:
            return
        self.jobs[name] = dict(cfg) if isinstance(cfg, dict) else {}
        self.jobs[name]['_stage'] = stage
        self.file_map[name] = source
        self._needs[name] = list(deps)

    # ------------------------------------------------------------------
    def get_job_stage(self, job_name):
        job = self.jobs.get(job_name)
        if not job:
            return 'unknown'
        return job.get('_stage', 'workflow')

    def get_job_needs(self, job_name):
        return [{'job': n, 'optional': False}
                for n in self._needs.get(job_name, [])]
