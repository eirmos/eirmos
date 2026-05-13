"""Codefresh parser.

Codefresh pipelines are an ordered mapping of step name → step config
under ``steps:``. Cross-step ordering is mostly *implicit* (steps
run in declaration order), with an optional ``when.steps:`` clause
overriding it::

    steps:
      clone:
        type: git-clone
      build:
        type: build
        when:
          steps:
            - name: clone
              on: [success]
      run_tests:
        type: parallel        ◄── flatten children as peers
        steps:
          unit:
            type: freestyle
          lint:
            type: freestyle

Children of a ``type: parallel`` block become peer jobs, each
inheriting the parent block's predecessor (computed from
``when.steps[].name`` of the enclosing parallel block, or
sequential fallback).
"""

from pathlib import Path

from .base import BasePipelineParser


class CodefreshParser(BasePipelineParser):
    """Parses ``codefresh.yml`` / ``.codefresh.yml``."""

    def __init__(self, base_path='.'):
        super().__init__(base_path=base_path)
        self.workflow_name = "Codefresh"
        self._needs = {}
        self._last_registered = None

    # ------------------------------------------------------------------
    def parse(self, file_path):
        file_path = Path(file_path).resolve()
        content = self._load_yaml(file_path)
        if content is None:
            return self

        self.workflow_name = content.get('name', "Codefresh")
        steps = content.get('steps') or {}
        if not isinstance(steps, dict):
            return self
        if 'workflow' not in self.stages:
            self.stages.append('workflow')

        source = str(file_path)
        self._walk(steps, source, parent_predecessor=None, prev_seq=[None])
        return self

    # ------------------------------------------------------------------
    def _walk(self, steps_map, source, parent_predecessor, prev_seq):
        """Walk a steps mapping, registering jobs.

        ``parent_predecessor`` is the step name (or None) that an
        explicit-``when``-less child should depend on. ``prev_seq`` is
        a 1-element mutable list holding the most recently registered
        sibling so siblings without ``when:`` chain sequentially.
        """
        for name, cfg in steps_map.items():
            if not isinstance(cfg, dict):
                continue
            explicit_deps = self._explicit_when(cfg)
            if explicit_deps is not None:
                deps = explicit_deps
            else:
                deps = [prev_seq[0]] if prev_seq[0] else (
                    [parent_predecessor] if parent_predecessor else [])

            if cfg.get('type') == 'parallel' and isinstance(cfg.get('steps'), dict):
                # The parallel block itself is not registered as a job;
                # children inherit `deps` as their predecessor and run
                # as peers.
                child_seq = [None]  # children do not chain among themselves
                parent_pred = deps[0] if deps else None
                # Recurse with a shared parent_predecessor so each child
                # gets `deps` (unless the child has its own explicit when).
                self._walk_parallel(cfg['steps'], source, parent_pred, deps)
                # The "successor of this parallel block" is any child;
                # for sequential chaining we point to the LAST child
                # registered (deterministic).
                last_child = self._last_registered
                prev_seq[0] = last_child
                continue

            self._register(name, deps, source, cfg)
            prev_seq[0] = name
            self._last_registered = name

    def _walk_parallel(self, steps_map, source, parent_predecessor, default_deps):
        for name, cfg in steps_map.items():
            if not isinstance(cfg, dict):
                continue
            explicit = self._explicit_when(cfg)
            deps = explicit if explicit is not None else list(default_deps)
            self._register(name, deps, source, cfg)
            self._last_registered = name

    @staticmethod
    def _explicit_when(cfg):
        when = cfg.get('when')
        if not isinstance(when, dict):
            return None
        steps = when.get('steps')
        if not isinstance(steps, list):
            return None
        deps = []
        for s in steps:
            if isinstance(s, dict) and isinstance(s.get('name'), str):
                deps.append(s['name'])
        return deps

    def _register(self, name, deps, source, cfg):
        if name in self.jobs:
            return
        self.jobs[name] = dict(cfg)
        self.jobs[name]['_stage'] = 'workflow'
        self.file_map[name] = source
        # Filter Nones out of deps
        self._needs[name] = [d for d in deps if d]

    # ------------------------------------------------------------------
    def get_job_stage(self, job_name):
        job = self.jobs.get(job_name)
        if not job:
            return 'unknown'
        return job.get('_stage', 'workflow')

    def get_job_needs(self, job_name):
        return [{'job': n, 'optional': False}
                for n in self._needs.get(job_name, [])]

    def get_job_rules_summary(self, job_name):
        job = self.jobs.get(job_name)
        if not job:
            return ''
        triggers = []
        when = job.get('when')
        if isinstance(when, dict):
            steps = when.get('steps')
            if isinstance(steps, list):
                for s in steps:
                    if isinstance(s, dict):
                        # YAML 1.1 parses bare `on:` as the boolean True;
                        # check both spellings.
                        on = s.get('on')
                        if on is None:
                            on = s.get(True)
                        if isinstance(on, list):
                            triggers.extend(on)
                        elif isinstance(on, str):
                            triggers.append(on)
        return ', '.join(sorted(set(triggers)))
