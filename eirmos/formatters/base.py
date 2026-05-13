"""Common base class for formatters."""

import re


class BaseFormatter:
    """Tiny shared base — keeps formatter API uniform."""

    def __init__(self, parser, graph):
        self.parser = parser
        self.graph = graph

    def render(self, filter_stage=None, filter_job=None):  # pragma: no cover
        raise NotImplementedError

    @staticmethod
    def sanitize_id(name):
        """Sanitize a name for use as a Mermaid/DOT identifier."""
        return re.sub(r'[^a-zA-Z0-9_]', '_', name)
