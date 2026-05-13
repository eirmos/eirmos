"""Text/tree formatter."""

from ..colors import Colors
from ..parsers.gitlab import GitLabCIParser
from ..parsers.github import GitHubActionsParser
from .base import BaseFormatter


class TreeFormatter(BaseFormatter):
    """Outputs a text-based tree visualization."""

    def render(self, filter_stage=None, filter_job=None):
        lines = []
        lines.append(f"\n{Colors.BOLD}{'═' * 80}{Colors.RESET}")
        if isinstance(self.parser, GitLabCIParser):
            ci_name = "GitLab CI"
        elif isinstance(self.parser, GitHubActionsParser):
            ci_name = "GitHub Actions"
        else:
            ci_name = getattr(self.parser, 'workflow_name', 'CI/CD')
        lines.append(f"{Colors.BOLD}  {ci_name} Visualization{Colors.RESET}")
        lines.append(f"{Colors.BOLD}{'═' * 80}{Colors.RESET}\n")

        lines.append(f"  {Colors.CYAN}Files parsed:{Colors.RESET} {len(self.parser.parsed_files)}")
        lines.append(f"  {Colors.CYAN}Jobs found:{Colors.RESET}   {len(self.parser.jobs)}")
        if getattr(self.parser, 'templates', None) is not None:
            lines.append(f"  {Colors.CYAN}Templates:{Colors.RESET}    {len(self.parser.templates)}")
        lines.append(f"  {Colors.CYAN}Stages:{Colors.RESET}       {len(self.graph.get_ordered_stages())}")
        lines.append(f"  {Colors.CYAN}Edges:{Colors.RESET}        {len(self.graph.edges)}")
        lines.append("")

        if filter_job:
            lines.extend(self._render_job_detail(filter_job))
        else:
            lines.extend(self._render_stages(filter_stage))

        return '\n'.join(lines)

    def _render_stages(self, filter_stage=None):
        lines = []
        stages = self.graph.get_ordered_stages()

        for i, stage in enumerate(stages):
            if filter_stage and stage != filter_stage:
                continue

            jobs = self.graph.stage_jobs.get(stage, [])
            if not jobs:
                continue

            is_last_stage = (i == len(stages) - 1)
            connector = '└' if is_last_stage else '├'
            lines.append(
                f"  {connector}── {Colors.BOLD}{Colors.BLUE}Stage: {stage}{Colors.RESET} "
                f"({len(jobs)} jobs)"
            )

            prefix = '   ' if is_last_stage else '  │'
            for j, job_name in enumerate(sorted(jobs)):
                is_last_job = (j == len(jobs) - 1)
                job_connector = '└' if is_last_job else '├'

                needs = self.parser.get_job_needs(job_name)
                trigger = self.parser.get_job_triggers(job_name)
                rules_summary = self.parser.get_job_rules_summary(job_name)

                job_color = Colors.GREEN
                if trigger:
                    job_color = Colors.YELLOW
                elif needs:
                    job_color = Colors.CYAN

                job_line = f"{prefix}  {job_connector}── {job_color}{job_name}{Colors.RESET}"
                if trigger:
                    job_line += f" {Colors.YELLOW}⟶ trigger{Colors.RESET}"
                if rules_summary:
                    job_line += f" {Colors.DIM}[{rules_summary}]{Colors.RESET}"

                lines.append(job_line)

                inner_prefix = f"{prefix}  {'   ' if is_last_job else '│  '}"
                for need in needs:
                    need_job = need.get('job', need.get('pipeline', '?'))
                    optional = ' (optional)' if need.get('optional') else ''
                    lines.append(
                        f"{inner_prefix}  {Colors.DIM}← needs: "
                        f"{need_job}{optional}{Colors.RESET}"
                    )

            lines.append(f"{prefix}")

        return lines

    def _render_job_detail(self, job_name):
        lines = []

        templates = getattr(self.parser, 'templates', {}) or {}
        if job_name not in self.parser.jobs and job_name not in templates:
            lines.append(f"  {Colors.RED}Job '{job_name}' not found.{Colors.RESET}")
            all_names = list(self.parser.jobs.keys()) + list(templates.keys())
            matches = [n for n in all_names if job_name.lower() in n.lower()]
            if matches:
                lines.append(f"\n  Did you mean:")
                for m in matches[:10]:
                    lines.append(f"    - {m}")
            return lines

        lines.append(f"  {Colors.BOLD}Job: {job_name}{Colors.RESET}\n")

        stage = self.parser.get_job_stage(job_name)
        source = self.parser.file_map.get(job_name, 'unknown')
        lines.append(f"  {Colors.CYAN}Stage:{Colors.RESET}    {stage}")
        lines.append(f"  {Colors.CYAN}Source:{Colors.RESET}   {source}")

        variables = self.parser.get_job_variables(job_name)
        if variables:
            lines.append(f"\n  {Colors.BOLD}Variables:{Colors.RESET}")
            for var_name, var_value in sorted(variables.items()):
                value_str = str(var_value)
                if len(value_str) > 60:
                    value_str = value_str[:57] + "..."
                lines.append(f"    {Colors.CYAN}{var_name}:{Colors.RESET} {value_str}")

        extends = self.parser.get_job_extends(job_name)
        if extends:
            lines.append(f"  {Colors.CYAN}Extends:{Colors.RESET}  {', '.join(extends)}")

        rules_summary = self.parser.get_job_rules_summary(job_name)
        if rules_summary:
            lines.append(f"  {Colors.CYAN}Triggers:{Colors.RESET} {rules_summary}")

        lines.append(f"\n  {Colors.BOLD}Dependencies (needs):{Colors.RESET}")
        preds = self.graph.get_predecessors(job_name)
        if preds:
            for pred, etype in preds:
                opt = ' (optional)' if etype == 'needs-optional' else ''
                lines.append(f"    ← {Colors.GREEN}{pred}{Colors.RESET}{opt}")
        else:
            lines.append(f"    {Colors.DIM}(none){Colors.RESET}")

        lines.append(f"\n  {Colors.BOLD}Dependents (needed by):{Colors.RESET}")
        succs = self.graph.get_successors(job_name)
        if succs:
            for succ, etype in succs:
                opt = ' (optional)' if etype == 'needs-optional' else ''
                lines.append(f"    → {Colors.YELLOW}{succ}{Colors.RESET}{opt}")
        else:
            lines.append(f"    {Colors.DIM}(none){Colors.RESET}")

        trigger = self.parser.get_job_triggers(job_name)
        if trigger:
            lines.append(f"\n  {Colors.BOLD}Triggers child pipeline:{Colors.RESET}")
            lines.append(f"    ⟶ {Colors.YELLOW}{trigger.get('include', trigger)}{Colors.RESET}")

        return lines

    @property
    def file_map(self):
        return self.parser.file_map
