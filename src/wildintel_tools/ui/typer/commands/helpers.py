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
from typing import Annotated, Any
from typer_config import conf_callback_factory
from wildintel_tools.ui.typer.i18n import _
from wildintel_tools.ui.typer.TyperUtils import TyperUtils
from wildintel_tools.ui.typer.settings import SettingsManager

from wildintel_tools.helpers import (
    check_ffmpeg,
    check_exiftool,
    check_trapper_connection,
    get_trapper_classification_projects,
    get_trapper_research_projects,
    get_trapper_locations, get_trapper_deployments
)

import typer

app = typer.Typer(
    help=_("Helpers"),
    short_help=_("Helpers")
)

def make_dynaconf_callback(override_mapping: dict | None = None):
    def callback(ctx, param: typer.CallbackParam, value: Any):
        return TyperUtils.dynamic_dynaconf_callback(ctx, param, value, override_mapping=override_mapping)
    return callback

override_mapping = {
    "user": ("GENERAL", "login"),
    "url": ("GENERAL", "host"),
    "password": ("GENERAL", "password"),
}

callback_with_override = make_dynaconf_callback(override_mapping)

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


@app.command(help=_("Test connection to Trapper server (API)") + " (alias: tc)",
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

                    project_id : Annotated[
                        int,
                        typer.Option(
                            help=_("Classification project ID to test the connection against")
                        )
                    ] = None,

                    config: Annotated[
                        Path,
                        typer.Option(
                            hidden=True,
                            help=_("File to save the report"),
                            callback=callback_with_override
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
        TyperUtils.info(_(f"Testing Trapper API connection {url} {user} {project_id}..."))
        check_trapper_connection(url, user, password, None, project_id)
        TyperUtils.success(_("Trapper API connection successful!"))
    except Exception as e:
        TyperUtils.fatal(_(f"Failed to connect to Trapper API. Check your settings: {str(e)}"))

app.command(name="tc", hidden=True, help=_("Alias for test_connection ")) (test_connection)

@app.command(help=_("Test the availability of FFMPEG & exiftool") + " (alias: tet)",
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
    settings = ctx.obj.get("settings")

    try:
        TyperUtils.logger.info(_("Testing FFMPEG"))
        check_ffmpeg(settings.GENERAL.ffmpeg)
        TyperUtils.success(_("FFMPEG test successful!"))
    except Exception as e:
        TyperUtils.error(_(f"FFMPEG test failed: {str(e)}"))

    try:
        TyperUtils.logger.info(_("Testing exiftool."))
        check_exiftool(settings.GENERAL.exiftool)
        TyperUtils.success(_("exiftool test successful!"))
    except Exception as e:
        TyperUtils.error(_(f"exiftool test failed: {str(e)}"))

app.command(name="tet", hidden=True, help=_("Alias for test_external_tools ")) (test_external_tools)

@app.command(help=_("Get classification project info from trapper instance") + " (alias: cp)",
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
                callback=callback_with_override
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

app.command(name="cp", hidden=True, help=_("Alias for classification_projects ")) (classification_projects)

@app.command(help=_("Get research project info from trapper instance") + " (alias: rp)", short_help=_("Get research project info"))
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
                  callback=callback_with_override
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

app.command(name="rp", hidden=True, help=_("Alias for research_projects ")) (research_projects)

@app.command(help=_("Get locations info from trapper instance") + " (alias: loc)", short_help=_("Get locations info"))
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
                  callback=callback_with_override
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
        TyperUtils.show_table(data, "Trapper Locations"
                              , fields=["pk", "location_id", "research_project", "timezone", "ignoreDST", "coordinates"], )
    except Exception as e:
        TyperUtils.fatal(_(f"Failed getting trapper locations: {str(e)}"))

app.command(name="loc", hidden=True, help=_("Alias for locations ")) (locations)

@app.command(help=_("Get deployments info from trapper instance") + " (alias: dep)", short_help=_("Get deployments info"))
def deployments(ctx: typer.Context,
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
                  callback=callback_with_override
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
        locs = get_trapper_deployments(url, user, password, None)
        data = [cp.model_dump() for cp in locs.results]
        TyperUtils.show_table(data, "Trapper Deployments",
                        fields=["pk", "deployment_id", "research_project", "location", "location_id", "start_date", "end_date"], )
    except Exception as e:
        TyperUtils.fatal(_(f"Failed getting trapper deployments: {str(e)}"))

app.command(name="dep", hidden=True, help=_("Alias for deployments ")) (deployments)