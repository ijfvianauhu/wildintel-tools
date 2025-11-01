# python
"""
Helpers CLI commands module for Typer.

Provides utilities to test connections and retrieve information from a
Trapper instance, and to check external tools (ffmpeg, exiftool).

Functions
---------
dynaconf_loader(file_path: str) -> dict
    Load configuration from a JSON string.
dynamic_dynaconf_callback(ctx, param, value)
    Dynamic callback that loads runtime configuration and fills context params.
main_callback(ctx: typer.Context)
    Callback executed before any Typer command.
test_connection(...)
    Test connection to a Trapper server (API).
test_external_tools(ctx: typer.Context)
    Test availability of FFMPEG and exiftool using project settings.
classification_projects(...)
    Retrieve classification projects from a Trapper instance and display them.
research_projects(...)
    Retrieve research projects from a Trapper instance and display them.
locations(...)
    Retrieve locations from a Trapper instance and display them.
"""
import json
from pathlib import Path
from typing import Annotated
from typer_config import conf_callback_factory
from wildintel_tools.ui.typer.i18n import _
from wildintel_tools.ui.typer.TyperUtils import TyperUtils
from wildintel_tools.ui.typer.settings import SettingsManager

from wildintel_tools.helpers import(
    check_ffmpeg,
    check_exiftool,
    check_trapper_connection,
    get_trapper_classification_projects,
    get_trapper_research_projects,
    get_trapper_locations
)

import typer

app = typer.Typer(
    help=_("Helpers"),
    short_help=_("Helpers")
)

def dynaconf_loader(file_path: str) -> dict:
    """
    Load configuration from a JSON string.

    Note:
        Despite the name, this function calls ``json.loads`` on ``file_path``,
        so it expects a JSON string containing the configuration, not a file path.

    :param file_path: JSON string with the configuration.
    :type file_path: str
    :return: Deserialized configuration dictionary.
    :rtype: dict
    :raises json.JSONDecodeError: If the string is not valid JSON.
    """
    return json.loads(file_path)


# Base callback
base_conf_callback = conf_callback_factory(dynaconf_loader)


def dynamic_dynaconf_callback(ctx, param, value):
    """
    Dynamic callback to load configuration values at runtime.

    This callback obtains configuration from ``ctx.obj["settings"]`` and
    serializes it to pass it to ``base_conf_callback``. It also fills
    context parameters (``user``, ``url``, ``password``) if they were not
    provided explicitly.

    :param ctx: Typer/Click context.
    :type ctx: typer.Context
    :param param: Parameter associated with the callback.
    :type param: click.Parameter
    :param value: Current parameter value.
    :type value: Any
    :return: Result of applying ``base_conf_callback``.
    :rtype: Any
    """
    settings = ctx.obj.get("settings", {}).as_dict()
    settings_manager = ctx.obj.get("setting_manager")
    json_str = json.dumps(settings, default=str)
    a = base_conf_callback(ctx, param, json_str)

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
    Callback executed before any Typer command.

    Use this to initialize or modify the global context.

    :param ctx: Typer context.
    :type ctx: typer.Context
    """
    # ctx.obj = {"config": "global value"}
    # typer.echo("Callback executed")
    pass


@app.command(help=_("Test connection to Trapper server (API)"),
             short_help=_("Test connection to Trapper server (API & FTPS)"))
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
                    ),

                    config: Annotated[
                        Path,
                        typer.Option(
                            hidden=True,
                            help=_("File to save the report"),
                            callback=dynamic_dynaconf_callback
                        )
                    ] = None,
    ):
    """
    Test the connection to a Trapper server (API).

    Performs a check using ``check_trapper_connection`` and reports the result
    to the console.

    :param ctx: Typer context.
    :type ctx: typer.Context
    :param url: Base URL of the Trapper server.
    :type url: str
    :param user: Username for authentication.
    :type user: str
    :param password: Password for the user (optional).
    :type password: str
    :param token: Access token (optional).
    :type token: str
    :param config: Internal configuration option (dynamic callback).
    :type config: pathlib.Path | None
    :raises Exception: If the connection fails a fatal message is logged.
    """
    settings = ctx.obj.get("settings", {})

    try:
        TyperUtils.info(_("Testing Trapper API connection..."))
        check_trapper_connection(url, user, password, None)
        TyperUtils.success(_("Trapper API connection successful!"))
    except Exception as e:
        TyperUtils.fatal(_(f"Failed to connect to Trapper API. Check your settings: {str(e)}"))


@app.command(help=_("Test the availability of FFMPEG & exiftool"),
             short_help=_("Test the availability of FFMPEG & exiftool"))
def test_external_tools(ctx: typer.Context):
    """
    Check availability of external tools: ffmpeg and exiftool.

    Loads the current project settings and runs the corresponding checks.

    :param ctx: Typer context (must contain ``project`` and ``setting_manager``).
    :type ctx: typer.Context
    :raises Exception: If any check raises, the error is logged.
    """
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

@app.command(help=_("Get classification project info from trapper instance"),
             short_help=_("Get classification project info"))
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
        ),

        config: Annotated[
            Path,
            typer.Option(
                hidden=True,
                help=_("File to save the report"),
                callback=dynamic_dynaconf_callback
            )
        ] = None,
):
    """
    Retrieve classification projects from a Trapper instance and display them.

    :param ctx: Typer context.
    :type ctx: typer.Context
    :param url: Base URL of the Trapper server.
    :type url: str
    :param user: Username for authentication.
    :type user: str
    :param password: Password for the user (optional).
    :type password: str
    :param token: Access token (optional).
    :type token: str
    :param config: Internal configuration option (dynamic callback).
    :type config: pathlib.Path | None
    :raises Exception: If retrieval fails a fatal message is logged.
    """
    settings = ctx.obj.get("settings", {})

    try:
        cps = get_trapper_classification_projects(url, user, password, None)
        data = [cp.model_dump() for cp in cps.results]
        TyperUtils.show_table(data, _("Trapper Classification Projects"), fields=["pk", "name", "research_project"])
    except Exception as e:
        TyperUtils.fatal(_(f"Failed getting trapper classification projects: {str(e)}"))


@app.command(help=_("Get research project info from trapper instance"), short_help=_("Get research project info"))
def research_projects(ctx: typer.Context,
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
        ),
        config: Annotated[
              Path,
              typer.Option(
                  hidden=True,
                  help=_("File to save the report"),
                  callback=dynamic_dynaconf_callback
              )
          ] = None,
):
    """
    Retrieve research projects from a Trapper instance and display them.

    :param ctx: Typer context.
    :type ctx: typer.Context
    :param url: Base URL of the Trapper server.
    :type url: str
    :param user: Username for authentication.
    :type user: str
    :param password: Password for the user (optional).
    :type password: str
    :param token: Access token (optional).
    :type token: str
    :param config: Internal configuration option (dynamic callback).
    :type config: pathlib.Path | None
    :raises Exception: If retrieval fails a fatal message is logged.
    """
    settings = ctx.obj.get("settings", {})

    try:
        rps = get_trapper_research_projects(url, user, password, None)
        data = [rp.model_dump() for rp in rps.results]
        TyperUtils.show_table(data, "Trapper Research Projects", fields=["pk", "acronym", "name"])
    except Exception as e:
        TyperUtils.fatal(_(f"Failed getting trapper research projects: {str(e)}"))


@app.command(help=_("Get locations info from trapper instance"), short_help=_("Get locations info"))
def locations(ctx: typer.Context,
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
        ),
        config: Annotated[
              Path,
              typer.Option(
                  hidden=True,
                  help=_("File to save the report"),
                  callback=dynamic_dynaconf_callback
              )
          ] = None,
):
    """
    Retrieve locations from a Trapper instance and display them.

    :param ctx: Typer context.
    :type ctx: typer.Context
    :param url: Base URL of the Trapper server.
    :type url: str
    :param user: Username for authentication.
    :type user: str
    :param password: Password for the user (optional).
    :type password: str
    :param token: Access token (optional).
    :type token: str
    :param config: Internal configuration option (dynamic callback).
    :type config: pathlib.Path | None
    :raises Exception: If retrieval fails a fatal message is logged.
    """
    settings = ctx.obj.get("settings", {})

    try:
        locs = get_trapper_locations(url, user, password, None)
        data = [cp.model_dump() for cp in locs.results]
        TyperUtils.show_table(data, "Trapper Locations")
    except Exception as e:
        TyperUtils.fatal(_(f"Failed getting trapper locations: {str(e)}"))