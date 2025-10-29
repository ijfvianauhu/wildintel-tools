from enum import Enum
from dynaconf import ValidationError
import typer
from typing_extensions import Annotated
from typing import Optional
from pathlib import Path
from getpass import getpass
from wildintel_tools.ui.typer.i18n import _
from wildintel_tools.ui.typer.TyperUtils import TyperUtils
from wildintel_tools.ui.typer.settings import SettingsManager, SETTINGS_ORDER

app = typer.Typer(
    help=_("Manage project configurations"),
    short_help=_("Manage project configurations")
)

@app.callback()
def main_callback(ctx: typer.Context,
          template: Annotated[
                  Optional[Path],
                  typer.Option(help=_("Path to custom settings template"))
              ] = None,
    ):
    """
    Esta función se ejecuta antes de cualquier comando.
    Puedes usarla para configurar el contexto global.
    """
    if ctx.obj is None:
        ctx.obj = {}

    ctx.obj["template"] = template

@app.command(
   help=_("Initialize a new project configuration"), 
   short_help=_("Initialize a new project configuration")
)
def init(
    ctx: typer.Context,
    env_file: Annotated[
        Optional[bool],
        typer.Option(help="Indica si se debe generar un archivo .env.")
    ] = False,
):
    settings_manager = ctx.obj.get("setting_manager")
    project_name =  str(ctx.obj.get("project", "default"))
    env_file =  ctx.obj.get("project", "default")

    template = ctx.obj.get("template", None)
    settings_file = settings_manager.create_project_settings(
        project_name, template, env_file=env_file
    )
    
    TyperUtils.success(_(f"Created project settings at: {settings_file}"))


@app.command(help=_("Validate and show current project settings"), short_help=_("Validate and show current project settings"))
def show(
    ctx: typer.Context,
    project_name: Annotated[
        str,
        typer.Argument(help="Nombre del proyecto que se va a inicializar.")
    ]="default"):
    
    settings_manager:SettingsManager = ctx.obj.get("setting_manager")
    logger = ctx.obj.get("logger")

    try:
        settings = settings_manager.load_settings(project_name, validate=True)
    except ValidationError as e:
        print(e)
        logger.error(f"Settings validation error: {e}")
        exit(1)

    # Print directly to stdout for user-facing output
    print(f"\nSettings for project '{project_name}':")
    for group in SETTINGS_ORDER:
        if hasattr(settings, group):
            print(f"\n[{group}]")
            for key in SETTINGS_ORDER[group]:
                if key == "password":
                    print(f"{key} = [hidden]")
                else:
                    variable = f"{group}.{key}"
                    print(f"{key} = {getattr(settings, variable, '')}")

@app.command(help=_("List all available project configurations"), short_help=_("List all available project configurations"))
def list(ctx: typer.Context):
    settings_manager:SettingsManager = ctx.obj.get("setting_manager")
    
    """List all available project configurations."""
    projects = settings_manager.list_projects()
    if not projects:
        TyperConsole.info(_("No project configurations found"))
        return
    # Keep print for output that users might want to copy/paste
    TyperUtils.console.print(_("\nAvailable project configurations:"))
    for project in projects:
        print(f"- {project}")

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

class GroupEnum(str, Enum):
    general = "general"
    convert = "convert"
    package = "tres"
    upload = "upload"
    pipeline = "pipeline"

@app.command(help=_("Interactively configure settings for a specific group"), short_help=_("Interactively configure settings for a specific group"))
def setup(ctx: typer.Context, 
    project_name: Annotated[
        str,
        typer.Argument(help=_("Name of the project whose configuration will be edited"))
    ],
    group: Annotated[
        GroupEnum,
        typer.Argument(help=_("Name of the section that will be edited"))
    ]
    ):
    
    settings_manager:SettingsManager = ctx.obj.get("setting_manager")
    
    TyperUtils.info(_(f"Starting interactive configuration for {project_name}/{group}"))
    settings = settings_manager.load_settings(project_name)
    settings_path = settings_manager.get_settings_path(project_name)

    if not hasattr(settings, group):
        TyperUtils.warning(f"No settings found for group '{group}'")
        return

    TyperUtils.console.print(f"\nCurrent {group} settings:")
    group_settings = getattr(settings, group)
    modified_count = 0
    quit_all = False

    for key in group_settings:
        value = getattr(group_settings, key)

        # Display current value (keep print for user interaction)
        if key == "password":
            TyperUtils.console.print(f"\n{key} = [hidden]")
        else:
            TyperUtils.console.print(f"\n{key} = {value}")

        while True:
            # If value is list inform user about format
            if isinstance(value, list):
                prompt_hint = "[hint: this is a list variable; please provide values separated by commas]\n"
            else:
                prompt_hint = ""
            prompt = f"Enter new value for '{key}' (press Enter to keep current, or type 'q' to quit):\n{prompt_hint}"

            # use safe input for password
            if key == "password":
                new_value = getpass(prompt)
            else:
                new_value = input(prompt)

            if new_value.lower() in ("q", "quit"):
                TyperUtils.info("Exiting interactive settings session")
                quit_all = True
                break

            if not new_value:  # Keep current value
                break

            try:
                # Handle different value types
                if isinstance(value, bool):
                    new_value = new_value.lower() in ("true", "yes", "1", "y")
                elif isinstance(value, int):
                    new_value = int(new_value)
                elif isinstance(value, list):
                    # list of integers
                    if key in ["resize_img_size"]:
                        try:
                            new_value = [
                                int(x.strip()) for x in new_value.split(",")
                            ]
                        except ValueError:
                            raise ValueError(
                                "List values must be integers separated by commas"
                            )
                    # list of strings
                    else:
                        new_value = [x.strip() for x in new_value.split(",")]

                # Update setting, if value is not valid it will raise a ValidatorError
                settings.update({f"{group}.{key}": new_value}, validate=True)
                modified_count += 1
                TyperUtils.success(f"Updated setting {group}.{key}")
                break  # Break if update successful

            except (ValueError, KeyError, ValidationError) as e:
                error_msg = str(e)
                TyperUtils.error(_(f"Failed to update {key}: {error_msg}"))

                retry = input(
                    "Would you like to try again? (y/n, or 'q' to quit): "
                )
                if retry.lower() in ("q", "quit"):
                    TyperUtils.info("Exiting interactive settings session")
                    quit_all = True
                    break
                if retry.lower() != "y":
                    break

        if quit_all:
            break

    if modified_count > 0:
        # Save modified settings back to file
        settings_manager.export_settings(settings.to_dict(), settings_path)
        TyperUtils.success(f"Successfully updated {modified_count} settings in {group}!")


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