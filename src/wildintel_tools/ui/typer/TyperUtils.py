from typing import List, Dict, Any, Callable

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




