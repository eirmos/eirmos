"""Bitbucket Pipelines parser.

Bitbucket pipelines live in ``bitbucket-pipelines.yml`` under
``pipelines:`` and are grouped by trigger type::

    pipelines:
      default: [...]            # runs on every push
      branches:
        main: [...]
      pull-requests:
        '**': [...]
      custom:
        nightly: [...]

Each value is a list of items. Items are typically ``{step: {...}}``
mappings, but ``parallel:`` siblings are written as
``{parallel: [step, step, ...]}``. Steps run sequentially in
declaration order; parallel siblings share the predecessor of the
``parallel:`` block.
"""

from pathlib import Path

from .base import BasePipelineParser


_GROUPS = ('default', 'branches', 'pull-requests', 'tags', 'custom')


class BitbucketPipelinesParser(BasePipelineParser):
    """Parses ``bitbucket-pipelines.yml``."""

    def __init__(self, base_path='.'):
        super().__init__(base_path=base_path)
        self.workflow_name = "Bitbucket Pipelines"
        self._needs = {}

    # ------------------------------------------------------------------
    def parse(self, file_path):
        file_path = Path(file_path).resolve()
        content = self._load_yaml(file_path)
        if content is None:
            return self

        pipelines = content.get('pipelines') or {}
        if not isinstance(pipelines, dict):
            return self

        source = str(file_path)
        for group in _GROUPS:
            spec = pipelines.get(group)
            if spec is None:
                continue
            if group in ('default',):
                self._parse_pipeline(spec, group, source)
            elif isinstance(spec, dict):
                for trigger_name, items in spec.items():
                    stage = f"{group}:{trigger_name}"
                    self._parse_pipeline(items, stage, source)
        return self

    def _parse_pipeline(self, items, stage, source):
        if not isinstance(items, list):
            return
        if stage not in self.stages:
            self.stages.append(stage)

        prev = None
        for item in items:
            if not isinstance(item, dict):
                continue
            if 'parallel' in item:
                par = item['parallel']
                # Bitbucket allows `{parallel: [...]}` or
                # `{parallel: {steps: [...], fail-fast: true}}`.
                steps = par if isinstance(par, list) else (
                    par.get('steps') if isinstance(par, dict) else [])
                names = []
                for s in steps or []:
                    name = self._register_step(s, stage, [prev] if prev else [], source)
                    if name:
                        names.append(name)
                # Next sequential predecessor is the last parallel sibling
                # (any of them is fine; we pick the last for determinism).
                prev = names[-1] if names else prev
            else:
                name = self._register_step(item, stage, [prev] if prev else [], source)
                if name:
                    prev = name

    def _register_step(self, step_entry, stage, deps, source):
        if not isinstance(step_entry, dict):
            return None
        step = step_entry.get('step')
        if not isinstance(step, dict):
            return None
        name = step.get('name') or f"step_{len(self.jobs) + 1}"
        # Disambiguate duplicate names across stages
        original = name
        suffix = 2
        while name in self.jobs:
            name = f"{original}#{suffix}"
            suffix += 1
        self.jobs[name] = dict(step)
        self.jobs[name]['_stage'] = stage
        self.file_map[name] = source
        self._needs[name] = list(deps)
        return name

    # ------------------------------------------------------------------
    def get_job_stage(self, job_name):
        job = self.jobs.get(job_name)
        if not job:
            return 'unknown'
        return job.get('_stage', 'workflow')

    def get_job_needs(self, job_name):
        return [{'job': n, 'optional': False}
                for n in self._needs.get(job_name, [])]
