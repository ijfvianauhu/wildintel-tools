# python
"""
Commands for managing generated reports via Typer.

This module provides commands to list, view, archive and remove report YAML
files created by the application.

Functions
---------
main_callback(ctx)
    Typer callback executed before any command.
list(ctx)
    Show a list of generated reports.
info(ctx, filename=None)
    Validate and display a report file.
archive(ctx, days=60)
    Archive report files older than a given number of days.
remove(ctx, days=60)
    Remove previously archived report files.
_choose_report_file(results_dir, filename=None)
    Select a report file from the results directory.
"""
import datetime
import logging
import typer
from rich.prompt import Confirm
from typing_extensions import Annotated
from pathlib import Path

from wildintel_tools.reports import Report
from wildintel_tools.ui.typer.i18n import _
from wildintel_tools.ui.typer.TyperUtils import TyperUtils
from wildintel_tools.ui.typer.settings import SettingsManager

app = typer.Typer(
    help=_("Manage project configurations"),
    short_help=_("Manage project configurations")
)

@app.callback()
def main_callback(ctx: typer.Context                  ):
    """
    Typer callback executed before any command.

    Use this callback to initialize or modify the shared Typer context.

    :param ctx: Typer context object.
    :type ctx: typer.Context
    :return: None
    """
    pass

@app.command(
    help=_("Show a list of generated reports"),
    short_help=_("Show a list of generated reports")
)
def list(
        ctx: typer.Context,
):
    """
    Show a list of generated report YAML files.

    The command locates the default reports directory and prints a summary
    of report files found there.

    :param ctx: Typer context (expects `setting_manager`, `project`, `logger`).
    :type ctx: typer.Context
    :return: None
    """
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
    """
    Load and display a report file.

    If `filename` is not provided, the most recent report file from the
    default reports directory is selected.

    :param ctx: Typer context (expects `setting_manager`, `project`, `logger`).
    :type ctx: typer.Context
    :param filename: Optional YAML filename to display.
    :type filename: str | None
    :raises SystemExit: Exits with a fatal message if no reports are found or
        if the requested file does not exist.
    :return: None
    """
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
    """
    Archive report files older than `days`.

    Files older than the threshold are renamed with a leading dot (hidden).

    :param ctx: Typer context (expects `setting_manager`, `project`, `logger`).
    :type ctx: typer.Context
    :param days: Age threshold in days for archiving files.
    :type days: int
    :return: None
    """
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
    """
    Remove archived (hidden) report files.

    The function lists files with the pattern `.*.yaml`, displays them,
    and requests confirmation before deleting.

    :param ctx: Typer context (expects `setting_manager`, `project`, `logger`).
    :type ctx: typer.Context
    :param days: Unused parameter kept for CLI compatibility.
    :type days: int
    :return: None
    """
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
    """
    Choose a report YAML file to operate on.

    If `filename` is omitted, the most recent `*.yaml` file in `results_dir`
    is returned. If `filename` is provided, the corresponding path is validated.

    :param results_dir: Directory where report YAML files are stored.
    :type results_dir: pathlib.Path
    :param filename: Optional filename to select.
    :type filename: str | None
    :raises SystemExit: If no reports are found or the requested file does not exist.
    :return: Path to the selected YAML file.
    :rtype: pathlib.Path
    """
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