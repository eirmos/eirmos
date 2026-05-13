"""GitHub Actions workflow parser."""

from pathlib import Path

from .base import BasePipelineParser


class GitHubActionsParser(BasePipelineParser):
    """Parses GitHub Actions YAML files and extracts job definitions."""

    def __init__(self, base_path='.'):
        super().__init__(base_path=base_path)
        self.workflow_name = "GitHub Workflow"

    def parse(self, file_path):
        file_path = Path(file_path).resolve()
        content = self._load_yaml(file_path)
        if content is None:
            return self

        self.workflow_name = content.get('name', file_path.name)
        jobs_dict = content.get('jobs', {})
        if isinstance(jobs_dict, dict):
            for job_id, job_config in jobs_dict.items():
                if isinstance(job_config, dict):
                    self.jobs[job_id] = job_config
                    self.file_map[job_id] = str(file_path)
        return self

    def get_job_stage(self, job_name):
        return 'workflow'

    def get_job_needs(self, job_name):
        job = self.jobs.get(job_name)
        if not job:
            return []

        needs = job.get('needs', [])
        if isinstance(needs, str):
            needs = [needs]
        if not isinstance(needs, list):
            return []
        return [{'job': n, 'optional': False} for n in needs]

    def get_job_rules_summary(self, job_name):
        return "on: push/pr"
