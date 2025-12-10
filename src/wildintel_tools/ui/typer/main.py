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
import requests
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
__version__ = "0.2.3"

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

def make_dynaconf_callback(override_mapping: dict | None = None):
    def callback(ctx, param: typer.CallbackParam, value: Any):
        return TyperUtils.dynamic_dynaconf_callback(ctx, param, value, override_mapping=override_mapping)
    return callback

override_mapping = {
    "verbosity": ("LOGGER", "loglevel"),
    "log_file": ("LOGGER", "filename"),
}

callback_with_override = make_dynaconf_callback(override_mapping)

def get_latest_github_release(owner: str, repo: str) -> str:
    """
    Returns the tag name of the latest GitHub release.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    response = requests.get(url)
    if response.status_code != 200:
        TyperUtils.error(_(f"GitHub API request failed with status {response.status_code}"))
        return None

    data = response.json()
    return data["tag_name"]


def is_newer_version(current_version: str, latest_version: str) -> bool:
    """
    Returns True if latest_version is newer than current_version.
    Assumes versions are in semantic versioning format: vMAJOR.MINOR.PATCH
    """

    def parse_version(v: str):
        return tuple(int(x) for x in v.lstrip("v").split("."))

    return parse_version(latest_version) > parse_version(current_version)


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
          callback=callback_with_override
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
    setup_logging(APP_NAME,verbosity, log_file)

    TyperUtils.home = Path(typer.get_app_dir(APP_NAME))

    ctx.obj = {
        "setting_manager": SettingsManager(settings_dir=Path(settings_dir)),
        "settings": settings,
        "logger": logger,
        "_":_,
        "project": project
    }

    latest_version = get_latest_github_release("ijfvianauhu", APP_NAME)
    if latest_version and is_newer_version(__version__, latest_version):
        TyperUtils.warning(_(f"A newer version is available: {latest_version}. You can download it from "
                             f"https://github.com/ijfvianauhu/wildintel-tools"))
    else:
        pass

if __name__ == "__main__":
    app()