"""Semaphore CI parser.

Semaphore pipelines are organised as ``blocks:`` (top-level units of
work). Each block declares ``dependencies:`` listing the names of
blocks it depends on::

    blocks:
      - name: build
      - name: test
        dependencies: [build]
      - name: deploy
        dependencies: [test]

Each block has nested ``task.jobs:`` running in parallel within the
block; we expose blocks as the unit of the dependency graph (parallel
sub-jobs are not modelled as separate nodes — their parallelism is
implicit within a block).
"""

from pathlib import Path

from .base import BasePipelineParser


class SemaphoreParser(BasePipelineParser):
    """Parses ``.semaphore/semaphore.yml``."""

    def __init__(self, base_path='.'):
        super().__init__(base_path=base_path)
        self.workflow_name = "Semaphore"
        self._needs = {}

    # ------------------------------------------------------------------
    def parse(self, file_path):
        file_path = Path(file_path).resolve()
        content = self._load_yaml(file_path)
        if content is None:
            return self

        self.workflow_name = content.get('name', "Semaphore")
        blocks = content.get('blocks')
        if not isinstance(blocks, list):
            return self
        if 'blocks' not in self.stages:
            self.stages.append('blocks')

        source = str(file_path)
        for block in blocks:
            if not isinstance(block, dict):
                continue
            name = block.get('name')
            if not name:
                continue
            deps = block.get('dependencies') or []
            if not isinstance(deps, list):
                deps = []
            self.jobs[name] = dict(block)
            self.jobs[name]['_stage'] = 'blocks'
            self.file_map[name] = source
            self._needs[name] = [d for d in deps if isinstance(d, str)]
        return self

    # ------------------------------------------------------------------
    def get_job_stage(self, job_name):
        job = self.jobs.get(job_name)
        if not job:
            return 'unknown'
        return job.get('_stage', 'workflow')

    def get_job_needs(self, job_name):
        return [{'job': n, 'optional': False}
                for n in self._needs.get(job_name, [])]
