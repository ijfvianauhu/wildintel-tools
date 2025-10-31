import datetime
import logging
import os
import time

from dynaconf import ValidationError
import typer
from rich.prompt import Confirm
from typing_extensions import Annotated
from typing import Optional
from pathlib import Path

from wildintel_tools.reports import Report
from wildintel_tools.ui.typer.i18n import _
from wildintel_tools.ui.typer.TyperUtils import TyperUtils
from wildintel_tools.ui.typer.settings import SettingsManager, SETTINGS_ORDER

app = typer.Typer(
    help=_("Manage project configurations"),
    short_help=_("Manage project configurations")
)

@app.callback()
def main_callback(ctx: typer.Context                  ):
    pass

@app.command(
    help=_("Show a list of generated reports"),
    short_help=_("Show a list of generated reports")
)
def list(
        ctx: typer.Context,
):
    settings_manager = ctx.obj.get("setting_manager")
    project_name = str(ctx.obj.get("project", "default"))
    logger = ctx.obj.get("logger", logging.getLogger(__name__))

    results_dir = TyperUtils.get_default_report_dir()
    TyperUtils.print_reports_in_directory(results_dir)

@app.command(help=_("Validate and show current project settings"),
             short_help=_("Validate and show current project settings"))
def info(ctx: typer.Context,
    filename: Annotated[
        str,
        typer.Argument(help=_("Name of the YAML report file to display (optional)"))
    ] = None,
):
    settings_manager: SettingsManager = ctx.obj.get("setting_manager")
    project_name = str(ctx.obj.get("project", "default"))
    logger = ctx.obj.get("logger", logging.getLogger(__name__))

    results_dir = TyperUtils.get_default_report_dir()
    target_file = _choose_report_file(results_dir, filename)
    report = Report.from_yaml(target_file)
    TyperUtils.display_report(report, True)

@app.command(help=_("Archive old reports"),
             short_help=_("Archive old reports"))
def archive(ctx: typer.Context,
            days: Annotated[
                int,
                typer.Argument(help=_("Number of days since the report was created after which it will be deleted."))
            ] = 60,
):
    settings_manager: SettingsManager = ctx.obj.get("setting_manager")
    project_name = str(ctx.obj.get("project", "default"))
    logger = ctx.obj.get("logger", logging.getLogger(__name__))
    results_dir = TyperUtils.get_default_report_dir()

    umbral = datetime.datetime.now() - datetime.timedelta(days=days)

    yaml_files = sorted(
        [p for p in results_dir.glob("*.yaml") if datetime.datetime.fromtimestamp(p.stat().st_mtime) < umbral],
        key=lambda p: p.stat().st_mtime,
    )

    for path in yaml_files:
        nuevo_path = path.parent / f".{path.name}"
        path.rename(nuevo_path)

    TyperUtils.info(_(f"{len(yaml_files)} files archived"))

@app.command(help=_("Remove archived reports"),
             short_help=_("Remove archived reports"))
def remove(ctx: typer.Context,
            days: Annotated[
                int,
                typer.Argument(help=_("Number of days since the report was created after which it will be deleted."))
            ] = 60,
):
    settings_manager: SettingsManager = ctx.obj.get("setting_manager")
    project_name = str(ctx.obj.get("project", "default"))
    logger = ctx.obj.get("logger", logging.getLogger(__name__))
    results_dir = TyperUtils.get_default_report_dir()

    files_to_delete = list(results_dir.glob(".*.yaml"))

    if not files_to_delete:
        TyperUtils.warning("No archived file report found.")
        return

    TyperUtils.console.print("[bold red]The following files will be deleted:[/bold red]")
    for f in files_to_delete:
        TyperUtils.console.print(f"  • {f.name}")

    if Confirm.ask("[bold]Do you want to proceed?[/bold]", default=False):
        for f in files_to_delete:
            f.unlink()
            TyperUtils.console.print(f"[green]Deleted:[/green] {f.name}")
    else:
        TyperUtils.console.print("[cyan]Operation cancelled.[/cyan]")

def _choose_report_file(results_dir:Path, filename:str = None) -> Path:

    # Si el usuario no pasa ningún archivo → mostrar el último
    if filename is None:
        yaml_files = sorted(
            results_dir.glob("*.yaml"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        if not yaml_files:
            TyperUtils.fatal(f"No reports found in: {results_dir}")

        target_file = yaml_files[0]
        TyperUtils.info(_(f"Showing latest report: {target_file.name}"))
    else:
        target_file = results_dir / filename
        if not target_file.exists():
            TyperUtils.fatal(f"Report file not found:{target_file}")

    return target_file
if __name__ == "__main__":
    app()