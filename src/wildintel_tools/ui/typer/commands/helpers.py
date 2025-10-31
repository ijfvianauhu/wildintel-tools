import json

from dynaconf import Dynaconf
from rich.table import Table
from typer_config import conf_callback_factory

from wildintel_tools.ui.typer.i18n import _
from wildintel_tools.ui.typer.TyperUtils import TyperUtils
from wildintel_tools.ui.typer.settings import SettingsManager, SETTINGS_ORDER

from wildintel_tools.helpers import(
    check_ffmpeg,
    check_exiftool,
    check_trapper_connection,
    get_trapper_classification_projects
)

import typer

app = typer.Typer(
    help=_("Helpers"),
    short_help=_("Helpers")
)


# 🔹 Loader que recibe la ruta completa del archivo
def dynaconf_loader(file_path: str) -> dict:
    return json.loads(file_path)

# 🔹 Callback base
base_conf_callback = conf_callback_factory(dynaconf_loader)

# 🔹 Callback dinámico que usa otro parámetro (base_path)
def dynamic_dynaconf_callback(ctx, param, value):
    settings = ctx.obj.get("settings", {}).as_dict()
    settings_manager = ctx.obj.get("setting_manager")
    json_str = json.dumps(settings, default=str)
    a=base_conf_callback(ctx, param, json_str)

    for key, value in ctx.params.items():
        if key == "user":
            if value is None:
                ctx.params[key] = settings["GENERAL"]["login"]
        if key == "url":
            if value is None:
                ctx.params[key] = settings["GENERAL"]["host"]

        if key == "password":
            if value is None:
                ctx.params[key] = settings["GENERAL"]["password"]

    return a

@app.callback()
def main_callback(ctx: typer.Context):
    """
    Esta función se ejecuta antes de cualquier comando.
    Puedes usarla para configurar el contexto global.
    """
    #ctx.obj = {"config": "valor global"}
    #typer.echo("Callback ejecutado")
    pass
    
@app.command(help=_("Test connection to Trapper server (API & FTPS)"), short_help=_("Test connection to Trapper server (API & FTPS)"))
def test_connection(ctx: typer.Context,
                    url: str = typer.Argument(
                        None,
                        help=_("Base URL of the Trapper server (e.g., https://trapper.example.org)"),
                    ),
                    user: str = typer.Argument(
                        None,
                        help=_("Username to authenticate with the Trapper server")
                    ),
                    password: str = typer.Option(
                        None,
                        "--password",
                        "-p",
                        help=_("Password for the specified user (use only if no access token is provided)")
                    ),
                    token: str = typer.Option(
                        None,
                        "--token",
                        "-t",
                        help=_("Access token for the Trapper API (alternative to using a password)"),
                        callback=dynamic_dynaconf_callback
                    ),
    ):

    settings = ctx.obj.get("settings", {})

    try:
        TyperUtils.info(_("Testing Trapper API connection..."))
        check_trapper_connection(url,user, password, None)
        TyperUtils.success(_("Trapper API connection successful!"))
    except Exception as e:
        TyperUtils.fatal(_(f"Failed to connect to Trapper API. Check your settings: {str(e)}"))

@app.command(help=_("Test the availability of FFMPEG & exiftool"), short_help=_("Test the availability of FFMPEG & exiftool"))
def test_external_tools(ctx: typer.Context):
    project_name = ctx.obj.get("project")
    settings_manager: SettingsManager = ctx.obj.get("setting_manager")
    settings = settings_manager.load_settings(project_name)

    try:
        TyperUtils.logger.info(_("Testing FFMPEG"))
        check_ffmpeg(settings.general.ffmpeg)
        TyperUtils.success(_("FFMPEG test successful!"))
    except Exception as e:
        TyperUtils.error(_(f"FFMPEG test failed: {str(e)}"))

    try:
        TyperUtils.logger.info(_("Testing exiftool."))
        check_exiftool(settings.general.exiftool)
        TyperUtils.success(_("exiftool test successful!"))
    except Exception as e:
        TyperUtils.error(_(f"exiftool test failed: {str(e)}"))


@app.command(help=_("Get research project info from trapper instance"), short_help=_("Get research project info"))
def classification_projects(ctx: typer.Context,
        url: str = typer.Argument(
            None,
            help=_("Base URL of the Trapper server (e.g., https://trapper.example.org)"),
        ),
        user: str = typer.Argument(
            None,
            help=_("Username to authenticate with the Trapper server")
        ),
        password: str = typer.Option(
            None,
            "--password",
            "-p",
            help=_("Password for the specified user (use only if no access token is provided)")
        ),
        token: str = typer.Option(
            None,
            "--token",
            "-t",
            help=_("Access token for the Trapper API (alternative to using a password)"),
            callback=dynamic_dynaconf_callback
        ),
    ):
    settings = ctx.obj.get("settings", {})

    try:
        TyperUtils.info(_("Testing Trapper API connection..."))

        cp=get_trapper_classification_projects(settings.get("GENERAL.host"),
                                 settings.get("GENERAL.login"),
                                 settings.get("GENERAL.password"),
                                 # settings.get("GENERAL.access_token")
                                 None
                                 )

        # Crear la tabla
        table = Table(title="Trapper Classification Projects")

        table.add_column("PK", style="cyan", no_wrap=True)
        table.add_column("Name", style="green")
        table.add_column("Owner", style="magenta")
        table.add_column("Research Project", style="yellow")
        table.add_column("Status", style="blue")
        table.add_column("Active", style="red")
        table.add_column("Roles", style="white")

        # Añadir filas
        for p in cp.results:
            roles_str = ", ".join([role.roles[0] for role in p.project_roles])
            table.add_row(str(p.pk), p.name, p.owner, p.research_project, p.status, str(p.is_active), roles_str)

        # Mostrar la tabla
        TyperUtils.console.print(table)
        #console.print("✅ Trapper API connection successful!", style="bold green")

    except Exception as e:
        TyperUtils.fatal(_(f"Failed to connect to Trapper API. Check your settings: {str(e)}"))

