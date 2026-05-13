"""Variable analysis formatter."""

from collections import defaultdict

from ..colors import Colors
from .base import BaseFormatter


class VariableFormatter(BaseFormatter):
    """Outputs variable analysis."""

    def render(self, filter_stage=None, filter_job=None):
        lines = []
        lines.append(f"\n{Colors.BOLD}Variable Analysis{Colors.RESET}")
        lines.append(f"{'─' * 60}")

        global_vars = self.parser.get_global_variables()
        lines.append(f"\n{Colors.BOLD}Global Variables ({len(global_vars)}):{Colors.RESET}")
        for var_name, var_value in sorted(global_vars.items()):
            lines.append(f"  {Colors.CYAN}{var_name}:{Colors.RESET}")
            lines.append(f"    {Colors.DIM}{var_value}{Colors.RESET}")

        lines.append(f"\n{Colors.BOLD}Variables by Job:{Colors.RESET}")
        templates = getattr(self.parser, 'templates', {}) or {}
        for job_name in sorted(self.parser.jobs.keys()):
            if filter_job and filter_job != job_name:
                continue
            stage = self.parser.get_job_stage(job_name)
            if filter_stage and filter_stage != stage:
                continue

            variables = self.parser.get_job_variables(job_name)
            if not variables:
                continue

            lines.append(f"\n  {Colors.BOLD}{job_name}{Colors.RESET} {Colors.DIM}[{stage}]{Colors.RESET}")
            for var_name, var_value in sorted(variables.items()):
                inherited = ""
                for ext in self.parser.get_job_extends(job_name):
                    ext_job = templates.get(ext)
                    if ext_job and var_name in ext_job.get('variables', {}):
                        inherited = f" {Colors.DIM}(from {ext}){Colors.RESET}"
                        break

                value_str = str(var_value)
                if len(value_str) > 50:
                    value_str = value_str[:47] + "..."

                lines.append(f"    {Colors.CYAN}{var_name}:{Colors.RESET} {value_str}{inherited}")

        lines.append(f"\n{Colors.BOLD}Variable Usage Matrix:{Colors.RESET}")
        var_jobs = defaultdict(list)
        for job_name in self.parser.jobs:
            for var_name in self.parser.get_job_variables(job_name).keys():
                var_jobs[var_name].append(job_name)

        for var_name in sorted(var_jobs.keys()):
            jobs = var_jobs[var_name]
            lines.append(f"\n  {Colors.CYAN}{var_name}{Colors.RESET} ({len(jobs)} jobs):")
            for job in sorted(jobs)[:10]:
                lines.append(f"    - {job}")
            if len(jobs) > 10:
                lines.append(f"    {Colors.DIM}... and {len(jobs) - 10} more{Colors.RESET}")

        return '\n'.join(lines)
