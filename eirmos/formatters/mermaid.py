"""Mermaid flowchart formatter."""

from .base import BaseFormatter


class MermaidFormatter(BaseFormatter):
    """Outputs a Mermaid diagram."""

    @staticmethod
    def _escape_label(name):
        return name.replace('"', '#quot;')

    @staticmethod
    def _make_ids(stage_jobs, edges):
        """Build a unique, collision-free ``name -> id`` mapping."""
        seen = {}
        ids = {}
        all_names = set()
        for jobs in stage_jobs.values():
            all_names.update(jobs)
        for src, dst, _ in edges:
            all_names.add(src)
            all_names.add(dst)
        for name in sorted(all_names):
            sid = BaseFormatter.sanitize_id(name)
            if sid in seen and seen[sid] != name:
                suffix = 2
                while f"{sid}_{suffix}" in seen:
                    suffix += 1
                sid = f"{sid}_{suffix}"
            seen[sid] = name
            ids[name] = sid
        return ids

    def render(self, filter_stage=None, filter_job=None):
        lines = ["```mermaid", "flowchart TD", ""]

        stages = self.graph.get_ordered_stages()
        node_ids = self._make_ids(self.graph.stage_jobs, self.graph.edges)
        rendered_jobs = set()

        for stage in stages:
            if filter_stage and stage != filter_stage:
                continue

            jobs = self.graph.stage_jobs.get(stage, [])
            if not jobs:
                continue

            stage_id = node_ids.get(stage, self.sanitize_id(stage))
            lines.append(f"    subgraph {stage_id}[\"{self._escape_label(stage)}\"]")
            for job_name in sorted(jobs):
                if filter_job and filter_job != job_name:
                    preds = [src for src, dst, _ in self.graph.edges if dst == job_name]
                    succs = [dst for _, dst, _ in self.graph.edges if dst == job_name]
                    if filter_job not in preds and filter_job not in succs:
                        continue

                sid = node_ids[job_name]
                trigger = self.parser.get_job_triggers(job_name)
                escaped = self._escape_label(job_name)
                if trigger:
                    lines.append(f"        {sid}[[\"{escaped}\"]]\n")
                else:
                    lines.append(f"        {sid}[\"{escaped}\"]\n")
                rendered_jobs.add(job_name)
            lines.append("    end")
            lines.append("")

        lines.append("    %% Dependencies")
        for src, dst, etype in self.graph.edges:
            if src not in rendered_jobs and dst not in rendered_jobs:
                continue
            src_id = node_ids.get(src, self.sanitize_id(src))
            dst_id = node_ids.get(dst, self.sanitize_id(dst))
            if etype == 'needs':
                lines.append(f"    {src_id} --> {dst_id}")
            elif etype == 'needs-optional':
                lines.append(f"    {src_id} -.-> {dst_id}")
            elif etype == 'trigger':
                lines.append(f"    {src_id} ==> {dst_id}")

        lines.append("```")
        return '\n'.join(lines)
