import logging
from dynaconf import ValidationError
import typer
from typing_extensions import Annotated
from typing import Optional
from pathlib import Path
from wildintel_tools.ui.typer.i18n import _
from wildintel_tools.ui.typer.TyperUtils import TyperUtils
from wildintel_tools.ui.typer.settings import SettingsManager, SETTINGS_ORDER

app = typer.Typer(
    help=_("Manage project configurations"),
    short_help=_("Manage project configurations")
)

@app.callback()
def main_callback(ctx: typer.Context
    ):
    pass

@app.command(
   help=_("Initialize a new project configuration"), 
   short_help=_("Initialize a new project configuration")
)
def init(
    ctx: typer.Context,
    template: Annotated[
                  Optional[Path],
                  typer.Option(help=_("Path to custom settings template"))
              ] = None,
    env_file: Annotated[
        Optional[bool],
        typer.Option(help=_("Load .env file with environment variables"))
    ] = False,
):
    settings_manager = ctx.obj.get("setting_manager")
    project_name     =  str(ctx.obj.get("project", "default"))
    logger = ctx.obj.get("logger", logging.getLogger(__name__))

    settings_file = settings_manager.create_project_settings(
        project_name, template, env_file=env_file
    )
    
    TyperUtils.success(_(f"Created project settings at: {settings_file}"))


@app.command(help=_("Validate and show current project settings"), short_help=_("Validate and show current project settings"))
def show(
    ctx: typer.Context):
    
    settings_manager:SettingsManager = ctx.obj.get("setting_manager")
    project_name     =  str(ctx.obj.get("project", "default"))

    logger = ctx.obj.get("logger", logging.getLogger(__name__))

    try:
        settings = settings_manager.load_settings(project_name, validate=True)
    except ValidationError as e:
        TyperUtils.fatal("Settings validation error: {e}")

    TyperUtils.console.print(f"\nSettings for project '{project_name}':")

    for group in SETTINGS_ORDER:
        if hasattr(settings, group):
            TyperUtils.console.print(f"\n[{group}]")
            for key in SETTINGS_ORDER[group]:
                if key == "password":
                    TyperUtils.console.print(f"{key} = [hidden]")
                else:
                    variable = f"{group}.{key}"
                    TyperUtils.console.print(f"{key} = {getattr(settings, variable, '')}")

@app.command(help=_("List all available project configurations"), short_help=_("List all available project configurations"))
def list(ctx: typer.Context):
    settings_manager:SettingsManager = ctx.obj.get("setting_manager")
    
    """List all available project configurations."""
    projects = settings_manager.list_projects()
    if not projects:
        TyperUtils.info(_("No project configurations found"))
        return
    # Keep print for output that users might want to copy/paste
    TyperUtils.console.print(_("\nAvailable project configurations:"))
    for project in projects:
        TyperUtils.console.print(f"- {project}")

@app.command(help=_("Edit settings file in default editor"), short_help=_("Edit settings file in default editor"))
def edit(ctx: typer.Context, project_name: Annotated[
        str,
        typer.Argument(help=_("Name of the project whose configuration will be edited"))
    ]="default"):
    
    settings_manager:SettingsManager = ctx.obj.get("setting_manager")
    
    try:
        settings_manager.edit_settings(project_name)
        TyperUtils.success(_(f"Settings validated and saved successfully for project '{project_name}'"))
    except Exception as e:
        TyperUtils.error(f"Failed to edit settings for project '{project_name}': {e}")
        return

@app.command(
    help=_("Show the value of a specific project configuration setting"),
    short_help=_("Display a project setting")
)
def get(
        ctx: typer.Context,
        project_name: Annotated[
            str,
            typer.Option(help="Nombre del proyecto que se va a inicializar.")
        ] = "default",
        param: Annotated[
            str,
            typer.Argument(help="Parameter to get in the format 'GROUP.key'")
        ] = ...,
):
    settings_manager: SettingsManager = ctx.obj.get("setting_manager")
    project_name = ctx.obj.get("project", project_name)

    try:
        value = settings_manager.get_param(project_name, param)
        TyperUtils.console.print(f"{param} = {value}")
    except Exception as e:
        TyperUtils.fatal(f"Failed to get parameter '{param}': {e}")

@app.command("set",
    help=_("Set or update the value of a specific project setting parameter"),
    short_help=_("Set a project setting")
)
def set_param(
        ctx: typer.Context,
        project_name: Annotated[
            str,
            typer.Option(help=_("Nombre del proyecto que se va a inicializar."))
        ] = "default",
        param_name: Annotated[
            str,
            typer.Argument(help=_("Parameter to set in the format 'GROUP.key'"))
        ] = "",
        param_value: Annotated[
            str,
            typer.Argument(help=_("Value to set "))
        ] = "",
):
    settings_manager: SettingsManager = ctx.obj.get("setting_manager")
    project_name = ctx.obj.get("project", project_name)

    try:
        settings_manager.set_param(project_name, param_name, param_value)
        settings = settings_manager.load_settings(project_name, validate=True)
        TyperUtils.success(f"Settings {param_name} updated successfully to {param_value} for project '{project_name}'")
    except ValidationError as e:
        TyperUtils.fatal(f"Settings validation error: {e}")

if __name__ == "__main__":
    app()