"""CircleCI ``.circleci/config.yml`` parser.

CircleCI defines reusable ``jobs`` and one or more ``workflows`` that
chain those jobs together. Inter-job ordering is expressed via the
``requires`` key on a workflow entry::

    version: 2.1
    jobs:
      build: { ... }
      test:  { ... }
      deploy:{ ... }
    workflows:
      ci:
        jobs:
          - build
          - test:
              requires: [build]
          - deploy:
              requires: [test]

For visualisation purposes we expose every workflow-job entry as a
"job" (qualified by workflow name when ambiguous) and translate
``requires`` into ``needs``.
"""

from pathlib import Path

from .base import BasePipelineParser


class CircleCIParser(BasePipelineParser):
    """Parses ``.circleci/config.yml`` workflow definitions."""

    def __init__(self, base_path='.'):
        super().__init__(base_path=base_path)
        self.workflow_name = "CircleCI"
        self._needs = {}  # job_name -> [required job names]

    # ------------------------------------------------------------------
    def parse(self, file_path):
        file_path = Path(file_path).resolve()
        content = self._load_yaml(file_path)
        if content is None:
            return self

        job_defs = content.get('jobs', {}) or {}
        workflows = content.get('workflows', {}) or {}

        # Strip the special ``version`` key from workflows mapping.
        if isinstance(workflows, dict):
            workflows = {k: v for k, v in workflows.items() if k != 'version'}
        else:
            workflows = {}

        if workflows:
            for wf_name, wf in workflows.items():
                if not isinstance(wf, dict):
                    continue
                for entry in wf.get('jobs', []) or []:
                    job_name, requires = _normalise_workflow_entry(entry)
                    if job_name is None:
                        continue
                    self._register(job_name, wf_name, requires, str(file_path),
                                   job_defs.get(job_name, {}))
        else:
            # No workflows: just expose the raw jobs definitions.
            if isinstance(job_defs, dict):
                for job_name, cfg in job_defs.items():
                    self._register(job_name, 'jobs', [], str(file_path),
                                   cfg if isinstance(cfg, dict) else {})
        return self

    # ------------------------------------------------------------------
    def _register(self, job_name, stage, requires, source, cfg):
        self.jobs[job_name] = cfg or {}
        self.file_map[job_name] = source
        if stage not in self.stages:
            self.stages.append(stage)
        self.jobs[job_name]['_stage'] = stage
        self._needs[job_name] = list(requires)

    # ------------------------------------------------------------------
    def get_job_stage(self, job_name):
        job = self.jobs.get(job_name)
        if not job:
            return 'unknown'
        return job.get('_stage', 'workflow')

    def get_job_needs(self, job_name):
        return [{'job': n, 'optional': False} for n in self._needs.get(job_name, [])]


def _normalise_workflow_entry(entry):
    """Return ``(job_name, [requires...])`` for a workflow ``jobs`` entry.

    Entries may be a bare string (``"build"``) or a single-key
    mapping (``{"test": {"requires": ["build"]}}``).
    """
    if isinstance(entry, str):
        return entry, []
    if isinstance(entry, dict) and len(entry) == 1:
        job_name, cfg = next(iter(entry.items()))
        requires = []
        if isinstance(cfg, dict):
            req = cfg.get('requires', []) or []
            if isinstance(req, str):
                requires = [req]
            elif isinstance(req, list):
                requires = [r for r in req if isinstance(r, str)]
        return job_name, requires
    return None, []
