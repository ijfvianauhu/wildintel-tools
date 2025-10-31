from dynaconf import Dynaconf
from typer_config import conf_callback_factory, use_config

from wildintel_tools.ui.typer.i18n import _, setup_locale
import locale
import os, sys
import typer

from typing_extensions import Annotated
from typing import Optional, Dict, Any
from pathlib import Path

locales_dir=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "locales")
setup_locale(locale.getdefaultlocale()[0] if locale.getdefaultlocale()[0] else "en_GB", locales_dir)

from wildintel_tools.ui.typer.logger import logger, setup_logging
from wildintel_tools.ui.typer.settings import SettingsManager
from wildintel_tools.ui.typer.TyperUtils import TyperUtils

from wildintel_tools.ui.typer.commands import config
from wildintel_tools.ui.typer.commands import reports
from wildintel_tools.ui.typer.commands import helpers
from wildintel_tools.ui.typer.commands import wildintel

APP_NAME = "wildintel-tools"
__version__ = "0.1.0"

app = typer.Typer(help="WildINTEL CLI Tool", invoke_without_command=True)
app.add_typer(config.app, name="config")
app.add_typer(helpers.app, name="helpers")
app.add_typer(reports.app, name="reports")
app.add_typer(wildintel.app, name="wildintel")

# 🔹 Loader que recibe la ruta completa del archivo
def dynaconf_loader(file_path: str) -> dict:
    settings_dir = os.path.dirname(file_path)
    file_name = os.path.basename(file_path)
    setting_manager = SettingsManager(settings_dir=Path(settings_dir))
    settings = setting_manager.load_settings(file_name, True, True)
    return settings.as_dict()

# 🔹 Callback base
base_conf_callback = conf_callback_factory(dynaconf_loader)

# 🔹 Callback dinámico que usa otro parámetro (base_path)
def dynamic_dynaconf_callback(ctx, param, value):
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
    
    log_file: Annotated[
        Optional[Path],
        typer.Option(
            "--logfile",
            help="Path to the log file"
        )
    ] = Path(typer.get_app_dir(APP_NAME))/ "app.log",

    env_file: Annotated[
        Optional[bool],
        typer.Option(
            "--env-file",
            help=_("Load .env file with dotenv")
        )
    ] = False,

    settings_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--settings-dir",
            help=_("Directory containing settings files"),
        )
    ] = Path(typer.get_app_dir(APP_NAME)),

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