"""GitLab CI YAML parser."""

import re
from pathlib import Path

from .base import BasePipelineParser


class GitLabCIParser(BasePipelineParser):
    """Parses GitLab CI YAML files and extracts job definitions."""

    # Keys that are GitLab CI keywords (not job names)
    RESERVED_KEYS = {
        'default', 'variables', 'stages', 'include', 'workflow',
        'image', 'services', 'before_script', 'after_script',
        'cache', 'artifacts', 'pages', 'deploy'
    }

    # Keys whose presence in a mapping marks it as a job/template
    JOB_MARKERS = (
        'script', 'stage', 'extends', 'trigger', 'rules',
        'needs', 'image', 'variables', 'before_script',
        'after_script', 'services', 'artifacts', 'cache',
        'allow_failure', 'tags', 'resource_group', 'parallel',
    )

    def __init__(self, base_path='.', follow_includes=True):
        super().__init__(base_path=base_path)
        self.follow_includes = follow_includes
        self.includes = []
        self.global_variables = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def parse(self, file_path=None):
        """Parse the main CI file and optionally follow includes."""
        if file_path is None:
            file_path = self.base_path / '.gitlab-ci.yml'
        else:
            file_path = Path(file_path).resolve()

        self._parse_file(file_path)
        return self

    def get_job_stage(self, job_name):
        job = self._lookup(job_name)
        if not job:
            return 'unknown'

        if 'stage' in job:
            return job['stage']

        for ext in self._normalize_extends(job.get('extends')):
            ext_job = self._lookup(ext)
            if ext_job and 'stage' in ext_job:
                return ext_job['stage']

        return 'test'  # GitLab default

    def get_job_needs(self, job_name):
        job = self._lookup(job_name)
        if not job:
            return []

        needs = job.get('needs', [])
        if not isinstance(needs, list):
            return []

        result = []
        for need in needs:
            if isinstance(need, str):
                result.append({'job': need, 'optional': False})
            elif isinstance(need, dict):
                if 'job' in need:
                    result.append({
                        'job': need['job'],
                        'optional': need.get('optional', False),
                        'artifacts': need.get('artifacts', True),
                    })
                elif 'pipeline' in need:
                    result.append({
                        'pipeline': need.get('pipeline', ''),
                        'job': need.get('job', ''),
                        'optional': True,
                    })
        return result

    def get_job_extends(self, job_name):
        job = self._lookup(job_name)
        if not job:
            return []
        return self._normalize_extends(job.get('extends'))

    def get_job_triggers(self, job_name):
        job = self._lookup(job_name)
        if not job:
            return None

        trigger = job.get('trigger')
        if not trigger:
            return None

        if isinstance(trigger, str):
            return {'type': 'project', 'project': trigger}
        if isinstance(trigger, dict):
            if 'include' in trigger:
                inc = trigger['include']
                if isinstance(inc, str):
                    return {'type': 'child', 'include': inc}
                if isinstance(inc, list):
                    paths = []
                    for item in inc:
                        if isinstance(item, dict) and 'local' in item:
                            paths.append(item['local'])
                        elif isinstance(item, str):
                            paths.append(item)
                    return {'type': 'child', 'include': paths}
            if 'project' in trigger:
                return {'type': 'project', 'project': trigger['project']}
        return None

    def get_job_rules_summary(self, job_name):
        job = self._lookup(job_name)
        if not job:
            return ''

        rules = job.get('rules', [])
        if not rules:
            return 'always'

        triggers = set()
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            condition = str(rule.get('if', ''))
            if 'web' in condition:
                triggers.add('manual')
            if 'push' in condition:
                triggers.add('push')
            if 'merge_request' in condition:
                triggers.add('MR')
            if 'schedule' in condition:
                triggers.add('schedule')
            if 'parent_pipeline' in condition:
                triggers.add('child')

            custom_match = re.search(r'CUSTOM_BUILD\s*==\s*"([^"]+)"', condition)
            if custom_match:
                triggers.add(f'CB:{custom_match.group(1)}')

        return ', '.join(sorted(triggers)) if triggers else 'conditional'

    def get_job_variables(self, job_name):
        job = self._lookup(job_name)
        if not job:
            return {}

        variables = {}
        for ext in self.get_job_extends(job_name):
            ext_job = self._lookup(ext)
            if ext_job and 'variables' in ext_job:
                variables.update(ext_job.get('variables', {}))
        if 'variables' in job:
            variables.update(job.get('variables', {}))
        return variables

    def get_global_variables(self):
        return self.global_variables

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _lookup(self, job_name):
        return self.jobs.get(job_name) or self.templates.get(job_name)

    @staticmethod
    def _normalize_extends(extends):
        if extends is None:
            return []
        if isinstance(extends, str):
            return [extends]
        if isinstance(extends, list):
            return list(extends)
        return []

    def _parse_file(self, file_path):
        file_path = Path(file_path).resolve()

        if str(file_path) in self.parsed_files:
            return

        content = self._load_yaml(file_path)
        if content is None:
            return

        try:
            rel_path = str(file_path.relative_to(self.base_path))
        except ValueError:
            rel_path = str(file_path)

        # Stages
        if isinstance(content.get('stages'), list):
            for stage in content['stages']:
                if stage not in self.stages:
                    self.stages.append(stage)

        # Includes
        if 'include' in content:
            includes = content['include']
            if not isinstance(includes, list):
                includes = [includes]
            for inc in includes:
                self._process_include(inc)

        # Global variables
        if isinstance(content.get('variables'), dict):
            self.global_variables.update(content['variables'])

        # Jobs / templates
        for key, value in content.items():
            if key in self.RESERVED_KEYS:
                continue
            if not isinstance(value, dict):
                continue
            if not any(k in value for k in self.JOB_MARKERS):
                continue

            if key.startswith('.'):
                self.templates[key] = value
            else:
                self.jobs[key] = value
            self.file_map[key] = rel_path

    def _process_include(self, include_spec):
        if isinstance(include_spec, str):
            local_path = include_spec
        elif isinstance(include_spec, dict):
            if 'local' in include_spec:
                local_path = include_spec['local']
            elif 'component' in include_spec:
                self.includes.append({'type': 'component', 'path': include_spec['component']})
                return
            elif 'project' in include_spec:
                self.includes.append({
                    'type': 'project',
                    'project': include_spec['project'],
                    'file': include_spec.get('file', ''),
                })
                return
            else:
                return
        else:
            return

        self.includes.append({'type': 'local', 'path': local_path})

        if self.follow_includes:
            full_path = (self.base_path / local_path.lstrip('/')).resolve()
            base = str(self.base_path)
            resolved = str(full_path)
            if resolved == base or resolved.startswith(base + '/'):
                self._parse_file(full_path)
