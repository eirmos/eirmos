"""Azure Pipelines parser.

Azure pipelines come in three top-level shapes:

* ``stages: [...]``     — multi-stage pipeline (each stage owns ``jobs:``)
* ``jobs: [...]``       — flat list of jobs (single implicit stage)
* ``steps: [...]``      — single implicit job (single implicit stage)

Stages and jobs both support ``dependsOn`` (string or list). When
``dependsOn`` is omitted the entity implicitly depends on the
previous one in declaration order::

    stages:
      - stage: build           ◄── no deps
      - stage: test            ◄── implicitly dependsOn: build
      - stage: deploy
        dependsOn: [build]     ◄── explicit, skips test

Deployment jobs (``deployment: name``) are modelled as regular jobs.
"""

from pathlib import Path

from .base import BasePipelineParser


class AzurePipelinesParser(BasePipelineParser):
    """Parses ``azure-pipelines.yml`` (or ``.azure-pipelines/*.yml``)."""

    def __init__(self, base_path='.'):
        super().__init__(base_path=base_path)
        self.workflow_name = "Azure Pipelines"
        self._needs = {}  # job_name -> [predecessor names]
        self._stage_jobs = {}  # stage_name -> [job names registered in it]

    # ------------------------------------------------------------------
    def parse(self, file_path):
        file_path = Path(file_path).resolve()
        content = self._load_yaml(file_path)
        if content is None:
            return self

        self.workflow_name = content.get('name', "Azure Pipelines")
        source = str(file_path)

        if isinstance(content.get('stages'), list):
            self._parse_stages(content['stages'], source)
        elif isinstance(content.get('jobs'), list):
            self._parse_flat_jobs(content['jobs'], source, stage='jobs')
        elif isinstance(content.get('steps'), list):
            # Single implicit job covering the whole file
            name = self.workflow_name or 'job'
            self._register_job(name, 'job', [], source, {'steps': content['steps']})
        return self

    # ------------------------------------------------------------------
    def _parse_stages(self, stages, source):
        prev_stage = None
        for entry in stages:
            if not isinstance(entry, dict):
                continue
            stage_name = entry.get('stage') or entry.get('template') or 'stage'
            if stage_name not in self.stages:
                self.stages.append(stage_name)
            stage_dep_stages = self._normalise_depends(entry.get('dependsOn'),
                                                      implicit=prev_stage)
            # Map predecessor stage names to the actual last-jobs of
            # those stages so cross-stage edges connect to real nodes.
            stage_dep_jobs = []
            for dep_stage in stage_dep_stages:
                tail = self._stage_jobs.get(dep_stage, [])
                if tail:
                    stage_dep_jobs.extend(tail)
            jobs = entry.get('jobs') if isinstance(entry.get('jobs'), list) else []
            self._parse_stage_jobs(jobs, stage_name, stage_dep_jobs, source)
            prev_stage = stage_name

    def _parse_stage_jobs(self, jobs, stage_name, stage_deps, source):
        prev_job = None
        last_jobs_in_stage = []
        for entry in jobs:
            if not isinstance(entry, dict):
                continue
            job_name = (entry.get('job') or entry.get('deployment')
                        or entry.get('template') or 'job')
            # Job dependsOn defaults to "previous job in this stage" when
            # omitted; if there is no previous job, inherit the stage's
            # predecessors so the graph still connects.
            implicit = prev_job if prev_job else None
            job_deps = self._normalise_depends(entry.get('dependsOn'),
                                               implicit=implicit)
            if not entry.get('dependsOn') and prev_job is None:
                # First job of a stage inherits stage-level predecessors.
                job_deps = list(stage_deps)
            self._register_job(job_name, stage_name, job_deps, source, entry)
            prev_job = job_name
            last_jobs_in_stage.append(job_name)
        self._stage_jobs[stage_name] = last_jobs_in_stage

    def _parse_flat_jobs(self, jobs, source, stage):
        if stage not in self.stages:
            self.stages.append(stage)
        prev_job = None
        for entry in jobs:
            if not isinstance(entry, dict):
                continue
            job_name = (entry.get('job') or entry.get('deployment')
                        or entry.get('template') or 'job')
            job_deps = self._normalise_depends(entry.get('dependsOn'),
                                               implicit=prev_job)
            self._register_job(job_name, stage, job_deps, source, entry)
            prev_job = job_name

    # ------------------------------------------------------------------
    @staticmethod
    def _normalise_depends(value, implicit=None):
        """Return a list of dependency names.

        Accepts string, list, or None. None means "use the implicit
        predecessor" (or no deps if there isn't one).
        """
        if value is None:
            return [implicit] if implicit else []
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [v for v in value if isinstance(v, str)]
        return []

    def _register_job(self, name, stage, deps, source, cfg):
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
