"""Render :class:`~eirmos.diff.GraphDelta` to text / markdown / JSON.

These are standalone functions, *not* ``BaseFormatter`` subclasses:
``BaseFormatter.__init__`` takes ``(parser, graph)`` — one of each — and
a diff has two. Force-fitting it would corrupt that interface. See plan
§2 for the rationale.
"""

import json
from typing import Optional

from . import GraphDelta


def render_json(delta: GraphDelta, *, system: Optional[str] = None,
                indent: int = 2) -> str:
    """Stable JSON encoding of the delta — friendly to CI tooling.

    ``system`` is the CI system name (e.g. ``"GitHub Actions"``) used in
    the rendered title. Omit for system-agnostic output.
    """
    payload = {
        "system": system,
        "base_status": delta.base_status,
        "head_status": delta.head_status,
        "ci_system_changed": (
            {"from": delta.ci_system_changed[0],
             "to": delta.ci_system_changed[1]}
            if delta.ci_system_changed else None
        ),
        "nodes_added": list(delta.nodes_added),
        "nodes_removed": list(delta.nodes_removed),
        "nodes_stage_changed": [
            {"job": j, "from": old, "to": new}
            for j, old, new in delta.nodes_stage_changed
        ],
        "edges_added": [
            {"from": s, "to": d, "type": t} for s, d, t in delta.edges_added
        ],
        "edges_removed": [
            {"from": s, "to": d, "type": t} for s, d, t in delta.edges_removed
        ],
        "cycle_introduced": delta.cycle_introduced,
        "critical_path": (
            {"base": delta.critical_path[0], "head": delta.critical_path[1]}
            if delta.critical_path is not None else None
        ),
        "isolated_added": list(delta.isolated_added),
        "has_changes": delta.has_changes,
    }
    return json.dumps(payload, indent=indent, sort_keys=False)


def render_markdown(delta: GraphDelta, *, system: Optional[str] = None) -> str:
    """Render the delta as a PR-ready markdown comment."""
    title = "Pipeline graph changes"
    if system:
        title = f"{title} — {system}"

    lines = [f"### {title}", ""]

    # Hard-stop renderings — bail before structural details to avoid
    # misleading users.
    if delta.ci_system_changed:
        old, new = delta.ci_system_changed
        lines.append(f"**CI system changed:** `{old}` → `{new}`")
        lines.append("")
        lines.append(
            "Skipping structural diff — the two graphs aren't comparable "
            "across systems."
        )
        return "\n".join(lines).rstrip() + "\n"

    if delta.base_status == 'failed' or delta.head_status == 'failed':
        which = []
        if delta.base_status == 'failed':
            which.append("base")
        if delta.head_status == 'failed':
            which.append("head")
        lines.append(
            f"**Could not diff:** parse failed on {', '.join(which)}. "
            "Fix the CI config first — a parse error is not a deletion."
        )
        return "\n".join(lines).rstrip() + "\n"

    if not delta.has_changes:
        lines.append("_No pipeline changes._")
        return "\n".join(lines).rstrip() + "\n"

    for job in delta.nodes_added:
        lines.append(f"- **+ job** `{job}`")
    for job in delta.nodes_removed:
        lines.append(f"- **− job** `{job}`")
    for job, old, new in delta.nodes_stage_changed:
        lines.append(f"- **~ stage** `{job}` `{old}` → `{new}`")
    for src, dst, etype in delta.edges_added:
        lines.append(f"- **+ edge** `{src}` → `{dst}` ({etype})")
    for src, dst, etype in delta.edges_removed:
        lines.append(f"- **− edge** `{src}` → `{dst}` ({etype})")

    if delta.cycle_introduced:
        lines.append("")
        lines.append("- ⚠ **cycle introduced** — head graph has a cycle "
                     "in `needs` that base did not.")

    if delta.critical_path is not None:
        base_len, head_len = delta.critical_path
        if base_len != head_len:
            arrow = "↑" if head_len > base_len else "↓"
            lines.append(
                f"- **! critical path** {arrow} {base_len} → {head_len} jobs"
            )

    if delta.isolated_added:
        lines.append("")
        for job in delta.isolated_added:
            lines.append(
                f"- ⚠ `{job}` has no edges — dead-ends the graph. Intended?"
            )

    return "\n".join(lines).rstrip() + "\n"


def render_text(delta: GraphDelta, *, system: Optional[str] = None) -> str:
    """Render the delta as plain text — what ``eirmos diff`` prints by default."""
    title = "Pipeline graph changes"
    if system:
        title = f"{title} — {system}"
    lines = [title, "=" * len(title)]

    if delta.ci_system_changed:
        old, new = delta.ci_system_changed
        lines.append(f"CI system changed: {old} -> {new}")
        lines.append("Skipping structural diff (graphs not comparable).")
        return "\n".join(lines) + "\n"

    if delta.base_status == 'failed' or delta.head_status == 'failed':
        which = []
        if delta.base_status == 'failed':
            which.append("base")
        if delta.head_status == 'failed':
            which.append("head")
        lines.append(f"Could not diff: parse failed on {', '.join(which)}.")
        return "\n".join(lines) + "\n"

    if not delta.has_changes:
        lines.append("No pipeline changes.")
        return "\n".join(lines) + "\n"

    if delta.nodes_added:
        lines.append("")
        lines.append("Added jobs:")
        for job in delta.nodes_added:
            lines.append(f"  + {job}")
    if delta.nodes_removed:
        lines.append("")
        lines.append("Removed jobs:")
        for job in delta.nodes_removed:
            lines.append(f"  - {job}")
    if delta.nodes_stage_changed:
        lines.append("")
        lines.append("Stage changes:")
        for job, old, new in delta.nodes_stage_changed:
            lines.append(f"  ~ {job}: {old} -> {new}")
    if delta.edges_added:
        lines.append("")
        lines.append("Added edges:")
        for src, dst, etype in delta.edges_added:
            lines.append(f"  + {src} -> {dst} ({etype})")
    if delta.edges_removed:
        lines.append("")
        lines.append("Removed edges:")
        for src, dst, etype in delta.edges_removed:
            lines.append(f"  - {src} -> {dst} ({etype})")

    if delta.cycle_introduced:
        lines.append("")
        lines.append("WARNING: cycle introduced in head graph.")

    if delta.critical_path is not None:
        base_len, head_len = delta.critical_path
        if base_len != head_len:
            lines.append("")
            lines.append(
                f"Critical path: {base_len} -> {head_len} jobs."
            )

    if delta.isolated_added:
        lines.append("")
        lines.append("Isolated added jobs (no edges in or out):")
        for job in delta.isolated_added:
            lines.append(f"  ! {job}")

    return "\n".join(lines) + "\n"


__all__ = ["render_json", "render_markdown", "render_text"]
