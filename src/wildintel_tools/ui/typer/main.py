"""
Main command-line interface (CLI) entry point for the WildINTEL Tools package.

This module initializes the WildINTEL CLI using :mod:`typer`, configures
localization, logging, and dynamic settings management through `Dynaconf`.

The CLI provides several subcommands for configuration, reporting, data
management, and integration with WildINTEL services.

Subcommands:
    - ``config``: Manage configuration files and environment settings.
    - ``helpers``: Utility functions and helper operations.
    - ``reports``: Generate and handle processing reports.
    - ``wildintel``: Interface with the WildINTEL platform.

Example:
    .. code-block:: console

        $ wildintel-tools --help
        $ wildintel-tools config list
        $ wildintel-tools reports generate --project my_project
"""
from typer_config import conf_callback_factory
from wildintel_tools.ui.typer.i18n import _, setup_locale

import locale
import os
import sys

# --------------------------------------------------------------------------- #
# Localization setup
# --------------------------------------------------------------------------- #

locales_dir=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "locales")
setup_locale(locale.getdefaultlocale()[0] if locale.getdefaultlocale()[0] else "en_GB", locales_dir)

import typer
from typing_extensions import Annotated
from typing import Optional, Any
from pathlib import Path
from wildintel_tools.ui.typer.logger import logger, setup_logging
from wildintel_tools.ui.typer.settings import SettingsManager
from wildintel_tools.ui.typer.TyperUtils import TyperUtils
from wildintel_tools.ui.typer.commands import config
from wildintel_tools.ui.typer.commands import reports
from wildintel_tools.ui.typer.commands import logger
from wildintel_tools.ui.typer.commands import helpers
from wildintel_tools.ui.typer.commands import wildintel
from wildintel_tools.ui.typer.commands import epicollect


# --------------------------------------------------------------------------- #
# App metadata
# --------------------------------------------------------------------------- #

APP_NAME = "wildintel-tools"
__version__ = "0.2.0"

# --------------------------------------------------------------------------- #
# Typer CLI definition
# --------------------------------------------------------------------------- #

app = typer.Typer(help="WildINTEL CLI Tool", invoke_without_command=True)
app.add_typer(config.app, name="config")
app.add_typer(helpers.app, name="helpers")
app.add_typer(reports.app, name="reports")
app.add_typer(logger.app, name="logger")
app.add_typer(wildintel.app, name="wildintel")
app.add_typer(epicollect.app, name="epicollect")

def dynaconf_loader(file_path: str) -> dict:
    """
    Load application settings using Dynaconf.

    :param file_path: Full path to the settings file.
    :type file_path: str
    :return: Dictionary containing loaded configuration values.
    :rtype: dict

    Example:
        .. code-block:: python

            settings = dynaconf_loader("/path/to/project.toml")
    """
    settings_dir = os.path.dirname(file_path)
    file_name = os.path.basename(file_path)
    setting_manager = SettingsManager(settings_dir=Path(settings_dir))
    settings = setting_manager.load_settings(file_name, True, True)
    return settings.as_dict()

# 🔹 Callback base
base_conf_callback = conf_callback_factory(dynaconf_loader)

# 🔹 Callback dinámico que usa otro parámetro (base_path)
def dynamic_dynaconf_callback(ctx: typer.Context, param: typer.CallbackParam, value: Any):
    """
    Typer callback to dynamically load configuration before executing a command.

    This callback loads a Dynaconf configuration based on the current project
    and settings directory, then injects the resulting configuration into
    the Typer context object (`ctx.obj`).

    :param ctx: The current Typer context.
    :type ctx: typer.Context
    :param param: The parameter being processed.
    :type param: typer.CallbackParam
    :param value: The raw parameter value passed to the callback.
    :type value: Any
    :return: Configuration dictionary from Dynaconf.
    :rtype: dict
    """

    base_path = ctx.params.get("settings_dir", ".")
    file_path = os.path.join(base_path, ctx.params.get("project", "default"))
    a= base_conf_callback(ctx, param, file_path)

    if ctx.obj is None:
        ctx.obj = {}

    settings = ctx.default_map.copy() if ctx.default_map else {}

    for key, value in ctx.params.items():
        if key == "verbosity":
            if value is None:
                ctx.params[key] = settings["LOGGER"]["loglevel"]

        if key == "log_file":
            if value is None:
                ctx.params[key] = settings["LOGGER"]["filename"]

    ctx.obj["settings"] = settings

    return a

@app.callback()
def main_callback(ctx: typer.Context,
    version: Annotated[Optional[bool], typer.Option( help=_("Show program's version number and exit"))] = None,
    verbosity: Annotated[Optional[int], typer.Option( help=_("Logger level: 0 (error), 1 (info), 2 (debug).")) ] = None,
    log_file: Annotated[Optional[Path], typer.Option( "--logfile",
                help="Path to the log file")] = Path(typer.get_app_dir(APP_NAME))/ "app.log",
    env_file: Annotated[Optional[bool], typer.Option("--env-file", help=_("Load .env file with dotenv"))] = False,

    settings_dir: Annotated[Optional[Path], typer.Option("--settings-dir",
                help=_("Directory containing settings files"), )] = Path(typer.get_app_dir(APP_NAME)),

    project: Annotated[
          Optional[str],
          typer.Option(
              "--project",
              help=_("Project name for settings"),
          )
    ] = "default",

    config: Annotated[
      Path,
      typer.Option(
          hidden=True,
          callback=dynamic_dynaconf_callback
      )
    ] = None,

):
    """
    Main CLI entry point for WildINTEL Tools.

    This callback initializes the logging system, loads the settings, and
    prepares the Typer context with commonly used objects for subcommands.

    :param ctx: Typer context object.
    :type ctx: typer.Context
    :param version: Show version information and exit.
    :type version: bool, optional
    :param verbosity: Logging level (0=WARNING, 1=INFO, 2=DEBUG).
    :type verbosity: int, optional
    :param log_file: Optional path to a log file.
    :type log_file: Path, optional
    :param env_file: Whether to load an additional .env file for settings.
    :type env_file: bool, optional
    :param settings_dir: Directory where settings files are stored.
    :type settings_dir: Path, optional
    :param project: Name of the active project to load settings for.
    :type project: str, optional
    :param config: Hidden parameter for internal Dynaconf callback use.
    :type config: Path, optional
    :return: None
    :rtype: None
    """
    if (version):
        prog = os.path.basename(sys.argv[0])
        TyperUtils.console.print(f"{prog}s {__version__}")
        exit(1)

    ## Load settings --> in project param callback
    settings = ctx.obj["settings"]
    settings_dyn=SettingsManager.load_from_array(settings)
    setup_logging(APP_NAME,verbosity, log_file)

    TyperUtils.home = Path(typer.get_app_dir(APP_NAME))

    ctx.obj = {
        "setting_manager": SettingsManager(settings_dir=Path(settings_dir)),
        "settings": settings_dyn,
        "logger": logger,
        "_":_,
        "project": project
    }

if __name__ == "__main__":
    app()