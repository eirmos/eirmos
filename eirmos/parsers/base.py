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
        # Files we attempted to read but couldn't (malformed YAML, IO
        # error, or non-mapping top-level). Drives ``status`` so callers
        # — notably the diff engine — can distinguish a broken config
        # from a genuinely empty one.
        self.parse_errors = []

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------
    @abstractmethod
    def parse(self, file_path=None):
        """Parse the given file (or a default one) and return ``self``."""

    @property
    def status(self):
        """``'failed'`` if any file errored, ``'empty'`` if no jobs, else ``'ok'``.

        The diff engine relies on this to avoid reporting a YAML typo as
        a mass deletion of every job — see plan section 5 (CRITICAL GAP).
        """
        if self.parse_errors:
            return 'failed'
        if not self.jobs:
            return 'empty'
        return 'ok'

    # ------------------------------------------------------------------
    # Shared loaders
    # ------------------------------------------------------------------
    def _load_yaml(self, file_path):
        """Open a YAML file and return its top-level mapping.

        Returns ``None`` if the file is missing, unreadable, malformed,
        or the top-level isn't a mapping. On parse / IO error a yellow
        warning is emitted to stderr and the file is recorded in
        ``self.parse_errors`` so ``status`` can flip to ``'failed'``.
        The path is added to ``self.parsed_files`` whenever the file
        exists, so callers don't double-track it.
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
            self.parse_errors.append((str(file_path), str(e)))
            return None
        if not isinstance(content, dict):
            # A non-mapping top-level is malformed for every CI system
            # we support — flag it instead of silently returning empty.
            self.parse_errors.append(
                (str(file_path), "top-level is not a mapping"))
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
