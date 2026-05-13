"""AppVeyor parser.

AppVeyor pipelines run a fixed sequence of phases on each matrix
entry::

    init → install → before_build → build → after_build →
    before_test → test → after_test → deploy → after_deploy

We model phases as stages running sequentially. If ``environment.matrix``
is present, each combination becomes one job per phase that has any
script defined; otherwise we treat the file as a single matrix entry.

Matrix expansion is capped at ``matrix_limit`` (default 200). When
``image`` and ``environment.matrix`` both list multiple values, the
parser takes their cartesian product (matching AppVeyor's runtime
behaviour).
"""

import itertools
from pathlib import Path

from .base import BasePipelineParser


_PHASES = (
    'init', 'install', 'before_build', 'build', 'after_build',
    'before_test', 'test', 'after_test',
    'deploy', 'after_deploy',
)

# Map a phase name to the YAML keys that, when present, indicate the
# user actually defined work for that phase.
_PHASE_KEYS = {
    'init': ('init',),
    'install': ('install',),
    'before_build': ('before_build',),
    'build': ('build', 'build_script'),
    'after_build': ('after_build',),
    'before_test': ('before_test',),
    'test': ('test', 'test_script'),
    'after_test': ('after_test',),
    'deploy': ('deploy', 'deploy_script'),
    'after_deploy': ('after_deploy',),
}


class AppVeyorParser(BasePipelineParser):
    """Parses ``appveyor.yml`` / ``.appveyor.yml``."""

    def __init__(self, base_path='.', matrix_limit=200):
        super().__init__(base_path=base_path)
        self.workflow_name = "AppVeyor"
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
        active_phases = [p for p in _PHASES if self._has_phase(content, p)]
        if not active_phases:
            # Treat build+test as default if no phases declared
            active_phases = ['build', 'test']

        for phase in active_phases:
            if phase not in self.stages:
                self.stages.append(phase)

        combos = self._expand_matrix(content)
        if not combos:
            combos = [{'_label': ''}]

        # For each combo, lay down one job per active phase.
        prev_phase_jobs = []
        for phase in active_phases:
            current = []
            for combo in combos:
                label = combo.get('_label')
                base = phase
                name = f"{base}[{label}]" if label else base
                stored = name
                suffix = 2
                while stored in self.jobs:
                    stored = f"{name}#{suffix}"
                    suffix += 1
                self._register(stored, phase, list(prev_phase_jobs), source,
                               {'_combo': combo, '_phase': phase})
                current.append(stored)
            prev_phase_jobs = current
        return self

    # ------------------------------------------------------------------
    @staticmethod
    def _has_phase(content, phase):
        return any(k in content for k in _PHASE_KEYS[phase])

    def _expand_matrix(self, content):
        env = content.get('environment') or {}
        matrix = env.get('matrix') if isinstance(env, dict) else None
        images = content.get('image')

        axes = []
        if isinstance(matrix, list) and matrix:
            axes.append([self._label_entry(e) for e in matrix])
        if isinstance(images, list) and len(images) > 1:
            axes.append(images)

        if not axes:
            return []

        combos = list(itertools.product(*axes))
        if len(combos) > self.matrix_limit:
            self._truncated = True
            self._warn_truncated(len(combos))
            combos = combos[: self.matrix_limit]

        result = []
        for combo in combos:
            label = '+'.join(str(part) for part in combo)
            result.append({'_label': label})
        return result

    @staticmethod
    def _label_entry(entry):
        if isinstance(entry, dict):
            return ','.join(f"{k}={v}" for k, v in entry.items())
        return str(entry)

    def _warn_truncated(self, total):
        import sys
        from ..colors import Colors
        print(
            f"  {Colors.YELLOW}WARNING: AppVeyor matrix produced {total} "
            f"combinations; truncated to {self.matrix_limit} "
            f"(matrix_limit).{Colors.RESET}",
            file=sys.stderr,
        )

    def _register(self, name, phase, deps, source, cfg):
        if name in self.jobs:
            return
        self.jobs[name] = dict(cfg)
        self.jobs[name]['_stage'] = phase
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
