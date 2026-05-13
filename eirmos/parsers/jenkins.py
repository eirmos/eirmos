"""Jenkins ``Jenkinsfile`` parser.

Jenkins pipelines are written in a Groovy DSL rather than YAML, so a
fully accurate parser would require a Groovy interpreter. This
parser implements a *best-effort* lexical extraction tuned for the
Declarative Pipeline syntax, which is the most common in practice:

    pipeline {
        stages {
            stage('Build')   { ... }
            stage('Test')    { steps { ... } }
            stage('Parallel') {
                parallel {
                    stage('Lint') { ... }
                    stage('Unit') { ... }
                }
            }
        }
    }

We extract stage names and treat them as both jobs and stages, with
sequential ``needs`` dependencies between top-level stages and no
dependencies between siblings inside a ``parallel`` block.
"""

import re
import sys
from pathlib import Path

from ..colors import Colors
from .base import BasePipelineParser


_STAGE_RE = re.compile(r"""stage\s*\(\s*['"]([^'"]+)['"]\s*\)""")


class JenkinsParser(BasePipelineParser):
    """Best-effort parser for declarative ``Jenkinsfile`` pipelines."""

    DEFAULT_FILENAMES = ("Jenkinsfile", "jenkinsfile", "Jenkinsfile.groovy")

    def __init__(self, base_path='.'):
        super().__init__(base_path=base_path)
        self.workflow_name = "Jenkins Pipeline"
        self._order = []  # preserves discovery order for sequential needs
        self._parallel_groups = {}  # job_name -> set(siblings)

    # ------------------------------------------------------------------
    def parse(self, file_path):
        file_path = Path(file_path).resolve()
        if not file_path.exists():
            return self
        self.parsed_files.add(str(file_path))
        try:
            text = file_path.read_text()
        except IOError as e:
            print(f"  {Colors.YELLOW}WARNING: Could not read {file_path}: {e}{Colors.RESET}",
                  file=sys.stderr)
            return self

        self._parse_text(text, str(file_path))
        return self

    # ------------------------------------------------------------------
    def _parse_text(self, text, source):
        """Walk the token stream and extract ``stage('name')`` blocks.

        We track brace depth to detect when we enter/leave a
        ``parallel { ... }`` block so siblings can be flagged as
        parallel (no inter-dependency).
        """
        i = 0
        depth = 0
        # stack of (kind, depth_when_entered) where kind in {"stages","parallel","stage"}
        stack = []
        last_top_stage = None

        while i < len(text):
            ch = text[i]
            if ch == '{':
                depth += 1
                i += 1
                continue
            if ch == '}':
                depth -= 1
                # pop any frames opened deeper than current depth
                while stack and stack[-1][1] > depth:
                    stack.pop()
                i += 1
                continue

            # Match `parallel {`
            m = re.match(r"parallel\s*\{", text[i:])
            if m:
                stack.append(("parallel", depth + 1))
                depth += 1
                i += m.end()
                continue

            # Match `stage('name')`
            m = _STAGE_RE.match(text[i:])
            if m:
                name = m.group(1)
                in_parallel = any(k == "parallel" for k, _ in stack)
                self._add_stage(name, source, in_parallel, last_top_stage)
                if not in_parallel:
                    last_top_stage = name
                # advance past the matched stage(...) header
                i += m.end()
                continue

            i += 1

    def _add_stage(self, name, source, in_parallel, last_top_stage):
        if name in self.jobs:
            return
        self.jobs[name] = {"in_parallel": in_parallel}
        self.file_map[name] = source
        if name not in self.stages:
            self.stages.append(name)
        self._order.append(name)
        if in_parallel:
            # depend on the most recent top-level (non-parallel) stage
            if last_top_stage:
                self.jobs[name]["_needs"] = [last_top_stage]
            else:
                self.jobs[name]["_needs"] = []
        else:
            self.jobs[name]["_needs"] = [last_top_stage] if last_top_stage else []

    # ------------------------------------------------------------------
    def get_job_stage(self, job_name):
        return job_name if job_name in self.jobs else 'unknown'

    def get_job_needs(self, job_name):
        job = self.jobs.get(job_name)
        if not job:
            return []
        return [{'job': n, 'optional': False} for n in job.get('_needs', [])]
