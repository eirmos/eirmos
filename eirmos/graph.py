"""Dependency graph built from any parser implementing the protocol."""

from collections import defaultdict


class DependencyGraph:
    """Builds and manages the job dependency graph."""

    NEEDS_EDGES = ('needs', 'needs-optional')

    def __init__(self, parser):
        self.parser = parser
        self.edges = []  # (from_job, to_job, edge_type)
        self.stage_jobs = defaultdict(list)  # stage -> [jobs]
        self._build()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build(self):
        for job_name in self.parser.jobs:
            stage = self.parser.get_job_stage(job_name)
            self.stage_jobs[stage].append(job_name)

        for job_name in self.parser.jobs:
            for need in self.parser.get_job_needs(job_name):
                target = need.get('job')
                if not target:
                    continue
                edge_type = 'needs-optional' if need.get('optional') else 'needs'
                self.edges.append((target, job_name, edge_type))

            trigger = self.parser.get_job_triggers(job_name)
            if trigger:
                label = trigger.get('include') or trigger.get('project') or 'pipeline'
                self.edges.append((job_name, f"[child:{label}]", 'trigger'))

            for ext in self.parser.get_job_extends(job_name):
                if ext in self.parser.jobs:
                    self.edges.append((ext, job_name, 'extends'))

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    def get_predecessors(self, job_name):
        return [(src, etype) for src, dst, etype in self.edges
                if dst == job_name and etype in self.NEEDS_EDGES]

    def get_successors(self, job_name):
        return [(dst, etype) for src, dst, etype in self.edges
                if src == job_name and etype in self.NEEDS_EDGES]

    def get_roots(self):
        with_deps = {dst for _, dst, etype in self.edges if etype in self.NEEDS_EDGES}
        return [j for j in self.parser.jobs if j not in with_deps]

    def get_ordered_stages(self):
        if getattr(self.parser, 'stages', None):
            return list(self.parser.stages)
        stages = []
        for job_name in self.parser.jobs:
            stage = self.parser.get_job_stage(job_name)
            if stage not in stages:
                stages.append(stage)
        return stages

    def has_cycle(self):
        """Return True if the ``needs`` subgraph contains a cycle."""
        adj = defaultdict(list)
        for src, dst, etype in self.edges:
            if etype in self.NEEDS_EDGES:
                adj[src].append(dst)

        WHITE, GRAY, BLACK = 0, 1, 2
        color = defaultdict(int)

        def visit(node):
            color[node] = GRAY
            for nxt in adj.get(node, []):
                if color[nxt] == GRAY:
                    return True
                if color[nxt] == WHITE and visit(nxt):
                    return True
            color[node] = BLACK
            return False

        for n in list(self.parser.jobs.keys()):
            if color[n] == WHITE and visit(n):
                return True
        return False
