"""Buildkite parser.

Buildkite pipelines are a flat list under ``steps:``. Each step may
declare a ``key:`` (its identifier) and ``depends_on:`` (string or
list referencing other keys).

The non-obvious construct is ``wait`` — a barrier that means
*"every step after me implicitly depends on every step before me"*::

           wait
   step_a ──┐  ┌──► step_d
   step_b ──┤  ├──► step_e
   step_c ──┘  └──► step_f

If a post-wait step already declares ``depends_on``, the explicit
list wins; we do NOT additionally add the cross-product edges
(no double-add).

``group:`` is a container that holds nested ``steps:``; we flatten
its children into the top-level sequence and discard the group
wrapper.
"""

from pathlib import Path

from .base import BasePipelineParser


class BuildkiteParser(BasePipelineParser):
    """Parses ``.buildkite/pipeline.yml`` (and variants)."""

    def __init__(self, base_path='.'):
        super().__init__(base_path=base_path)
        self.workflow_name = "Buildkite"
        self._needs = {}

    # ------------------------------------------------------------------
    def parse(self, file_path):
        file_path = Path(file_path).resolve()
        content = self._load_yaml(file_path)
        if content is None:
            return self

        steps = content.get('steps')
        if not isinstance(steps, list):
            return self

        flat = self._flatten_groups(steps)
        source = str(file_path)
        self._build_graph(flat, source)
        return self

    # ------------------------------------------------------------------
    def _flatten_groups(self, steps):
        """Replace each ``group:`` step with its nested children."""
        result = []
        for step in steps:
            if isinstance(step, dict) and 'group' in step:
                nested = step.get('steps')
                if isinstance(nested, list):
                    result.extend(self._flatten_groups(nested))
                # group itself is dropped
            else:
                result.append(step)
        return result

    def _build_graph(self, steps, source):
        # First pass: collect step definitions (excluding waits) and
        # remember each wait's index in the linear sequence.
        index = []  # parallel to flat list: 'wait' or step name
        last_wait_pos = -1
        registered = {}  # name -> True

        for i, raw in enumerate(steps):
            if raw == 'wait' or (isinstance(raw, dict) and 'wait' in raw and len(raw) == 1):
                index.append(('wait', i))
                continue
            if not isinstance(raw, dict):
                continue
            # Skip pure block / input / trigger steps that have no work
            name = raw.get('key') or raw.get('label') or raw.get('command') \
                or raw.get('block') or raw.get('input') or raw.get('trigger')
            if not name:
                name = f"step_{i + 1}"
            stored = str(name)
            suffix = 2
            while stored in registered:
                stored = f"{name}#{suffix}"
                suffix += 1
            registered[stored] = True
            self.jobs[stored] = dict(raw)
            self.jobs[stored]['_stage'] = 'workflow'
            self.file_map[stored] = source
            index.append(('step', i, stored, raw))
        if 'workflow' not in self.stages:
            self.stages.append('workflow')

        # Second pass: compute deps using waits as cross-product barriers.
        pre_wait = []  # step names in the segment BEFORE the most recent wait
        post_wait = []  # step names in the segment AFTER the most recent wait
        for entry in index:
            if entry[0] == 'wait':
                pre_wait = pre_wait + post_wait
                post_wait = []
                continue
            _, _, name, raw = entry
            explicit = raw.get('depends_on')
            if explicit is None:
                # Implicit: depend on everything in the pre_wait set
                self._needs[name] = list(pre_wait)
            elif isinstance(explicit, str):
                self._needs[name] = [explicit]
            elif isinstance(explicit, list):
                self._needs[name] = [d for d in explicit if isinstance(d, str)]
            else:
                self._needs[name] = []
            post_wait.append(name)

    # ------------------------------------------------------------------
    def get_job_stage(self, job_name):
        job = self.jobs.get(job_name)
        if not job:
            return 'unknown'
        return job.get('_stage', 'workflow')

    def get_job_needs(self, job_name):
        return [{'job': n, 'optional': False}
                for n in self._needs.get(job_name, [])]
