from wildintel_tools.ui.typer.i18n import _, setup_locale
import locale
import os, sys
import typer

from typing_extensions import Annotated
from typing import Optional
from pathlib import Path

locales_dir=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "locales")
setup_locale(locale.getdefaultlocale()[0] if locale.getdefaultlocale()[0] else "en_GB", locales_dir)

from wildintel_tools.ui.typer.logger import logger, setup_logging
from wildintel_tools.ui.typer.settings import SettingsManager
from wildintel_tools.ui.typer.TyperUtils import TyperUtils

from wildintel_tools.ui.typer.commands import config
#from wildintel_tools.ui.typer.commands import convert
#from wildintel_tools.ui.typer.commands import helpers
#from wildintel_tools.ui.typer.commands import package
#from wildintel_tools.ui.typer.commands import pipeline
#from wildintel_tools.ui.typer.commands import upload
from wildintel_tools.ui.typer.commands import wildintel

APP_NAME = "wildintel-tools"
__version__ = "0.1.0"

app = typer.Typer(help="WildINTEL CLI Tool", invoke_without_command=True)
app.add_typer(config.app, name="config")
#app.add_typer(convert.app, name="convert")
#app.add_typer(helpers.app, name="helpers")
#app.add_typer(package.app, name="package")
#app.add_typer(pipeline.app, name="pipeline")
#app.add_typer(upload.app, name="upload")
app.add_typer(wildintel.app, name="wildintel")

@app.callback()
def main_callback(ctx: typer.Context,
    version: Annotated[
        Optional[bool],
        typer.Option(
            "--version",
            help=_("Show program's version number and exit"),
            is_eager=True
        )
    ] = None,
    verbosity: Annotated[
        Optional[int],
        typer.Option(
            "--verbosity",
            help=_("Logger level: 0 (error), 1 (info), 2 (debug)."),
            case_sensitive=False
        )
    ] = 1,
    
    log_file: Annotated[
        Optional[Path],
        typer.Option(
            "--logfile",
            help="Path to the log file"
        )
    ] = Path(typer.get_app_dir(APP_NAME))/ "app.log",

    locale_code: Annotated[
        Optional[str],
        typer.Option(
            "--locale",
            help=_("Language code (for example, “es”, “en”). By default, the system language is used.")
        )
    ] = locale.getdefaultlocale()[0] if locale.getdefaultlocale()[0] else "en_GB",

    project: Annotated[
        Optional[str],
        typer.Option(
            "--project",
            help=_("Project name for settings")
        )
    ] = "default",

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
            help=_("Directory containing settings files")
        )
    ] = Path(typer.get_app_dir(APP_NAME)),
    

):
    if (version):
        prog = os.path.basename(sys.argv[0])
        TyperUtils.console.print(f"{prog}s {__version__}")
        exit(1)

    ## Load settings
    setting_manager= SettingsManager(settings_dir=settings_dir)
    settings= setting_manager.load_settings(project)

    if verbosity is not None:
        settings.update({"LOGGER.loglevel": verbosity}, validate=False)
    if log_file is not None:
        settings.update({"LOGGER.filename": log_file}, validate=False)
    if locale_code is not None:
        settings.update({"LOCALE.language": locale_code}, validate=False)

    # Setup locale
    locales_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "locales")
    setup_locale(settings.locale.language, locales_dir)

    # Setup logging
    setup_logging(settings.LOGGER.loglevel, settings.LOGGER.filename)

    ctx.obj = {
        "setting_manager": setting_manager,
        "settings": settings,
        "logger": logger,
        "_":_,
        "project": project
    }

if __name__ == "__main__":
    app()