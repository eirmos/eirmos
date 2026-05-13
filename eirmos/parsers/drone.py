"""Drone CI / Woodpecker CI parser (shared).

Drone and Woodpecker share the same dependency model:

* Steps live under ``steps:`` (or ``pipeline:`` in legacy configs).
* Steps may be a **list** (each step has a ``name:``) or a
  **mapping** (the key is the step name).
* Cross-step ordering uses ``depends_on:`` (string or list).
* Without ``depends_on``, steps run in declaration order
  (sequential fallback).

A single ``Workflow`` file may contain multiple pipelines (separated
by YAML document markers ``---``). We merge all of them into one
graph; collisions across documents are disambiguated by suffix.
"""

from pathlib import Path

from .._yaml import yaml, safe_load_all
from .base import BasePipelineParser


class DroneParser(BasePipelineParser):
    """Parses ``.drone.yml`` / ``.woodpecker.yml`` (and ``.woodpecker/*.yml``)."""

    def __init__(self, base_path='.', workflow_name="Drone CI"):
        super().__init__(base_path=base_path)
        self.workflow_name = workflow_name
        self._needs = {}

    # ------------------------------------------------------------------
    def parse(self, file_path):
        file_path = Path(file_path).resolve()
        if not file_path.exists():
            return self
        self.parsed_files.add(str(file_path))
        try:
            with open(file_path, 'r') as f:
                docs = list(safe_load_all(f))
        except (yaml.YAMLError, IOError):
            # Fall back to single-doc loader (which prints a warning).
            content = self._load_yaml(file_path)
            docs = [content] if content is not None else []

        source = str(file_path)
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            self._parse_doc(doc, source)
        return self

    # ------------------------------------------------------------------
    def _parse_doc(self, doc, source):
        pipeline_name = doc.get('name') or 'pipeline'
        if pipeline_name not in self.stages:
            self.stages.append(pipeline_name)

        steps = doc.get('steps')
        if steps is None:
            steps = doc.get('pipeline')

        # Normalise mapping form to list form: [{'name': k, **v}, ...]
        if isinstance(steps, dict):
            normalised = []
            for k, v in steps.items():
                if not isinstance(v, dict):
                    continue
                entry = dict(v)
                entry['name'] = k
                normalised.append(entry)
            steps = normalised

        if not isinstance(steps, list):
            return

        prev = None
        for step in steps:
            if not isinstance(step, dict):
                continue
            name = step.get('name') or f"step_{len(self.jobs) + 1}"
            stored_name = name
            suffix = 2
            while stored_name in self.jobs:
                stored_name = f"{name}#{suffix}"
                suffix += 1

            depends = step.get('depends_on')
            if depends is None:
                deps = [prev] if prev else []
            elif isinstance(depends, str):
                deps = [depends]
            elif isinstance(depends, list):
                deps = [d for d in depends if isinstance(d, str)]
            else:
                deps = []

            cfg = dict(step)
            cfg['_stage'] = pipeline_name
            self.jobs[stored_name] = cfg
            self.file_map[stored_name] = source
            self._needs[stored_name] = deps
            prev = stored_name

    # ------------------------------------------------------------------
    def get_job_stage(self, job_name):
        job = self.jobs.get(job_name)
        if not job:
            return 'unknown'
        return job.get('_stage', 'pipeline')

    def get_job_needs(self, job_name):
        return [{'job': n, 'optional': False}
                for n in self._needs.get(job_name, [])]


class WoodpeckerParser(DroneParser):
    """Identical model to Drone; separate class for registry display."""

    def __init__(self, base_path='.'):
        super().__init__(base_path=base_path, workflow_name="Woodpecker CI")
