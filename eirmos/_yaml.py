"""YAML loader configured for GitLab CI specifics.

Uses a private :class:`_EirmosSafeLoader` subclass so the
``!reference`` constructor is NOT registered on the global
``yaml.SafeLoader``.  Callers should use :func:`safe_load` /
:func:`safe_load_all` instead of ``yaml.safe_load`` /
``yaml.safe_load_all``.
"""

try:
    import yaml
except ImportError:  # pragma: no cover - import-time guard
    raise ImportError(
        "PyYAML is required. Install with: pip install pyyaml"
    )


def _reference_constructor(loader, node):
    """Handle GitLab CI ``!reference`` tags by returning the sequence as-is."""
    return loader.construct_sequence(node)


class _EirmosSafeLoader(yaml.SafeLoader):
    """Private loader with ``!reference`` support, isolated from the global
    ``SafeLoader`` so other libraries in the same process are unaffected."""


yaml.add_constructor('!reference', _reference_constructor, Loader=_EirmosSafeLoader)


def safe_load(stream):
    """Parse the first YAML document in *stream* using the private loader."""
    return yaml.load(stream, Loader=_EirmosSafeLoader)


def safe_load_all(stream):
    """Parse all YAML documents in *stream* using the private loader."""
    return yaml.load_all(stream, Loader=_EirmosSafeLoader)


__all__ = ["yaml", "safe_load", "safe_load_all"]
