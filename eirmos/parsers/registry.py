"""Parser adapter registry.

Each supported CI/CD system is described by a :class:`ParserAdapter`
that knows:

* its display ``name`` (e.g. ``"GitLab CI"``)
* how to ``detect`` whether a given repository uses this system
  (i.e. locate the main pipeline file)
* which :class:`BasePipelineParser` subclass to instantiate, and
  with which keyword arguments

This decouples the CLI from individual parsers and makes it trivial
to add new CI systems: implement a :class:`BasePipelineParser`,
register a :class:`ParserAdapter`, and the CLI will pick it up.

Detection model
---------------

``detect()`` evaluates **every** registered adapter (not just until
the first match) so that polyglot repos — e.g. mid-migration from
Travis to GitHub Actions — can be flagged. The function still
returns the *first* match (preserving the public signature), but
when more than one adapter matches it emits a yellow warning to
stderr naming all matched systems::

    repo
      ├── .travis.yml          ◄── Travis matches
      └── .github/workflows/   ◄── GitHub Actions matches
                                   ─►  WARNING printed; first wins
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Type

from ..colors import Colors
from .base import BasePipelineParser


@dataclass
class ParserAdapter:
    """Adapter describing one CI/CD system."""

    slug: str
    name: str
    parser_class: Type[BasePipelineParser]
    detect: Callable[[Path], Optional[Path]]
    parser_kwargs: Callable[[object], Dict] = field(
        default_factory=lambda: (lambda args: {})
    )


REGISTRY: List[ParserAdapter] = []


def register_adapter(adapter: ParserAdapter) -> ParserAdapter:
    """Register ``adapter`` and return it (usable as a decorator helper)."""
    REGISTRY.append(adapter)
    return adapter


def detect(base_path: Path) -> Tuple[Optional[ParserAdapter], Optional[Path]]:
    """Return the first matching adapter, warning on multi-match.

    Walks the full registry so we can detect polyglot repos. If two
    or more adapters match, prints a yellow warning to stderr and
    returns the first match (registry order is intentional — see the
    comment above the registrations in ``parsers/__init__.py``).
    """
    matches: List[Tuple[ParserAdapter, Path]] = []
    for adapter in REGISTRY:
        main_file = adapter.detect(base_path)
        if main_file is not None:
            matches.append((adapter, main_file))

    if not matches:
        return None, None

    if len(matches) > 1:
        names = ", ".join(a.name for a, _ in matches)
        first = matches[0][0].name
        print(
            f"  {Colors.YELLOW}WARNING: Detected multiple CI systems "
            f"({names}); using {first}.{Colors.RESET}",
            file=sys.stderr,
        )

    adapter, main_file = matches[0]
    return adapter, main_file
