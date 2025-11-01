"""
Logger management commands for the WildINTEL CLI.

This module provides Typer commands to manage project log files, including:
- Viewing logs in real time (similar to ``tail -f``).
- Archiving and compressing existing logs.

The commands rely on the application's loaded settings to determine the
location of the active log file.
"""

import gzip
import shutil
import time
from datetime import datetime
from pathlib import Path

import typer
from wildintel_tools.ui.typer.i18n import _
from wildintel_tools.ui.typer.TyperUtils import TyperUtils

app = typer.Typer(
    help=_("Manage project logger"),
    short_help=_("Manage project logger")
)

@app.callback()
def main_callback(ctx: typer.Context,
      ):
    """
    Entry point for the `logger` command group.

    This callback is executed before any subcommand in this module.
    It currently serves as a placeholder for future extensions.

    :param ctx: The Typer context object containing CLI state.
    :type ctx: typer.Context
    """
    pass

@app.command("show", help=_("Show log file content"), short_help=_("Show log file content"))
def show(
    ctx: typer.Context,
    follow: bool = typer.Option(False, help=_("Follow file content (like tail -f)")),
):
    """
    Display the contents of the current log file.

    This command reads the log file defined in the current project's settings.
    It can optionally follow new log entries in real time, similar to the Unix
    ``tail -f`` command.

    :param ctx: The Typer context containing loaded settings and managers.
    :type ctx: typer.Context
    :param follow: If True, continuously follow the log file output.
    :type follow: bool

    :raises SystemExit: If the log file does not exist.
    """
    settings = ctx.obj.get("settings")
    log_path=settings.LOGGER.filename

    if Path(log_path).exists():
        with Path(log_path).open("r") as f:
            if follow:
                # Ir al final del archivo
                f.seek(0, 2)
            else:
                # Mostrar todo el contenido existente
                for line in f:
                    print(line, end="")
                exit()
            try:
                while True:
                    line = f.readline()
                    if line:
                        print(line, end="")  # `end=""` para no duplicar saltos de línea
                    else:
                        time.sleep(0.5)  # Espera antes de volver a leer
            except KeyboardInterrupt:
                TyperUtils.info(_(f("\nStopped following the log.")))
    else:
        TyperUtils.fatal(_(f"Log file not found: {log_path}"))

@app.command("logger-archive", help=_("Compress the log file and remove the original"),
             short_help=_("Compress and archive log"))
def archive( ctx: typer.Context,):
    """
    Compress and archive the current log file.

    The active log file is compressed into a ``.gz`` archive with a timestamped
    filename and the original file is removed afterward.

    Example:
        If the log file is ``app.log``, the archive will be named
        ``app_2025-10-31_16-45-02.log.gz``.

    :param ctx: The Typer context containing the settings manager and configuration.
    :type ctx: typer.Context

    :raises SystemExit: If the log file cannot be found.
    """
    settings = ctx.obj.get("settings")
    log_path = settings.LOGGER.filename

    if not log_path.exists():
        TyperUtils.fatal(_(f"Log file not found: {log_path}"))

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    archive_path = log_path.with_name(f"{log_path.stem}_{timestamp}{log_path.suffix}.gz")

    with log_path.open("rb") as f_in, gzip.open(archive_path, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)

    log_path.unlink()

    TyperUtils.success(_(f"Log archived to: {archive_path}"))

