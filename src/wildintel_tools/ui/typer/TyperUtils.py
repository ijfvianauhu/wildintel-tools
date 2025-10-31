import os
from pathlib import Path
from typing import List, Dict, Any, Callable, Text

import yaml
from rich import box
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from wildintel_tools.ui.typer.i18n import _

import logging
import typer
from rich.console import Console
from rich.table import Table

from rich.progress import Progress, TextColumn, BarColumn, TimeElapsedColumn
from typing import Callable, Dict, Any


class HierarchicalProgress:
    def __init__(self, console: Console = None):
        self.console = console or Console()
        self.progress = Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            "[progress.percentage]{task.percentage:>3.0f}%",
            TimeElapsedColumn(),
            console=self.console,  # 👈 Se la pasamos aquí
        )
        self._task_tree: Dict[str, Dict[str, Any]] = {}

    def __enter__(self):
        self.progress.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.progress.__exit__(exc_type, exc_value, traceback)

    def start_parent(self, parent_id: str, description: str, total: int):
        self._task_tree[parent_id] = {
            "task_id": self.progress.add_task(description, total=total),
            "children": {},
        }

    def start_child(self, parent_id: str, child_id: str, description: str, total: int):
        parent = self._task_tree.get(parent_id)
        if not parent:
            raise ValueError(f"Parent '{parent_id}' no existe")

        parent["children"][child_id] = self.progress.add_task(f"  {description}", total=total)

    def advance(self, parent_id: str, child_id: str, advance: int = 1):
        child_task = self._task_tree[parent_id]["children"][child_id]
        self.progress.advance(child_task, advance)

    def complete_child(self, parent_id: str):
        parent_task = self._task_tree[parent_id]["task_id"]
        self.progress.advance(parent_task, 1)


class TyperUtils:
    console = Console()
    logger = logging.getLogger(__name__)
    home = os.path.expanduser("~")


    @staticmethod
    def info(message: str):
        TyperUtils.console.print(f"[blue]:information:[/blue] {message}")
        TyperUtils.logger.info(message)

    @staticmethod
    def warning(message: str):
        TyperUtils.console.print(f"[orange]:warning:[/orange] {message}")
        TyperUtils.logger.warning(message)

    @staticmethod
    def error(message: str):
        TyperUtils.console.print(f"[red]:cross_mark:[/red] {message}")
        TyperUtils.logger.error(message)

    @staticmethod
    def fatal(message: str):
        TyperUtils.console.print(f"[red]:skull:[/red] {message}")
        TyperUtils.logger.critical(message)
        raise typer.Exit(code=1)

    @staticmethod
    def success(message: str):
        TyperUtils.console.print(f"[green]:white_check_mark:[/green] {message}")
        TyperUtils.logger.info(message)

    @staticmethod
    def run_tasks_with_progress(tasks: List[Dict[str, Any]]):
        results = []

        with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                TimeElapsedColumn(),
        ) as progress:

            task_ids: Dict[str, int] = {}
            for t in tasks:
                desc = t.get("description", "Unnamed task")
                task_ids[desc] = progress.add_task(desc, total=1)

            for t in tasks:
                desc = t.get("description", "Unnamed task")
                func: Callable = t["func"]
                args = t.get("args", ())
                kwargs = t.get("kwargs", {})

                progress.update(task_ids[desc], description=f"[cyan]{desc}[/cyan] (running)")
                try:
                    result = func(*args, **kwargs)
                    results.append(result)
                    progress.update(task_ids[desc], advance=1, description=f"[green]{desc}[/green] (done)")
                except Exception as e:
                    progress.update(task_ids[desc], description=f"[red]{desc}[/red] (failed)")
                    TyperUtils.error(f"Error in task '{desc}': {e}")
                    raise

        return results

    @staticmethod
    def show_table(data:List[dict], title, fields:List[str]=None):
        """
        Muestra una lista de diccionarios en una tabla de rich.

        - data: lista de dicts
        - campos: lista de claves a mostrar (si None, muestra todas)
        """

        console = Console()

        if not data:
            TyperUtils.warning(_("Nothing to show."))
            return

        all_fields = sorted({k for d in data for k in d.keys()})

        if fields is None:
            fields = all_fields

        table = Table(title= title, show_header=True, header_style="bold cyan")
        for campo in fields:
            table.add_column(campo)

        for d in data:
            row = [str(d.get(campo, "")) for campo in fields]
            table.add_row(*row)

        TyperUtils.console.print(table)

        restantes = [c for c in all_fields if c not in fields]

        if restantes:
            TyperUtils.info(_(f"Available fields:{', '.join(all_fields)}"))

    @staticmethod
    def get_default_report_dir():
        return Path(TyperUtils.home) / ("reports")

    @staticmethod
    def print_reports_in_directory(results_dir: Path):
        """
        List all YAML upload reports saved in the default upload reports directory.
        Shows filename, report title, start/end time, and status.
        """

        yaml_files = sorted(
            [p for p in results_dir.glob("*.yaml") if not p.name.startswith(".")],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        if not yaml_files:
            TyperUtils.fatal(f"No upload reports found in{results_dir}")

        table = Table(
            title=f"📊 Reports in {str(results_dir)}",
            box=box.SIMPLE_HEAVY,
            header_style="bold cyan",
        )
        table.add_column("File name", style="cyan", no_wrap=True)
        table.add_column("Title", style="green")
        table.add_column("Start time", style="magenta")
        table.add_column("End time", style="white")
        table.add_column("Status", style="bold")

        for yaml_file in yaml_files:
            try:
                with open(yaml_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)

                title = data.get("title", "—")
                start_time = data.get("start_time", "—")
                end_time = data.get("end_time", "—")

                # Determinar estado
                errors = data.get("errors", {})
                successes = data.get("successes", {})

                has_errors = bool(errors)
                has_successes = bool(successes)

                if has_successes and not has_errors:
                    status = "[green]SUCCESS[/green]"
                elif has_errors and not has_successes:
                    status = "[red]FAILED[/red]"
                elif has_errors and has_successes:
                    status = "[yellow]PARTIAL[/yellow]"
                else:
                    status = "[bright_black]EMPTY[/bright_black]"

            except Exception as e:
                title = "⚠️ Error loading"
                start_time = end_time = "—"
                status = f"[red]{str(e)}[/red]"

            table.add_row(yaml_file.name, title, str(start_time), str(end_time), status)

        TyperUtils.console.print(table)

    @staticmethod
    def display_report(report: "Report", raw: bool = False) -> None:
        """
        Displays a formatted summary of the Report instance in the console using Rich.
        """

        if raw:
            # Mostrar el YAML tabulado
            if isinstance(report, Path):
                # Si se pasa la ruta, cargar el YAML
                with open(report, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
            else:
                # Convertir la instancia Report a diccionario
                from dataclasses import asdict
                data = asdict(report)

            yaml_str = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
            TyperUtils.console.print(yaml_str)
            return

        title = Text(f"📊 Report: {report.title}", style="bold cyan")
        TyperUtils.console.rule(title)

        time_panel = Panel.fit(
            f"Start: [green]{report.start_time}[/green]\n"
            f"End:   [green]{report.end_time or 'in progress'}[/green]",
            title="🕒 Timestamps",
            border_style="cyan"
        )
        TyperUtils.console.print(time_panel)

        total_errors = sum(len(v) for v in report.errors.values())
        total_successes = sum(len(v) for v in report.successes.values())

        stats = {
            "Total successes": total_successes,
            "Total errors": total_errors,
            "Unique identifiers": len(set(report.errors.keys()) | set(report.successes.keys())),
            "Unique actions": len(report.get_actions()),
            "Status": report.get_status(),
        }

        table = Table(box=box.SIMPLE_HEAVY)
        table.add_column("Metric", style="bold yellow")
        table.add_column("Value", justify="right", style="bold white")

        for key, value in stats.items():
            style = "green" if key == "Status" and value == "success" else "red" if key == "Status" and value == "failed" else "white"
            table.add_row(key, f"[{style}]{value}[/{style}]")

        TyperUtils.console.print(table)

        actions = report.get_actions()
        if actions:
            action_table = Table(box=box.SIMPLE)
            action_table.add_column("Action", style="bold magenta")
            action_table.add_column("Successes", justify="right", style="green")
            action_table.add_column("Errors", justify="right", style="red")

            for action in actions:
                action_data = report.get_by_action(action)
                success_count = sum(len(v) for v in action_data["successes"].values())
                error_count = sum(len(v) for v in action_data["errors"].values())
                action_table.add_row(action, str(success_count), str(error_count))

            TyperUtils.console.print(Panel.fit(action_table, title="⚙️ Actions Overview", border_style="magenta"))

        TyperUtils.console.rule(f"[bold cyan]Report Status: [white]{report.get_status().upper()}[/white]")


