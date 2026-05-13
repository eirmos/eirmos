"""Abstract base class describing the parser protocol.

Concrete parsers must populate ``self.jobs``, ``self.parsed_files``
and ``self.file_map`` and implement the ``get_job_*`` methods.
The base class only defines defaults that are reasonable for
pipelines that don't have a given concept (e.g. GitHub Actions
has no templates or child-pipeline triggers).
"""

import sys
from abc import ABC, abstractmethod
from pathlib import Path

from .._yaml import yaml, safe_load
from ..colors import Colors


class BasePipelineParser(ABC):
    """Common interface every CI parser must implement."""

    def __init__(self, base_path='.'):
        self.base_path = Path(base_path).resolve()
        self.jobs = {}
        self.templates = {}
        self.stages = []
        self.parsed_files = set()
        self.file_map = {}

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------
    @abstractmethod
    def parse(self, file_path=None):
        """Parse the given file (or a default one) and return ``self``."""

    # ------------------------------------------------------------------
    # Shared loaders
    # ------------------------------------------------------------------
    def _load_yaml(self, file_path):
        """Open a YAML file and return its top-level mapping.

        Returns ``None`` if the file is missing, unreadable, malformed,
        or the top-level isn't a mapping. On parse / IO error a yellow
        warning is emitted to stderr (matching the existing parser
        pattern). The path is added to ``self.parsed_files`` whenever
        the file exists, so callers don't double-track it.
        """
        file_path = Path(file_path)
        if not file_path.exists():
            return None
        self.parsed_files.add(str(file_path))
        try:
            with open(file_path, 'r') as f:
                content = safe_load(f)
        except (yaml.YAMLError, IOError) as e:
            print(f"  {Colors.YELLOW}WARNING: Could not parse {file_path}: {e}{Colors.RESET}",
                  file=sys.stderr)
            return None
        if not isinstance(content, dict):
            return None
        return content

    # ------------------------------------------------------------------
    # Job introspection — defaults are safe no-ops
    # ------------------------------------------------------------------
    def get_job_stage(self, job_name):
        return 'unknown'

    def get_job_needs(self, job_name):
        return []

    def get_job_extends(self, job_name):
        return []

    def get_job_triggers(self, job_name):
        return None

    def get_job_rules_summary(self, job_name):
        return ''

    def get_job_variables(self, job_name):
        return {}

    def get_global_variables(self):
        return {}
