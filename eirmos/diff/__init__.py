"""Pipeline graph diffing.

Pure structural diff over two ``DependencyGraph`` objects. No I/O, no
git, no platform coupling — the testable core of the diff feature
described in ``eirmos-graph-diff-plan.md``.

The output is a :class:`GraphDelta`; render it via
:mod:`eirmos.diff.render`.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from ..graph import DependencyGraph


# ``NEEDS`` edges drive ordering — they're the only ones that
# contribute to the structural critical path. ``trigger`` and
# ``extends`` are reported in add/remove deltas but don't form
# a dependency chain.
_NEEDS_EDGES = DependencyGraph.NEEDS_EDGES


@dataclass
class GraphDelta:
    """Structured difference between two pipeline graphs.

    Built by :meth:`GraphDiff.compute`. Rendering lives in
    :mod:`eirmos.diff.render` — keep this dataclass platform- and
    presentation-free so it stays trivially testable.
    """

    nodes_added: List[str] = field(default_factory=list)
    nodes_removed: List[str] = field(default_factory=list)
    nodes_stage_changed: List[Tuple[str, str, str]] = field(default_factory=list)
    edges_added: List[Tuple[str, str, str]] = field(default_factory=list)
    edges_removed: List[Tuple[str, str, str]] = field(default_factory=list)

    cycle_introduced: bool = False
    # base, head longest needs-chain (number of jobs). ``None`` if
    # either side has a cycle — the critical path is undefined there.
    critical_path: Optional[Tuple[int, int]] = None
    # Newly-added jobs with no in- AND no out-edges (any edge type).
    # Informational: usually a sign the author forgot to wire them up.
    isolated_added: List[str] = field(default_factory=list)

    # Parse-status of the two inputs. Drives "broken config" reporting
    # so a YAML typo isn't rendered as a mass deletion (plan §5).
    base_status: str = 'ok'
    head_status: str = 'ok'

    # When set, the diff was short-circuited because the two sides use
    # different CI systems (a migration PR). Carries the human-readable
    # names. Structural fields above are left at their defaults.
    ci_system_changed: Optional[Tuple[str, str]] = None

    @property
    def has_changes(self) -> bool:
        """True if any structural delta — or a status/system shift — was found."""
        return bool(
            self.nodes_added
            or self.nodes_removed
            or self.nodes_stage_changed
            or self.edges_added
            or self.edges_removed
            or self.cycle_introduced
            or self.ci_system_changed
            or self.base_status != 'ok'
            or self.head_status != 'ok'
        )

    @property
    def critical_path_regressed(self) -> bool:
        """True iff structural critical path grew from base to head."""
        if self.critical_path is None:
            return False
        base_len, head_len = self.critical_path
        return head_len > base_len


class GraphDiff:
    """Compute structural deltas between two pipeline graphs."""

    @staticmethod
    def compute(
        base_graph: Optional[DependencyGraph],
        head_graph: Optional[DependencyGraph],
        *,
        base_system: Optional[str] = None,
        head_system: Optional[str] = None,
        base_status: str = 'ok',
        head_status: str = 'ok',
    ) -> GraphDelta:
        """Diff ``base_graph`` against ``head_graph``.

        ``base_system`` / ``head_system`` are the human-readable CI system
        names (e.g. ``"GitHub Actions"``). When they differ, the diff is
        short-circuited to a migration notice — structural diffing across
        systems is not meaningful (the node-naming conventions, stage
        semantics, and edge types are all different).

        ``base_status`` / ``head_status`` come from
        :attr:`BasePipelineParser.status`. When either side is
        ``'failed'`` the delta carries that status and skips structural
        fields — a parse failure must not be rendered as a deletion.
        """
        delta = GraphDelta(base_status=base_status, head_status=head_status)

        # CI system migration short-circuits everything else: the graphs
        # are not comparable.
        if base_system and head_system and base_system != head_system:
            delta.ci_system_changed = (base_system, head_system)
            return delta

        # Parse failure on either side is also a hard stop — see plan §5.
        # We still surface the status; rendering will explain.
        if base_status == 'failed' or head_status == 'failed':
            return delta

        base_jobs = set(base_graph.parser.jobs.keys()) if base_graph else set()
        head_jobs = set(head_graph.parser.jobs.keys()) if head_graph else set()

        # Sort everything: deterministic output makes snapshot tests and
        # CI comments diff-friendly across runs.
        delta.nodes_added = sorted(head_jobs - base_jobs)
        delta.nodes_removed = sorted(base_jobs - head_jobs)

        for job in sorted(base_jobs & head_jobs):
            base_stage = base_graph.parser.get_job_stage(job)
            head_stage = head_graph.parser.get_job_stage(job)
            if base_stage != head_stage:
                delta.nodes_stage_changed.append((job, base_stage, head_stage))

        base_edges = set(base_graph.edges) if base_graph else set()
        head_edges = set(head_graph.edges) if head_graph else set()
        delta.edges_added = sorted(head_edges - base_edges)
        delta.edges_removed = sorted(base_edges - head_edges)

        base_has_cycle = bool(base_graph and base_graph.has_cycle())
        head_has_cycle = bool(head_graph and head_graph.has_cycle())
        delta.cycle_introduced = head_has_cycle and not base_has_cycle

        # Critical path is undefined when either side has a cycle — the
        # longest-chain computation would loop forever. Skip it cleanly.
        if not base_has_cycle and not head_has_cycle:
            base_cp = _longest_needs_chain(base_graph) if base_graph else 0
            head_cp = _longest_needs_chain(head_graph) if head_graph else 0
            delta.critical_path = (base_cp, head_cp)

        if head_graph and delta.nodes_added:
            # Newly added job that nothing else points to and which
            # points to nothing — likely a dead-end, surface it.
            with_any_edge = set()
            for src, dst, _ in head_graph.edges:
                with_any_edge.add(src)
                with_any_edge.add(dst)
            delta.isolated_added = [j for j in delta.nodes_added
                                    if j not in with_any_edge]

        return delta


def _longest_needs_chain(graph: DependencyGraph) -> int:
    """Return the number of jobs in the longest ``needs``/``needs-optional`` chain.

    Caller must guarantee the graph is acyclic — otherwise this loops.
    ``GraphDiff.compute`` enforces that with ``has_cycle()`` before
    invoking us.
    """
    if not graph.parser.jobs:
        return 0

    # Adjacency: src -> [dst]. Only nodes that are real jobs participate
    # in the structural chain — synthetic ``[child:...]`` trigger
    # targets aren't jobs and shouldn't extend the path.
    real_jobs = set(graph.parser.jobs.keys())
    adj = defaultdict(list)
    in_degree = defaultdict(int)
    for src, dst, etype in graph.edges:
        if etype not in _NEEDS_EDGES:
            continue
        if src not in real_jobs or dst not in real_jobs:
            continue
        adj[src].append(dst)
        in_degree[dst] += 1

    # Topological order via Kahn's algorithm.
    queue = [j for j in real_jobs if in_degree[j] == 0]
    order = []
    while queue:
        n = queue.pop(0)
        order.append(n)
        for nxt in adj.get(n, []):
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                queue.append(nxt)

    # DP: longest_to[n] = 1 + max(longest_to[pred]). A standalone job
    # contributes length 1 (itself).
    longest_to = {j: 1 for j in real_jobs}
    for n in order:
        for nxt in adj.get(n, []):
            cand = longest_to[n] + 1
            if cand > longest_to[nxt]:
                longest_to[nxt] = cand

    return max(longest_to.values())


__all__ = ["GraphDelta", "GraphDiff"]
