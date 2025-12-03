# python
"""
Utilities for interacting with Epicollect.

This module exposes Typer commands for interacting with Epicollect. Allow us to obtained project data and forms entries.

Functions
---------
dynaconf_loader(file_path: str) -> dict
    Load Dynaconf settings from a JSON string.
dynamic_dynaconf_callback(ctx, param, value)
    Inject runtime defaults into CLI parameters from project settings.
main_callback(ctx: typer.Context)
    Typer callback executed before any command.
check_collections(...)
    Validate collection and deployment folder naming and structure.
check_deployments(...)
    Validate deployments and image timestamp consistency.
prepare_for_trapper(...)
    Prepare collections for ingestion into Trapper.
_show_report(report, success_msg, error_msg, output)
    Render and persist a report in YAML format.
"""
import ast
import json
import os
import tempfile

from dynaconf import Dynaconf
from pydantic import BaseModel
from rich.progress import Progress, TextColumn, BarColumn, TimeElapsedColumn
from typer_config import conf_callback_factory
import logging

from wildintel_tools.epicollect import get_access_token, safe_call, get_all_entries, get_project_info, entries_to_csv, \
    group_entries_by_site_and_session, generate_field_sheet
from wildintel_tools.resouceutils import ResourceExtensionDTO
from wildintel_tools.ui.typer import EpicollectUtils
from wildintel_tools.ui.typer.i18n import _
from wildintel_tools.ui.typer.TyperUtils import TyperUtils, HierarchicalProgress
import wildintel_tools.wildintel as wildintel_processing
from typing_extensions import Annotated
from pathlib import Path
from typing import List, Dict, Tuple, Any

import typer

from wildintel_tools.ui.typer.settings import Settings, SettingsManager

app = typer.Typer(
    help=_("Includes several utilities to obtained tada froem a Epicollect project"),
    short_help=_("Utilities for managing Epicollect data"))

def make_dynaconf_callback(override_mapping: dict | None = None):
    def callback(ctx, param: typer.CallbackParam, value: Any):
        return TyperUtils.dynamic_dynaconf_callback(ctx, param, value, override_mapping=override_mapping)
    return callback

override_mapping = {
#    "client_id": ("EPICOLLECT", "client_id"),
#    "client_secret": ("EPICOLLECT", "client_secret"),
#    "app_slug": ("EPICOLLECT", "app_slug"),
}

callback_with_override = make_dynaconf_callback(override_mapping)

@app.callback()
def main_callback(ctx: typer.Context,
):
    """
    Typer callback executed before any command in this application.

    Use it to initialize or mutate shared values in ``ctx.obj`` such as
    ``settings``, ``setting_manager``, ``logger`` or ``project``.

    :param ctx: Typer context object.
    :type ctx: typer.Context
    :returns: None
    """
    pass

@app.command(
    help=_(
        "Show info of a public project"
    ),
    short_help=_("Show info of a public project")
)
def search_project(
    ctx: typer.Context,
    app_slug: Annotated[str, typer.Argument(help=_("Project slugs to process"))] = None,
    config: Annotated[
        Path, typer.Option(hidden=True, help=_("File to save the report"), callback=callback_with_override)
    ] = None,
):
    """
    Show info of a public project.

    :param ctx: Typer context (expects ``settings`` and ``logger`` in ``ctx.obj``).
    :type ctx: typer.Context
    :param app_slug: Optional list of project slugs to process.
    :type app_slug: list[str] | None
    :param config: Internal option supplied by Typer config callback.
    :type config: pathlib.Path | None
    :raises typer.BadParameter: If ``app_slug`` is missing or invalid.
    :returns: None
    """
    settings = ctx.obj.get("settings", {})
    logger = ctx.obj.get("logger", logging.getLogger(__name__))

    if app_slug is None:
        TyperUtils.fatal(_("At least one 'app_slug' must be provided"))

    import pyepicollect as pyep

    try:
        result =  safe_call(pyep.api.search_project,app_slug)

        if "errors" in result:
            raise Exception(result["errors"][0]["title"])

        try:
            project = result["data"][0]["project"]
        except (KeyError, IndexError, TypeError):
            raise Exception(_(f"No information found for the specified project slug {app_slug}"))

        EpicollectUtils.EpicollectUtils.show_public_project(project)

    except Exception as e:
        TyperUtils.fatal(_("An error occurred getting project info: {0}").format(str(e)))

@app.command(
    help=_(
        "Show info of a private project"
    ),
    short_help=_("Show info of a private project")
)
def get_project(
    ctx: typer.Context,
    app_slug: Annotated[str,
        typer.Argument(
            help=_("Project slugs to process")
        )
    ] = None,

    client_id: str = typer.Option(
        None,
        help=_("Client ID to authenticate with Epicollect server")
    ),
    client_secret: str = typer.Option(
        None,
        help=_("Client secret to authenticate with Epicollect server")
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
    Show info of a private project.

    :param ctx: Typer context (expects ``settings`` and ``logger`` in ``ctx.obj``).
    :type ctx: typer.Context
    :param app_slug: Optional list of project slugs to process.
    :type app_slug: list[str] | None
    :param client_id: Client ID to authenticate with Epicollect server.
    :param client_secret: Client secret to authenticate with Epicollect server.
    :param config: Internal option supplied by Typer config callback.
    :type config: pathlib.Path | None
    :raises typer.BadParameter: If ``data_path`` is missing or invalid.
    :returns: None
    """
    settings = ctx.obj.get("settings", {})
    logger = ctx.obj.get("logger", logging.getLogger(__name__))

    if app_slug is None:
        TyperUtils.fatal(_("At least one 'app_slug' must be provided"))

    try:
        token=get_access_token(client_id, client_secret,Path(TyperUtils.home) / (f"access_token_{app_slug}.json"))
        result = get_project_info(app_slug,token)
        if "errors" in result:
            raise Exception(result["errors"][0]["title"])
        EpicollectUtils.EpicollectUtils.show_private_project(result, title="[bold cyan]project[/]")
    except Exception as e:
        TyperUtils.fatal(_(f"Error retrieving project info {app_slug}: {str(e)}"))

@app.command(
    help=_(
        "Show all entries of a epicollect form"
    ),
    short_help=_("Show all entries of a epicollect form")
)
def get_entries(
    ctx: typer.Context,
    form_ref: Annotated[str, typer.Argument(help=_("Project slugs to process (sub-dirs in root data path)"))],
    app_slug: str = typer.Argument(None, help=_("Project slug")),
    client_id: str = typer.Option(None, help=_("Client ID to authenticate with Epicollect server")),
    client_secret: str = typer.Option(None, help=_("Client secret to authenticate with Epicollect server")),
    to_csv: Annotated[bool | None, typer.Option(help=_("Export results to CSV file."))] = None,
    csv_file: Annotated[
        Path | None, typer.Option(help=_("Csv filename. If not provided, a temporary .csv file is created."))
    ] = None,
    filters: Annotated[
        List[str] | None,
        typer.Option(help=_("Supports post-filters with expressions like: 4_Sitio==A01 4_Sitio==A01|A02")),
    ] = None,

    fields: Annotated[
        List[str] | None,
        typer.Option(help=_("Fields to show")),
    ] = None,

    config: Annotated[
        Path, typer.Option(hidden=True, help=_("File to save the report"), callback=callback_with_override)
    ] = None,
):
    """
    Get all entries of a epicollect form,

    :param ctx: Typer context (expects ``settings`` and ``logger`` in ``ctx.obj``).
    :type ctx: typer.Context
    :param form_ref: Form reference to process.
    :type form_ref: str | None
    :param app_slug: Project slug.
    :type app_slug: str | None
    :param client_id: Client ID to authenticate with Epicollect server.
    :param client_secret: Client secret to authenticate with Epicollect server.
    :param config: Internal option supplied by Typer config callback.
    :type config: pathlib.Path | None
    :raises typer.BadParameter: If ``data_path`` is missing or invalid.
    :returns: None
    """
    settings = ctx.obj.get("settings", {})
    logger = ctx.obj.get("logger", logging.getLogger(__name__))

    try:
        token = get_access_token(
            client_id, client_secret, Path(TyperUtils.home) / (f"access_token_app_{app_slug}.json")
        )
        result = get_all_entries(app_slug, form_ref, token, 1000, filters)

        if to_csv is not None:
            if csv_file is not None:
                output_path = Path(to_csv)
            else:
                fd, tmp_path = tempfile.mkstemp(prefix="entries_", suffix=".csv")
                Path(tmp_path).write_text("")  # Inicializa el archivo
                output_path = Path(tmp_path)

            # Exportar usando tu función
            entries_to_csv(result,output_path, fields=fields)

            TyperUtils.info(f"CSV exportado en: {output_path}")
        else:
            fields = fields if fields else ["4_Sitio", "2_Sesion", "5_Camara", "created_at", "10_SD"]
            TyperUtils.show_table(result, title="Results", fields=fields)
    except Exception as e:
        TyperUtils.fatal(_("Error retrieving form entries: {0}").format(str(e)))


@app.command(
    help=_(
        "Show all entries of a epicollect form"
    ),
    short_help=_("Show all entries of a epicollect form")
)
def entries_group_by_site(
    ctx: typer.Context,
    form_ref: Annotated[str, typer.Argument(help=_("Project slugs to process (sub-dirs in root data path)"))],
    app_slug: str = typer.Argument(None, help=_("Project slug")),
    client_id: str = typer.Option(None, help=_("Client ID to authenticate with Epicollect server")),
    client_secret: str = typer.Option(None, help=_("Client secret to authenticate with Epicollect server")),

    filters: Annotated[
        List[str] | None,
        typer.Option(help=_("Supports post-filters with expressions like: 4_Sitio==A01 4_Sitio==A01|A02")),
    ] = None,

    fields: Annotated[
        List[str] | None,
        typer.Option(help=_("Fields to show")),
    ] = None,

    session_field: Annotated[
        str,
        typer.Option(help=_("Field name to use as session identifier")),
    ] = "2_Sesion",

    site_field: Annotated[
        str,
        typer.Option(help=_("Field name to use as site identifier"))
    ] = "4_Sitio",

    config: Annotated[
        Path, typer.Option(hidden=True, help=_("File to save the report"), callback=callback_with_override)
    ] = None,
):
    """
    Get all entries of a epicollect form,

    :param ctx: Typer context (expects ``settings`` and ``logger`` in ``ctx.obj``).
    :type ctx: typer.Context
    :param form_ref: Form reference to process.
    :type form_ref: str | None
    :param app_slug: Project slug.
    :type app_slug: str | None
    :param client_id: Client ID to authenticate with Epicollect server.
    :param client_secret: Client secret to authenticate with Epicollect server.
    :param config: Internal option supplied by Typer config callback.
    :type config: pathlib.Path | None
    :raises typer.BadParameter: If ``data_path`` is missing or invalid.
    :returns: None
    """
    settings = ctx.obj.get("settings", {})
    logger = ctx.obj.get("logger", logging.getLogger(__name__))

    try:
        token = get_access_token(
            client_id, client_secret, Path(TyperUtils.home) / (f"access_token_app_{app_slug}.json")
        )

        if fields is not None:
            mandatory_fields = {session_field, site_field}
            fields = list(set(fields) | mandatory_fields)

        entries= get_all_entries(app_slug, form_ref, token, 1000, filters, fields)
        result =  group_entries_by_site_and_session(entries, {}, site_field, session_field)
        EpicollectUtils.EpicollectUtils.print_nested_entries(result)
    except Exception as e:
        TyperUtils.fatal(_("Error retrieving form entries: {0}").format(str(e)))

@app.command(
    help=_(
        "Remove auth tokens"
    ),
    short_help=_("Remove auth tokens")
)
def clean_tokens(
    ctx: typer.Context,
    app_slug: Annotated[
        str, typer.Argument(help=_("Project slugs to process"))
    ] = None,

    config: Annotated[
        Path, typer.Option(hidden=True, help=_("File to save the report"), callback=callback_with_override)
    ] = None,
):
    """
    Get all entries of a epicollect form,

    :param ctx: Typer context (expects ``settings`` and ``logger`` in ``ctx.obj``).
    :type ctx: typer.Context
    :param app_slug: Project slug.
    :type app_slug: str | None
    :param config: Internal option supplied by Typer config callback.
    :type config: pathlib.Path | None
    :raises typer.BadParameter: If ``data_path`` is missing or invalid.
    :returns: None
    """

    filename = Path(TyperUtils.home) / (f"access_token_app_{app_slug}.json")

    if filename.exists():
        filename.unlink()
        TyperUtils.success(f"Token {filename} was removed")
    else:
        TyperUtils.warning(f"Token {filename} noy found")


@app.command(
    help=_(
        "Generate field sheet"
    ),
    short_help=_("Generate field sheet")
)
def field_sheet(
    ctx: typer.Context,
    form_ref: Annotated[str, typer.Argument(help=_("Project slugs to process (sub-dirs in root data path)"))],
    app_slug: str = typer.Argument(None, help=_("Project slug")),
    client_id: str = typer.Option(None, help=_("Client ID to authenticate with Epicollect server")),
    client_secret: str = typer.Option(None, help=_("Client secret to authenticate with Epicollect server")),

    filters: Annotated[
        List[str] | None,
        typer.Option(help=_("Supports post-filters with expressions like: 4_Sitio==A01 4_Sitio==A01|A02")),
    ] = None,

    fields: Annotated[
        List[str] | None,
        typer.Option(help=_("Fields to show")),
    ] = None,

    session_field: Annotated[
        str,
        typer.Option(help=_("Field name to use as session identifier")),
    ] = "2_Sesion",

    site_field: Annotated[
        str,
        typer.Option(help=_("Field name to use as site identifier"))
    ] = "4_Sitio",

    config: Annotated[
        Path, typer.Option(hidden=True, help=_("File to save the report"), callback=callback_with_override)
    ] = None,

):
    """
    Get all entries of a epicollect form,

    :param ctx: Typer context (expects ``settings`` and ``logger`` in ``ctx.obj``).
    :type ctx: typer.Context
    :param app_slug: Project slug.
    :type app_slug: str | None
    :param config: Internal option supplied by Typer config callback.
    :type config: pathlib.Path | None
    :raises typer.BadParameter: If ``data_path`` is missing or invalid.
    :returns: None
    """
    try:
        token = get_access_token(
            client_id, client_secret, Path(TyperUtils.home) / (f"access_token_app_{app_slug}.json")
        )

        if fields is not None:
            mandatory_fields = {session_field, site_field}
            fields = list(set(fields) | mandatory_fields)

        entries= get_all_entries(app_slug, form_ref, token, 1000, filters, fields)
        result =  generate_field_sheet(entries, {}, site_field, session_field)
        TyperUtils.show_table(result, title="Field Sheet")

    except Exception as e:
        TyperUtils.fatal(_("Error retrieving form entries: {0}").format(str(e)))