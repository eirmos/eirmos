"""Interactive TUI for eirmos — explore CI/CD pipeline graphs in the terminal.

Powered by Textual.  Launch with ``eirmos-tui [path]``.
"""

from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    Static,
    Tree,
)

from .graph import DependencyGraph
from .parsers import detect as detect_adapter, REGISTRY

# ──────────────────────────────────────────────────────────────────
# Rich markup colours used inside Tree labels (Tree uses Rich, not
# Textual markup — so $variables don't work here).
# ──────────────────────────────────────────────────────────────────
RICH_GREEN = "green"
RICH_YELLOW = "yellow"
RICH_BLUE = "blue"
RICH_RED = "red"
RICH_DIM = "dim"
RICH_BOLD = "bold"


class PathScreen(Screen):
    """Initial screen: enter a repository path to analyse."""

    CSS = """
    PathScreen {
        align: center middle;
    }

    #path-dialog {
        width: 54;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }

    #path-dialog Label {
        width: 100%;
        text-align: center;
        margin-bottom: 1;
    }

    #path-input {
        margin-bottom: 1;
    }

    #path-buttons {
        width: 100%;
        align-horizontal: center;
    }

    #path-buttons Button {
        margin: 0 1;
    }

    #error-label {
        color: $error;
        text-align: center;
        margin-top: 1;
        height: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "quit", "Quit"),
    ]

    def __init__(self, initial_path: str = "."):
        super().__init__()
        self._initial_path = initial_path

    def compose(self) -> ComposeResult:
        with Vertical(id="path-dialog"):
            yield Label("[bold]eirmos[/bold] — CI/CD Pipeline Visualiser")
            yield Label("Enter repository path to analyse:")
            yield Input(value=self._initial_path, id="path-input", placeholder="/path/to/repo")
            with Horizontal(id="path-buttons"):
                yield Button("Analyse", variant="primary", id="btn-analyse")
                yield Button("Quit", variant="error", id="btn-quit")
            yield Label("", id="error-label")

    def on_mount(self) -> None:
        self.query_one("#path-input", Input).focus()

    @on(Input.Submitted, "#path-input")
    @on(Button.Pressed, "#btn-analyse")
    def handle_analyse(self) -> None:
        path_str = self.query_one("#path-input", Input).value.strip()
        if not path_str:
            self._show_error("Path cannot be empty.")
            return

        base_path = Path(path_str).expanduser().resolve()
        if not base_path.exists():
            self._show_error(f"Path does not exist: {base_path}")
            return

        adapter, main_file = detect_adapter(base_path)
        if adapter is None:
            supported = ", ".join(a.name for a in REGISTRY)
            self._show_error(f"No supported CI files found ({supported}).")
            return

        try:
            parser = adapter.parser_class(base_path=base_path)
            parser.parse(main_file)
            graph = DependencyGraph(parser)
        except Exception as exc:
            self._show_error(f"Parse error: {exc}")
            return

        self.app.push_screen(
            MainScreen(
                parser=parser,
                graph=graph,
                adapter=adapter,
                base_path=base_path,
                main_file=main_file,
            )
        )

    @on(Button.Pressed, "#btn-quit")
    def handle_quit(self) -> None:
        self.app.exit()

    def _show_error(self, message: str) -> None:
        self.query_one("#error-label", Label).update(message)


class MainScreen(Screen):
    """Main screen: interactive pipeline graph explorer."""

    CSS = """
    MainScreen > Vertical {
        height: 1fr;
    }

    MainScreen > Vertical > Horizontal {
        height: 1fr;
    }

    #sidebar {
        width: 40;
        border-right: solid $primary-background;
        background: $surface;
    }

    #sidebar-header {
        background: $panel;
        padding: 1;
        text-style: bold;
        color: $accent;
        height: auto;
    }

    #stats-box {
        padding: 0 1;
        height: auto;
    }

    #job-tree {
        overflow-y: auto;
    }

    Tree {
        padding: 1;
        scrollbar-size: 1 0;
    }

    #detail-panel {
        width: 1fr;
        background: $surface;
    }

    #detail-header {
        height: auto;
        content-align: center middle;
        background: $panel;
        color: $accent;
        text-style: bold;
        padding: 0 1;
    }

    #detail-body {
        padding: 0 1;
    }

    #detail-body Static {
        padding: 0 1;
    }

    #detail-body .kv-line {
        padding: 0 2;
        color: $text-muted;
    }

    #detail-body .section-title {
        color: $accent;
        text-style: bold;
        margin-top: 1;
        padding: 0 1;
    }

    #detail-body .no-data {
        color: $text-disabled;
        padding: 0 1;
    }

    #status-bar {
        height: 1;
        background: $panel;
        color: $text-muted;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "focus_tree", "Focus tree"),
        Binding("d", "focus_detail", "Focus detail"),
        Binding("s", "export_summary", "Summary"),
        Binding("m", "export_mermaid", "Mermaid"),
        Binding("escape", "go_back", "Back"),
    ]

    def __init__(
        self,
        parser,
        graph: DependencyGraph,
        adapter,
        base_path: Path,
        main_file: Path,
    ):
        super().__init__()
        self._parser = parser
        self._graph = graph
        self._adapter = adapter
        self._base_path = base_path
        self._main_file = main_file

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            with Horizontal():
                with Vertical(id="sidebar"):
                    yield Static(
                        f"[bold]eirmos[/bold] — {self._adapter.name}\n"
                        f"[dim]{self._base_path}[/dim]",
                        id="sidebar-header",
                    )

                    stages = self._graph.get_ordered_stages()
                    total_jobs = len(self._parser.jobs)
                    roots = self._graph.get_roots()
                    has_cycle = self._graph.has_cycle()

                    stats_text = (
                        f"[dim]Files:[/dim] {len(self._parser.parsed_files)}  "
                        f"[dim]Jobs:[/dim] {total_jobs}  "
                        f"[dim]Stages:[/dim] {len(stages)}\n"
                        f"[dim]Edges:[/dim] {len(self._graph.edges)}  "
                        f"[dim]Roots:[/dim] {len(roots)}"
                    )
                    if has_cycle:
                        stats_text += "\n[bold red]⚠ Cycle detected![/bold red]"
                    yield Static(stats_text, id="stats-box")

                    tree: Tree[str] = Tree("Jobs", id="job-tree")
                    tree.show_root = False
                    for stage in stages:
                        jobs = self._graph.stage_jobs.get(stage, [])
                        if not jobs:
                            continue
                        stage_node = tree.root.add(
                            f"[bold {RICH_BLUE}]▸ {stage}[/bold {RICH_BLUE}]",
                            expand=True,
                        )
                        stage_node.data = {"type": "stage", "stage": stage}
                        for job_name in sorted(jobs):
                            trigger = self._parser.get_job_triggers(job_name)
                            needs = self._parser.get_job_needs(job_name)
                            is_root = job_name in roots

                            if trigger:
                                label = f"[{RICH_YELLOW}]{job_name} ⚡[/{RICH_YELLOW}]"
                            elif is_root:
                                label = f"[{RICH_GREEN}]{job_name}[/{RICH_GREEN}]"
                            else:
                                label = job_name

                            job_node = stage_node.add_leaf(label)
                            job_node.data = {
                                "type": "job",
                                "name": job_name,
                                "stage": stage,
                            }

                            for need in needs:
                                need_job = need.get("job", need.get("pipeline", "?"))
                                optional = " (opt)" if need.get("optional") else ""
                                need_node = job_node.add_leaf(
                                    f"[{RICH_DIM}]← {need_job}{optional}[/{RICH_DIM}]"
                                )
                                need_node.data = {
                                    "type": "need",
                                    "name": need_job,
                                    "optional": need.get("optional", False),
                                }

                    yield tree

                with VerticalScroll(id="detail-panel"):
                    yield Static("Select a job to view details", id="detail-header")
                    yield VerticalScroll(Static(""), id="detail-body")

            yield Static("", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        tree = self.query_one("#job-tree", Tree)
        tree.focus()

        stages = self._graph.get_ordered_stages()
        total_jobs = len(self._parser.jobs)
        has_cycle = self._graph.has_cycle()
        cycle_msg = " ⚠ CYCLE" if has_cycle else ""
        self.query_one("#status-bar", Static).update(
            f"  {self._adapter.name} | {len(self._parser.parsed_files)} files"
            f" | {total_jobs} jobs | {len(stages)} stages"
            f" | {len(self._graph.edges)} edges{cycle_msg}"
            f" | q=quit  ↑↓=nav  Enter=details  s=summary  m=mermaid"
        )

    @on(Tree.NodeSelected, "#job-tree")
    def handle_node_selected(self, event: Tree.NodeSelected) -> None:
        self._show_detail(event.node.data or {})

    @on(Tree.NodeHighlighted, "#job-tree")
    def handle_node_highlighted(self, event: Tree.NodeHighlighted) -> None:
        self._show_detail(event.node.data or {})

    def _show_detail(self, data: dict) -> None:
        body = self.query_one("#detail-body", VerticalScroll)
        body.remove_children()

        node_type = data.get("type")
        if node_type == "job":
            self._render_job_detail(body, data["name"])
        elif node_type == "stage":
            self._render_stage_detail(body, data["stage"])
        elif node_type == "need":
            self._render_need_detail(body, data["name"])
        else:
            body.mount(Static("[dim]Select a job to view details[/dim]"))

    def _render_job_detail(self, container: VerticalScroll, job_name: str) -> None:
        stage = self._parser.get_job_stage(job_name)
        source = getattr(self._parser, "file_map", {}).get(job_name, "unknown")
        trigger = self._parser.get_job_triggers(job_name)
        extends = self._parser.get_job_extends(job_name)
        rules = self._parser.get_job_rules_summary(job_name)
        variables = self._parser.get_job_variables(job_name)

        header = self.query_one("#detail-header", Static)
        header.update(f"[bold]{job_name}[/bold]")

        container.mount(Static(f"[dim]Stage:[/dim]  {stage}"))
        container.mount(Static(f"[dim]Source:[/dim] {source}"))

        if extends:
            container.mount(Static(f"[dim]Extends:[/dim] {', '.join(extends)}"))
        if trigger:
            trigger_label = trigger.get("include") or trigger.get("project") or "pipeline"
            container.mount(Static(f"[dim]Trigger:[/dim] [bold yellow]{trigger_label}[/bold yellow]"))
        if rules:
            container.mount(Static(f"[dim]Rules:[/dim]   {rules}"))

        # Dependencies
        container.mount(Static("[bold]Dependencies (← needs)[/bold]", classes="section-title"))
        preds = self._graph.get_predecessors(job_name)
        if preds:
            for pred, etype in preds:
                opt = " (optional)" if etype == "needs-optional" else ""
                colour = "yellow" if etype == "needs-optional" else "green"
                line = f"  ← [{colour}]{pred}[/{colour}]{opt}"
                container.mount(Static(line))
        else:
            container.mount(Static("  [dim](none — root job)[/dim]", classes="no-data"))

        # Dependents
        container.mount(Static("[bold]Dependents (needed by →)[/bold]", classes="section-title"))
        succs = self._graph.get_successors(job_name)
        if succs:
            for succ, etype in succs:
                opt = " (optional)" if etype == "needs-optional" else ""
                container.mount(Static(f"  → [red]{succ}[/red]{opt}"))
        else:
            container.mount(Static("  [dim](none — leaf job)[/dim]", classes="no-data"))

        # Variables
        if variables:
            container.mount(Static("[bold]Variables[/bold]", classes="section-title"))
            for var_name, var_value in sorted(variables.items()):
                value_str = str(var_value)
                if len(value_str) > 80:
                    value_str = value_str[:77] + "..."
                container.mount(Static(f"  [bold blue]{var_name}[/bold blue]: {value_str}"))

    def _render_stage_detail(self, container: VerticalScroll, stage: str) -> None:
        jobs = self._graph.stage_jobs.get(stage, [])
        roots = self._graph.get_roots()

        header = self.query_one("#detail-header", Static)
        header.update(f"[bold]Stage: {stage}[/bold]")

        container.mount(Static(f"[dim]Jobs:[/dim] {len(jobs)}"))

        root_in_stage = [j for j in jobs if j in roots]
        if root_in_stage:
            container.mount(Static("[bold]Root jobs (no dependencies)[/bold]", classes="section-title"))
            for j in sorted(root_in_stage):
                container.mount(Static(f"  [green]{j}[/green]"))

        triggers_in_stage = [j for j in jobs if self._parser.get_job_triggers(j)]
        if triggers_in_stage:
            container.mount(Static("[bold]Trigger jobs[/bold]", classes="section-title"))
            for j in sorted(triggers_in_stage):
                container.mount(Static(f"  [yellow]{j} ⚡[/yellow]"))

        container.mount(Static("[bold]All jobs in stage[/bold]", classes="section-title"))
        for j in sorted(jobs):
            needs = self._parser.get_job_needs(j)
            dep_count = len(needs)
            container.mount(Static(f"  {j} [dim]({dep_count} deps)[/dim]"))

    def _render_need_detail(self, container: VerticalScroll, job_name: str) -> None:
        if job_name in self._parser.jobs:
            self._render_job_detail(container, job_name)
        else:
            header = self.query_one("#detail-header", Static)
            header.update(f"[dim]{job_name}[/dim]")
            container.mount(Static(f"[dim]{job_name}[/dim]"))
            container.mount(Static("[dim]Referenced but not defined in this pipeline.[/dim]"))

    def action_focus_tree(self) -> None:
        self.query_one("#job-tree", Tree).focus()

    def action_focus_detail(self) -> None:
        self.query_one("#detail-body", VerticalScroll).focus()

    def action_export_summary(self) -> None:
        from .formatters.summary import SummaryFormatter
        formatter = SummaryFormatter(self._parser, self._graph)
        output = formatter.render()
        body = self.query_one("#detail-body", VerticalScroll)
        body.remove_children()
        header = self.query_one("#detail-header", Static)
        header.update("[bold]Summary[/bold]")
        for line in output.split("\n"):
            body.mount(Static(line))

    def action_export_mermaid(self) -> None:
        from .formatters.mermaid import MermaidFormatter
        formatter = MermaidFormatter(self._parser, self._graph)
        output = formatter.render()
        body = self.query_one("#detail-body", VerticalScroll)
        body.remove_children()
        header = self.query_one("#detail-header", Static)
        header.update("[bold]Mermaid Diagram[/bold]")
        for line in output.split("\n"):
            body.mount(Static(line))

    def action_go_back(self) -> None:
        self.app.pop_screen()


class EirmosTUI(App):
    """The eirmos interactive terminal application."""

    TITLE = "eirmos"
    SUB_TITLE = "CI/CD Pipeline Visualiser"

    def __init__(self, path: str = "."):
        super().__init__()
        self._start_path = path

    def on_mount(self) -> None:
        self.push_screen(PathScreen(initial_path=self._start_path))


def run_tui(path: str = ".") -> None:
    """Entry point for the TUI."""
    app = EirmosTUI(path=path)
    app.run()


if __name__ == "__main__":  # pragma: no cover
    import sys
    run_tui(sys.argv[1] if len(sys.argv) > 1 else ".")
