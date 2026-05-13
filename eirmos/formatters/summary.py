"""Compact summary formatter."""

import re
from collections import defaultdict

from ..colors import Colors
from .base import BaseFormatter


class SummaryFormatter(BaseFormatter):
    """Outputs a compact summary view."""

    def render(self, filter_stage=None, filter_job=None):
        lines = []
        lines.append(f"\n{Colors.BOLD}Pipeline Summary{Colors.RESET}")
        lines.append(f"{'─' * 60}")

        templates = getattr(self.parser, 'templates', {}) or {}

        lines.append(f"\n{Colors.BOLD}Statistics:{Colors.RESET}")
        lines.append(f"  Total jobs:      {len(self.parser.jobs)}")
        lines.append(f"  Total templates: {len(templates)}")
        lines.append(f"  Total stages:    {len(self.graph.get_ordered_stages())}")
        lines.append(f"  Total edges:     {len(self.graph.edges)}")
        lines.append(f"  Files parsed:    {len(self.parser.parsed_files)}")

        lines.append(f"\n{Colors.BOLD}Stages:{Colors.RESET}")
        for stage in self.graph.get_ordered_stages():
            jobs = self.graph.stage_jobs.get(stage, [])
            bar = '█' * min(len(jobs), 40)
            lines.append(f"  {stage:<20} {Colors.BLUE}{bar}{Colors.RESET} ({len(jobs)})")

        lines.append(f"\n{Colors.BOLD}Most Connected Jobs (by needs):{Colors.RESET}")
        job_deps = {}
        for job_name in self.parser.jobs:
            needs = self.parser.get_job_needs(job_name)
            succs = self.graph.get_successors(job_name)
            job_deps[job_name] = len(needs) + len(succs)

        top_jobs = sorted(job_deps.items(), key=lambda x: x[1], reverse=True)[:15]
        for job_name, count in top_jobs:
            if count > 0:
                lines.append(f"  {job_name:<55} {Colors.GREEN}{count}{Colors.RESET}")

        trigger_jobs = [j for j in self.parser.jobs if self.parser.get_job_triggers(j)]
        if trigger_jobs:
            lines.append(f"\n{Colors.BOLD}Child Pipeline Triggers:{Colors.RESET}")
            for job_name in sorted(trigger_jobs):
                trigger = self.parser.get_job_triggers(job_name)
                inc = trigger.get('include', 'unknown')
                lines.append(f"  {Colors.YELLOW}{job_name}{Colors.RESET}")
                lines.append(f"    ⟶ {inc}")

        roots = self.graph.get_roots()
        if roots:
            lines.append(f"\n{Colors.BOLD}Root Jobs (no 'needs' dependencies):{Colors.RESET}")
            for job_name in sorted(roots)[:20]:
                stage = self.parser.get_job_stage(job_name)
                lines.append(f"  {job_name:<50} {Colors.DIM}[{stage}]{Colors.RESET}")
            if len(roots) > 20:
                lines.append(f"  ... and {len(roots) - 20} more")

        # CUSTOM_BUILD options mapping (GitLab CI specific)
        lines.append(f"\n{Colors.BOLD}CUSTOM_BUILD → Job Mapping:{Colors.RESET}")
        custom_build_map = defaultdict(list)
        for job_name, job in self.parser.jobs.items():
            for rule in job.get('rules', []) or []:
                if isinstance(rule, dict) and 'if' in rule:
                    matches = re.findall(r'CUSTOM_BUILD\s*==\s*"([^"]+)"', str(rule['if']))
                    for m in matches:
                        custom_build_map[m].append(job_name)

        for cb_name in sorted(custom_build_map.keys()):
            jobs = custom_build_map[cb_name]
            lines.append(f"\n  {Colors.CYAN}{cb_name}{Colors.RESET}:")
            for j in sorted(set(jobs)):
                lines.append(f"    → {j}")

        return '\n'.join(lines)
