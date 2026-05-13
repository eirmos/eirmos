"""Output formatters for ``DependencyGraph`` instances.

All formatters share the same constructor signature
``Formatter(parser, graph)`` and a ``render(filter_stage=None,
filter_job=None) -> str`` method, making them interchangeable.
"""

from .base import BaseFormatter
from .tree import TreeFormatter
from .mermaid import MermaidFormatter
from .dot import DotFormatter
from .summary import SummaryFormatter
from .variables import VariableFormatter

__all__ = [
    "BaseFormatter",
    "TreeFormatter",
    "MermaidFormatter",
    "DotFormatter",
    "SummaryFormatter",
    "VariableFormatter",
]
