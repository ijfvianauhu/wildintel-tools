import json
import os
import sys
import re
from pathlib import Path
from typing import List, Dict, Any, Callable, Text, Tuple, Optional
import uuid
from datetime import datetime
import yaml
from docutils.nodes import status
from pydantic import BaseModel, ValidationError
from rich import box
from rich.panel import Panel
from rich.prompt import Prompt
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from typer_config import conf_callback_factory

from wildintel_tools.ui.typer.i18n import _

import typer
from rich.console import Console
from rich.table import Table

from rich.progress import Progress, TextColumn, BarColumn, TimeElapsedColumn
from typing import Callable, Dict, Any

from wildintel_tools.ui.typer.settings import Settings, SettingsManager

import logging

logger = logging.getLogger(__name__)

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
    _stdin_cache: Optional[str] = None


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
        TyperUtils.logger.error(message, exc_info=True)

    @staticmethod
    def fatal(message: str):
        TyperUtils.console.print(f"[red]:skull:[/red] {message}")
        TyperUtils.logger.critical(message, exc_info=True)
        raise typer.Exit(code=1)

    @staticmethod
    def debug(message: str):
        if TyperUtils.logger.isEnabledFor(logging.DEBUG):
            TyperUtils.console.print(f"🐞 {message}")
        TyperUtils.logger.info(message)

    @staticmethod
    def success(message: str):
        TyperUtils.console.print(f"[green]:white_check_mark:[/green] {message}")
        TyperUtils.logger.info(message)

    #
    # Config methods
    #

    @staticmethod
    def generate_pydantic_mapping(model: BaseModel, overrides: Dict[str, Tuple[str, str]] | None = None) -> Dict[str, Tuple[str, str]]:
        """
        Generate a mapping {param_name: (section, key)} from a Pydantic model,
        recursively including nested models.

        :param model: Pydantic model instance
        :param prefix: Prefix for nested fields
        :param overrides: Optional dict to override or add mapping
        :return: Mapping dictionary
        """
        mapping = {}

        for section_name, section_field in model.model_fields.items():
            value = getattr(model, section_name)

            if isinstance(value, BaseModel):
                for field_name in value.model_fields.keys():
                    mapping[field_name] = (section_name, field_name)
            else:
                # Campos directos en Settings (si hubiera)
                mapping[section_name] = (section_name, section_name)

        if overrides:
            mapping.update(overrides)

        return mapping


    # 🔹 Loader que recibe la ruta completa del archivo
    @staticmethod
    def dynaconf_loader(file_path: str) -> dict:
        """
        Load a Dynaconf-compatible configuration from a JSON string.

        Note:
            Although its name suggests a path loader, this function expects a JSON
            string and returns a Python ``dict`` usable by ``typer_config`` and Dynaconf.

        :param file_path: JSON string containing the configuration.
        :type file_path: str
        :returns: Parsed configuration dictionary.
        :rtype: dict
        :raises json.JSONDecodeError: If the input is not valid JSON.
        """

        try:
            return json.loads(file_path)
        except Exception as e:
            pass  # Not JSON → try as file path

        #path = Path(file_path + ".toml")
        path = Path(file_path)
        #if path.exists() and path.is_file():
        logger.debug(f"Loading configuration from {path}")
        settings_dir = path.parent
        setting_manager = SettingsManager(settings_dir=settings_dir)
        settings = setting_manager.load_settings(path.name, True, True)
        return SettingsManager.to_plain_dict(settings)

        # If path does not exist or is not a file → raise
        #raise FileNotFoundError(f"Path does not exist or is not a file: {file_path}")

    # 🔹 Callback base
    base_conf_callback = conf_callback_factory(dynaconf_loader)

    # 🔹 Callback dinámico que usa otro parámetro (base_path)
    @staticmethod
    def dynamic_dynaconf_callback(
        ctx,
        param: typer.CallbackParam,
        value: Any,
        override_mapping: dict | None = None,
    ):
        """
        Dynamic callback that injects runtime defaults into Typer parameters.

        Serializes the runtime settings from ``ctx.obj["settings"]`` and delegates
        loading to the base configuration callback. It also fills CLI parameters
        when omitted by the user, using project settings.

        :param ctx: Typer/Click context.
        :type ctx: typer.Context
        :param param: Parameter associated with the callback.
        :type param: click.Parameter
        :param value: Current value of the processed parameter.
        :type value: Any
        :returns: Result of the underlying base configuration callback.
        :rtype: Any
        """

        # Load Settings

        if ctx.obj and "settings" in ctx.obj and ctx.obj["settings"] is not None:
            # Use settings from context
            settings_dict = SettingsManager.to_plain_dict(ctx.obj["settings"])
            value = json.dumps(settings_dict, default=str)
            TyperUtils.base_conf_callback(ctx, param, value)
        # if value is not None:
        #    print("por value")
        # Use the raw value (expected to be a Path)
        #    settings_dict= base_conf_callback(ctx, param, Path(value))
        else:
            base_path = ctx.params.get("settings_dir", ".")
            file_path = os.path.join(base_path, ctx.params.get("project", "default"))
            TyperUtils.base_conf_callback(ctx, param, file_path)

        # en ctx.default_map tengo las settings leídas por base_conf_callback
        settings = ctx.default_map.copy() if ctx.default_map else {}
        settings_model = Settings(**settings)

        # Guardo las settings si aún no están en ctx.obj
        if not ctx.obj:
            ctx.obj =  dict()

        if  "settings" not in ctx.obj:
            ctx.obj["settings"] = settings_model

        # A los parámetros les asigno los valores por defecto definidos en las settings si ya no tienen un valor
        # asignado

        mapping = TyperUtils.generate_pydantic_mapping(settings_model, override_mapping)

        for param_name in ctx.params:
            if ctx.params[param_name] is None and param_name in mapping:
                section, key = mapping[param_name]
                ctx.params[param_name] = settings[section][key]

        return value

    #
    #
    #

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
    def save_report(report, file_name=None):
        results_dir = TyperUtils.get_default_report_dir()
        results_dir.mkdir(parents=True, exist_ok=True)
        if file_name is None:
            unique_id = uuid.uuid4().hex[:8]
            file_name = f"report_{unique_id}_{datetime.now():%Y%m%d_%H%M%S}.yaml"
        report_file = results_dir / file_name
        report.to_yaml(report_file)
        return report_file

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

        title = Text(f"📊 Report: {report.title}")
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

    @staticmethod
    def _read_stdin_once() -> str:
        """Read stdin once and cache it (used for '-' inputs)."""
        if TyperUtils._stdin_cache is None:
            TyperUtils._stdin_cache = sys.stdin.read()
        return TyperUtils._stdin_cache

    @staticmethod
    def parse_id_list(value: Optional[str], allow_stdin: bool = True, param_name: str = "value") -> Optional[list[int]]:
        """
        Parse a comma/space separated list of integers. If value is '-' and allow_stdin=True,
        read from stdin (cached). Returns None for empty input.
        """
        if value is None:
            return None
        raw = value.strip()
        if raw == "-":
            if not allow_stdin:
                raise typer.BadParameter(f"{param_name} does not accept stdin marker '-'")
            raw = TyperUtils._read_stdin_once().strip()
        if not raw:
            return None
        tokens = re.split(r"[\s,]+", raw)
        ids: list[int] = []
        for token in tokens:
            if not token:
                continue
            try:
                ids.append(int(token))
            except ValueError as exc:
                raise typer.BadParameter(f"Invalid {param_name} '{token}'. Expected integers separated by comma or space.") from exc
        return ids or None

    @staticmethod
    def parse_query_params(pairs: Optional[List[str]]) -> dict:
        """Convert a list of "key=value" strings into a dictionary."""
        out: dict = {}
        for pair in pairs or []:
            if "=" not in pair:
                raise ValueError(f"Invalid query param '{pair}', expected key=value")
            k, v = pair.split("=", 1)
            out[k.strip()] = v.strip()
        return out

    def prompt_with_default(
            prompt_msg: str,
            default: str | None,
            model_cls: type,
            field_name: str,
            show_default: bool = True
    ):
        """
        Prompt the user, showing a default value optionally.
        If Enter is pressed, keep default. Validates input using Pydantic.

        :param prompt_msg: Message to show to the user.
        :param default: Default value to keep if Enter is pressed.
        :param model_cls: Pydantic model class for validation.
        :param field_name: Field name in the model to validate.
        :param show_default: If True, shows the default value in the prompt; if False, hides it.
        """
        while True:
            if default and show_default:
                value = typer.prompt(f"{prompt_msg} [{default}]", default=default, show_default=False)
            elif default:
                # Default exists but we hide it
                value = typer.prompt(prompt_msg, default=default, show_default=False)
            else:
                value = typer.prompt(prompt_msg)

            try:
                # Validar usando Pydantic
                model_cls(**{field_name: value})
                return value
            except ValidationError as e:
                typer.echo(f"Invalid input: {e.errors()[0]['msg']}. Please try again.")

    @staticmethod
    def select_from_list(
            items: List[Any],
            title: str = "Select an item",
            show_id: bool = True,
            show_name: bool = True,
            success_msg: str = "Selected item",
            id_attr: str = "pk",
            name_attr: str = "name",
            prompt_msg: str = "Enter the index of the item you want to select",
            multi_select: bool = False
    ) -> Any:
        """
        Allows the user to select an item from a list. If only one item exists, it is automatically selected.
        Otherwise, a table is displayed and the user is prompted to choose.

        Parameters
        ----------
        items : List[Any]
            List of objects to select from. Objects must have 'id' and 'name' attributes if show_id or show_name are True.
        title : str, optional
            Title of the selection table.
        show_id : bool, optional
            Whether to show the 'ID' column in the table.
        show_name : bool, optional
            Whether to show the 'Name' column in the table.
        success_msg : str, optional
            Message displayed when a single item is automatically selected.

        Returns
        -------
        Any
            The selected item from the list.
        """
        if not items:
            return None

        if len(items) == 1:
            TyperUtils.success(f"{success_msg}: {items[0].name}")
            return items[0], 0

        # Crear tabla
        table = Table(title=title, show_lines=True)
        table.add_column("Index", justify="right", style="cyan", no_wrap=True)
        if show_id:
            table.add_column("ID", justify="right", style="yellow")
        if show_name:
            table.add_column("Name", style="green")

        for i, item in enumerate(items, start=1):
            row = [str(i)]
            if show_id:
                row.append(str(getattr(item, id_attr)))
            if show_name:
                row.append(str(getattr(item, name_attr)))
            table.add_row(*row)
        TyperUtils.console.print(table)

        if multi_select:
            prompt_msg = f"{prompt_msg} (e.g. 1,3,5 or 2-6)"
        else:
            prompt_msg = f"{prompt_msg} (choose one number)"

        choice = Prompt.ask(prompt_msg)

        def parse_selection(choice_str: str) -> List[int]:
            result = set()

            parts = choice_str.strip().split(",")
            for part in parts:
                part = part.strip()

                if "-" in part:
                    start, end = part.split("-")
                    result.update(range(int(start), int(end) + 1))
                else:
                    try:
                        value = int(part)
                    except ValueError:
                        continue
                    result.add(value)

            # Filtrar índices válidos
            return [i for i in sorted(result) if 1 <= i <= len(items)]

        indices = parse_selection(choice)

        if not indices:
            TyperUtils.error("Invalid selection.")
            return None

        if not multi_select:
            return items[indices[0] - 1], indices[0] - 1

        return [items[i - 1] for i in indices],  [i-1 for i in indices]

        # Pedir al usuario que elija
        """choice = Prompt.ask(
            prompt_msg,
            choices=[str(i) for i in range(1, len(items) + 1)],
            show_choices=False
        )
        
        return items[int(choice) - 1], int(choice) - 1"""

