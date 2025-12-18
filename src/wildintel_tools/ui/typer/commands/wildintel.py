# python
"""
Utilities for validating and preparing WildIntel collections and deployments.

This module exposes Typer commands to validate collection and deployment
naming, check image timestamp consistency, and prepare collections for
upload to Trapper.

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
import asyncio
import json
import tempfile
from collections import defaultdict
from zoneinfo import ZoneInfo

from dynaconf import Dynaconf
from rich.progress import Progress, TextColumn, BarColumn, TimeElapsedColumn
from trapper_client.TrapperClient import TrapperClient
from typer_config import conf_callback_factory
import logging

from wildintel_tools.http_uploader import HTTPUploader
from wildintel_tools.resouceutils import ResourceExtensionDTO
from wildintel_tools.trapper_package import DataPackageGeneratorParallel
from wildintel_tools.ui.typer.i18n import _
from wildintel_tools.ui.typer.TyperUtils import TyperUtils, HierarchicalProgress
import wildintel_tools.wildintel as wildintel_processing
from typing_extensions import Annotated
from pathlib import Path
from typing import List, Any, Iterable

import typer

app = typer.Typer(
    help=_("Includes several utilities to validate and ensure the quality of collections and deployments produced within the WildIntel project"),
    short_help=_("Utilities for managing and validating WildIntel data"))

def make_dynaconf_callback(override_mapping: dict | None = None):
    def callback(ctx, param: typer.CallbackParam, value: Any):
        return TyperUtils.dynamic_dynaconf_callback(ctx, param, value, override_mapping=override_mapping)
    return callback

override_mapping = {
    "data_path": ("GENERAL", "data_dir"),
    "tolerance_hours": ("WILDINTEL", "tolerance_hours"),
    "output_path": ("WILDINTEL", "output_dir"),
    "owner": ("WILDINTEL", "owner"),
    "publisher": ("WILDINTEL", "publisher"),
    "coverage": ("WILDINTEL", "coverage"),
    "rp_name": ("WILDINTEL", "rp_name"),
    "user": ("GENERAL", "login"),
    "url": ("GENERAL", "host"),
    "password": ("GENERAL", "password"),
    "timezone": ("WILDINTEL","timezone"),
    "ignore_dst": ("WILDINTEL","ignore_dst"),
    "convert_to_utc": ("WILDINTEL","convert_to_utc"),
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
        "Validates the names of collections and deployments within a given data directory. "
        "It checks that collection folders follow the 'RNNNN' format and that deployment folders "
        "use the '<COLLECTION>-<LOCATION>_<SUFFIX>' pattern. "
        "Reports errors and successes for each validation step."
    ),
    short_help=_("Validate collection and deployment folder naming conventions" + " (alias: cc)")
)
def check_collections(
    ctx: typer.Context,
    collections: Annotated[List[str],
        typer.Argument(
            help=_("Collections to process (sub-dirs in root data path)")
        )
    ] = None,
    data_path: Annotated[Path,
            typer.Option(
                help=_("Root data path"),
                exists=True,  # debe existir
                file_okay=False,  # no puede ser fichero
                dir_okay=True  # debe ser directorio
            )
        ] = None,

    report_file: Annotated[Path,
         typer.Option(
             help=_("File to save the report"),
         )
    ] = None,

    url: str = typer.Option(
        None,
        help=_("Base URL of the Trapper server (e.g., https://trapper.example.org)"),
    ),
    user: str = typer.Option(
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

    validate_locations: Annotated[bool, typer.Option(help=_("Check if locations are created in Trapper."))] = True,
    max_workers: Annotated[ int, typer.Option(help=_("Number of parallel threads to use ."))] = 4,

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
    Validate collection and deployment folder naming and basic structure.

    Performs checks over the collections found in ``data_path``, validating
    collection and deployment naming patterns and reporting progress.

    :param ctx: Typer context (expects ``settings`` and ``logger`` in ``ctx.obj``).
    :type ctx: typer.Context
    :param collections: Optional list of collection names to process.
    :type collections: list[str] | None
    :param data_path: Root directory that contains collections (must exist).
    :type data_path: pathlib.Path
    :param report_file: Path to write the validation report (YAML).
    :type report_file: pathlib.Path | None
    :param url: Trapper base URL (optional, used by the checker).
    :type url: str | None
    :param user: Username for Trapper authentication (optional).
    :type user: str | None
    :param password: Password for Trapper authentication (optional).
    :type password: str | None
    :param token: Access token for Trapper (optional).
    :type token: str | None
    :param config: Internal option supplied by Typer config callback.
    :type config: pathlib.Path | None
    :raises typer.BadParameter: If ``data_path`` is missing or invalid.
    :returns: None
    """
    settings = ctx.obj.get("settings", {})
    logger = ctx.obj.get("logger", logging.getLogger(__name__))

    if data_path is None or not data_path.exists() or not data_path.is_dir():
        raise typer.BadParameter(_(f"'--data_path': {data_path} is not a valid directory or does not exist."))

    TyperUtils.info(_(f"Checking collections in {data_path}"))

    try:
        import wildintel_tools.ui.typer.wildintel

        report = wildintel_tools.ui.typer.wildintel.check_collections(
                data_path=Path(data_path),
                collections=collections,
                url = url,
                user = user,
                password = password,
                validate_locations = validate_locations,
                max_workers=max_workers
        )

        _show_report(report, output=report_file)

    except Exception as e:
        TyperUtils.error(_("An error occurred during collection checking: {0}").format(str(e)))

app.command(name="cc", hidden=True, help=_("Alias for check_collections")) (check_collections)

@app.command(
    help=_(
        "Validates the structure and content of deployment folders within the specified collections. "
        "Checks that image files exist, follow the expected chronological order, and that their "
        "timestamps are within the expected start and end ranges. Also generates a '.validated' "
        "file for successfully verified deployments."
    ),
    short_help=_("Validate deployment folders and image timestamp consistency" + " (alias: cd)")
)
def check_deployments(
    ctx: typer.Context,
    collections: Annotated[List[str],typer.Argument(help=_("Collections to process (sub-dirs in root data path)"))] = None,
    data_path: Annotated[Path,typer.Option(help=_("Root data path"),exists=True, file_okay=False, dir_okay=True) ] = None,
    report_file: Annotated[Path,typer.Option(help=_("File to save the report"),)] = None,
    tolerance_hours: Annotated[int,
        typer.Option( help=_("Allowed time deviation (in hours) when comparing the first and last image timestamps "
                             "against the expected deployment start and end times."))] = None,
    extensions: Annotated[List[ResourceExtensionDTO],typer.Option(help=_("File extension to process"))] = None,
    max_workers: Annotated[int, typer.Option(help=_("Number of parallel threads to use ."))] = 4,
    deployments: Annotated[List[str],
        typer.Option(
            help=_("Deployments to process (sub-dirs in root data path)")
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
    Validate deployments inside collections and verify image timestamp consistency.

    Ensures that deployments contain the expected files and that image timestamps
    are ordered and fall within the expected ranges according to ``tolerance_hours``.

    :param ctx: Typer context (expects ``settings`` and ``logger`` in ``ctx.obj``).
    :type ctx: typer.Context
    :param collections: Optional list of collection names to process.
    :type collections: list[str] | None
    :param data_path: Root directory that contains collections (must exist).
    :type data_path: pathlib.Path
    :param report_file: Path to write the validation report (YAML).
    :type report_file: pathlib.Path | None
    :param tolerance_hours: Allowed time deviation (in hours) for timestamp checks.
    :type tolerance_hours: int | None
    :param extensions: Optional list of file extensions to include.
    :type extensions: list[ResourceExtensionDTO] | None
    :param config: Internal option supplied by Typer config callback.
    :type config: pathlib.Path | None
    :raises typer.BadParameter: If ``data_path`` is missing or invalid.
    :returns: None
    """
    settings = ctx.obj.get("settings", {})
    logger = ctx.obj.get("logger", logging.getLogger(__name__))

    if data_path is None or not data_path.exists() or not data_path.is_dir():
        raise typer.BadParameter(_(f"'--data_path': {data_path} is not a valid directory or does not exist."))

    TyperUtils.info(_(f"Checking deployments in {data_path} using tolerance hours {tolerance_hours}"))

    try:
        import wildintel_tools.ui.typer.wildintel

        report = wildintel_tools.ui.typer.wildintel.check_deployments(
            data_path=Path(data_path),
            collections=collections,
            deployments=deployments,
            extensions=extensions,
            tolerance_hours=tolerance_hours,
            max_workers=max_workers,
        )

        _show_report(report, output=report_file)

    except Exception as e:
        TyperUtils.error(_("An error occurred during deployment checking: {0}").format(str(e)))

app.command(name="cd", hidden=True, help=_("Alias for check_deployments")) (check_deployments)

@app.command(
    help=_("Validate the internal structure of a collection by checking that all its deployments are correctly named, contain the expected files, and match their associated metadata. The validation also ensures that deployment folders correspond to the entries defined in the collection's CSV log and that image timestamps fall within the expected date ranges."),
    short_help=_("Validate the integrity and metadata of deployments in a collection.") + " (alias: pt)")
def prepare_for_trapper(
    ctx: typer.Context,
    data_path: Annotated[
        Path, typer.Option(help=_("Root data path"), exists=True, file_okay=False, dir_okay=True)
    ] = None,
    output_path: Annotated[
        Path, typer.Option(help=_("Root output path"), exists=True, file_okay=False, dir_okay=True)
    ] = None,
    collections: Annotated[
        List[str], typer.Argument(help=_("Collections to process (sub-dirs in root data path)"))
    ] = None,
    report_file: Annotated[Path, typer.Option(help=_("File to save the report"))] = None,
    deployments: Annotated[
        List[str], typer.Option(help=_("Deployments to process (sub-dirs in collections path)"))
    ] = None,
    extensions: Annotated[List[ResourceExtensionDTO], typer.Option(help=_("File extension to process"))] = None,
    owner: Annotated[str, typer.Option(help=_("Resource owner"))] = None,
    publisher: Annotated[str, typer.Option(help=_("Resource publisher"))] = None,
    coverage: Annotated[str, typer.Option(help=_("Resource coverage"))] = None,
    rp_name: Annotated[str, typer.Option(help=_("Research project name"))] = None,
    scale: Annotated[bool, typer.Option(help=_("Scale resources"))] = True,
    overwrite: Annotated[bool, typer.Option(help=_("Overwrite existing deployments directories  in output path"))] = False,
    timezone :  Annotated[  str, typer.Option( help=_("Timezone to use for timestamp normalization (default: 'UTC')") ) ] = "UTC",
    ignore_dst: Annotated[ bool, typer.Option( help=_("Whether to ignore daylight saving time adjustments (default: True)") ) ] = True,
    convert_to_utc: Annotated[ bool, typer.Option( help=_("Whether to convert all timestamps to UTC (default: True)") ) ] = True,
    create_deployment_table: Annotated[ bool, typer.Option( help=_("Generate deployment table") )] = True,
    max_workers: Annotated[int, typer.Option(help=_("Number of parallel threads to use ."))] = 4,

        config: Annotated[
        Path, typer.Option(hidden=True, help=_("File to save the report"), callback=callback_with_override)
    ] = None,
):
    """
    Prepare collections for ingestion into Trapper.

    Verifies and normalizes collection and deployment structure, writes XMP
    metadata when required, and exports prepared artifacts into ``output_path``.
    Progress is reported via a callback.

    :param ctx: Typer context (expects ``settings`` and ``logger`` in ``ctx.obj``).
    :type ctx: typer.Context
    :param data_path: Root directory that contains collections (must exist).
    :type data_path: pathlib.Path
    :param output_path: Destination directory for prepared outputs (must exist).
    :type output_path: pathlib.Path
    :param collections: Optional list of collections to process.
    :type collections: list[str] | None
    :param report_file: Path to write the preparation report (YAML).
    :type report_file: pathlib.Path | None
    :param deployments: Optional list of deployment names to process.
    :type deployments: list[str] | None
    :param extensions: Optional list of file extensions to include.
    :type extensions: list[ResourceExtensionDTO] | None
    :param owner: Resource owner metadata to embed.
    :type owner: str | None
    :param publisher: Resource publisher metadata to embed.
    :type publisher: str | None
    :param coverage: Coverage metadata to embed.
    :type coverage: str | None
    :param rp_name: Research project name metadata to embed.
    :type rp_name: str | None
    :param scale: Whether to scale resources during preparation.
    :type scale: bool
    :param overwrite: Whether to overwrite existing output directories.
    :type overwrite: bool
    :param config: Internal option supplied by Typer config callback.
    :type config: pathlib.Path | None
    :raises typer.BadParameter: If ``data_path`` or ``output_path`` are missing or invalid.
    :returns: None
    """
    settings = ctx.obj.get("settings", {})
    logger = ctx.obj.get("logger", logging.getLogger(__name__))

    if data_path is None or not data_path.exists() or not data_path.is_dir():
        raise typer.BadParameter(_(f"'--data_path' is not a valid directory or does not exist."))
    if output_path is None or not output_path.exists() or not output_path.is_dir():
        raise typer.BadParameter(_(f"'--output_path' is not a valid directory or does not exist."))

    xmp_info = {
        "rp_name" : rp_name,
        "coverage": coverage,
        "publisher" : publisher,
        "owner" : owner,
    }

    try:
        TyperUtils.info(_(f"Preparing collections \"{",".join(collections) if collections else "All"}\" in {data_path} for Trapper into {output_path}"))

        import wildintel_tools.ui.typer.wildintel

        report = wildintel_tools.ui.typer.wildintel.prepare_collections_for_trapper(
            data_path = data_path,
            output_dir = output_path,
            collections = collections,
            deployments = deployments,
            extensions = extensions,
            max_workers = max_workers,
            xmp_info = xmp_info,
            scale_images = scale,
            overwrite = overwrite,
            create_deployment_table=create_deployment_table,
            timezone = ZoneInfo(timezone),
            ignore_dst= ignore_dst,
            convert_to_utc= convert_to_utc
        )

        TyperUtils.success(_("Preparation for Trapper completed. Collections are available in {0}").format(output_path))
        url = f"{str(settings.GENERAL.host)}geomap/deployment/import/"
        TyperUtils.info(_(f"Before continuing, import the deployments table file that was created per collection into {url}."))
        _show_report(report, output=report_file)
    except Exception as e:
        TyperUtils.error(_("An error occurred during preparing collections for trapper: {0}").format(str(e)))
app.command(name="pt", hidden=True, help=_("Alias for prepare_for_trapper")) (prepare_for_trapper)

@app.command(
    help=_("Generate trapper package."),
    short_help=_("Generate trapper package. (alias: ctp)"))
def create_trapper_package(
    ctx: typer.Context,
    data_path: Annotated[
        Path, typer.Option(help=_("Root data path"), exists=True, file_okay=False, dir_okay=True)
    ] = None,
    output_path: Annotated[
        Path, typer.Option(help=_("Root output path"), exists=True, file_okay=False, dir_okay=True)
    ] = None,
    collections: Annotated[
        List[str], typer.Argument(help=_("Collections to process (sub-dirs in root data path)"))
    ] = None,
    report_file: Annotated[Path, typer.Option(help=_("File to save the report"))] = None,
    deployments: Annotated[
        List[str], typer.Option(help=_("Deployments to process (sub-dirs in collections path)"))
    ] = None,
    extensions: Annotated[List[ResourceExtensionDTO], typer.Option(help=_("File extension to process"))] = None,
    project_id: Annotated[int, typer.Option(help=_("Classification project id"))] = None,
    overwrite: Annotated[
        bool, typer.Option(help=_("Overwrite existing deployments directories  in output path"))
    ] = False,
    timezone: Annotated[
        str, typer.Option(help=_("Timezone to use for timestamp normalization (default: 'UTC')"))
    ] = "UTC",
    ignore_dst: Annotated[
        bool, typer.Option(help=_("Whether to ignore daylight saving time adjustments (default: True)"))
    ] = False,

    max_workers: Annotated[int, typer.Option(help=_("Number of parallel threads to use ."))] = 4,
    max_zip_size: Annotated[int, typer.Option(help=_("Maximum size (in MB) for each zip file."))] = 2000,

    config: Annotated[
        Path, typer.Option(hidden=True, help=_("File to save the report"), callback=callback_with_override)
    ] = None,
):
    """
    Prepare collections for ingestion into Trapper.

    Verifies and normalizes collection and deployment structure, writes XMP
    metadata when required, and exports prepared artifacts into ``output_path``.
    Progress is reported via a callback.

    :param ctx: Typer context (expects ``settings`` and ``logger`` in ``ctx.obj``).
    :type ctx: typer.Context
    :param data_path: Root directory that contains collections (must exist).
    :type data_path: pathlib.Path
    :param output_path: Destination directory for prepared outputs (must exist).
    :type output_path: pathlib.Path
    :param collections: Optional list of collections to process.
    :type collections: list[str] | None
    :param report_file: Path to write the preparation report (YAML).
    :type report_file: pathlib.Path | None
    :param deployments: Optional list of deployment names to process.
    :type deployments: list[str] | None
    :param extensions: Optional list of file extensions to include.
    :type extensions: list[ResourceExtensionDTO] | None
    :param owner: Resource owner metadata to embed.
    :type owner: str | None
    :param publisher: Resource publisher metadata to embed.
    :type publisher: str | None
    :param coverage: Coverage metadata to embed.
    :type coverage: str | None
    :param rp_name: Research project name metadata to embed.
    :type rp_name: str | None
    :param scale: Whether to scale resources during preparation.
    :type scale: bool
    :param overwrite: Whether to overwrite existing output directories.
    :type overwrite: bool
    :param config: Internal option supplied by Typer config callback.
    :type config: pathlib.Path | None
    :raises typer.BadParameter: If ``data_path`` or ``output_path`` are missing or invalid.
    :returns: None
    """
    settings = ctx.obj.get("settings", {})
    logger = ctx.obj.get("logger", logging.getLogger(__name__))

    if data_path is None or not data_path.exists() or not data_path.is_dir():
        raise typer.BadParameter(_(f"'--data_path' is not a valid directory or does not exist."))
    if output_path is None or not output_path.exists() or not output_path.is_dir():
        raise typer.BadParameter(_(f"'--output_path' is not a valid directory or does not exist."))

    TyperUtils.debug(f"Creating trapper package with parameters: {output_path} {data_path} {collections} {extensions} {project_id} {timezone} {ignore_dst}")

    try:
        TyperUtils.info(_(f"Creating packages with collections \"{",".join(collections) if collections else "All"}\" in {output_path} for Trapper into {output_path}"))
        import wildintel_tools.ui.typer.wildintel

        report = wildintel_tools.ui.typer.wildintel.create_trapper_package(
            data_path = data_path,
            output_path = output_path,
            collections = collections,
            extensions = extensions,
            project_id = project_id,
            timezone = timezone,
            ignore_dst = ignore_dst,
            max_workers= max_workers,
            max_zip_size = max_zip_size,
            deployments = deployments,
            overwrite = overwrite,
        )

        TyperUtils.success(_("Trapper packages creation completed. Packages are available in {0}").format(output_path))
        _show_report(report, output=report_file)
    except Exception as e:
        TyperUtils.error(_("An error occurred during Trapper package creation: {0}").format(str(e)))
app.command(name="ctp", hidden=True, help=_("Alias for create_trapper_package")) (create_trapper_package)

@app.command(
    help=_("Generate trapper package. (alias: utp)"),
    short_help=_("Generate trapper package. (alias: utp)"))
def upload_trapper_package(
    ctx: typer.Context,
    output_path: Annotated[
        Path, typer.Option(help=_("Root output path"), exists=True, file_okay=False, dir_okay=True)
    ] = None,
    collections: Annotated[
        List[str], typer.Argument(help=_("Collections to process (sub-dirs in root data path)"))
    ] = None,
    report_file: Annotated[Path, typer.Option(help=_("File to save the report"))] = None,
    deployments: Annotated[
        List[str], typer.Option(help=_("Deployments to process (sub-dirs in collections path)"))
    ] = None,

    url: str = typer.Option(
        None,
        help=_("Base URL of the Trapper server (e.g., https://trapper.example.org)"),
    ),
    user: str = typer.Option(
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

    trigger: bool = typer.Option(
        True,
        help=_("Whether to trigger collection processing after upload")),

    remove_zip: bool = typer.Option(
        True,
        help=_("Whether to remove the uploaded zip file after processing")),

    config: Annotated[
        Path, typer.Option(hidden=True, help=_("File to save the report"), callback=callback_with_override)
    ] = None,
):
    settings = ctx.obj.get("settings", {})
    logger = ctx.obj.get("logger", logging.getLogger(__name__))

    if output_path is None or not output_path.exists() or not output_path.is_dir():
        raise typer.BadParameter(_(f"'--output_path' is not a valid directory or does not exist."))
    if collections is None:
        collections = [ col.name for col in output_path.iterdir() if col.is_dir() ]

    TyperUtils.debug(f"Uploading trapper package with parameters: {output_path}  {collections} ")

    try:
        TyperUtils.info(_(f"Uploading packages for collections {",".join(collections)} to Trapper"))

        trapper_client = TrapperClient(
            base_url=url, user_name=user, user_password=password, access_token=None
        )
        import wildintel_tools.ui.typer.wildintel
        report = wildintel_tools.ui.typer.wildintel.upload_trapper_package(
            trapper_client=trapper_client,
            output_path=output_path,
            collections=collections,
            deployments=deployments,
            trigger=trigger,
            remove_zip=remove_zip,
        )

        TyperUtils.success(_(f"Uploading packages to Trapper completed. Collections are available in {url}storage/collection/list/"))
        _show_report(report, output=report_file)
    except Exception as e:
        TyperUtils.error(_("An error occurred during uploading collections fot trapper: {0}").format(str(e)))
app.command(name="utp", hidden=True, help=_("Alias for upload_trapper_package")) (upload_trapper_package)


@app.command(
    help=_("Run a pipeline of check collections, check deployments, and prepare for trapper steps."),
    short_help=_("Run a pipeline of check collections, check deployments, and prepare for trapper steps."))
def pipeline(
    ctx: typer.Context,
    data_path: Annotated[ Path, typer.Option( help=_("Root data path"), exists=True,  file_okay=False,  dir_okay=True ) ]=None,
    output_path: Annotated[ Path,typer.Option(help=_("Root output path"),exists=True,file_okay=False,  dir_okay=True)] = None,
    collections: Annotated[ List[str], typer.Argument(help=_("Collections to process (sub-dirs in root data path)"))] = None,
    deployments: Annotated[List[str], typer.Option( help=_("Deployments to process (sub-dirs in collections path)"))] = None,
    extensions: Annotated[List[ResourceExtensionDTO], typer.Option(help=_("File extension to process"))] = None,
    owner: Annotated[str, typer.Option(help=_("Resource owner"))] = None,
    publisher: Annotated[str, typer.Option(help=_("Resource publisher"))] = None,
    coverage: Annotated[str, typer.Option( help=_("Resource publisher") ) ] = None,
    rp_name: Annotated[str, typer.Option( help=_("Research project name") ) ] = None,
    tolerance_hours: Annotated[int,
    typer.Option(help=_("Allowed time deviation (in hours) when comparing the first and last image timestamps "
                        "against the expected deployment start and end times."))] = None,

    url: str = typer.Option(
        None,
        help=_("Base URL of the Trapper server (e.g., https://trapper.example.org)"),
    ),
    user: str = typer.Option(
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

    validate_locations: Annotated[bool, typer.Option(help=_("Check if locations are created in Trapper."))] = True,
    max_workers: Annotated[int, typer.Option(help=_("Number of parallel threads to use ."))] = 4,
    timezone :  Annotated[  str, typer.Option( help=_("Timezone to use for timestamp normalization (default: 'UTC')") ) ] = "UTC",
    ignore_dst: Annotated[ bool, typer.Option( help=_("Whether to ignore daylight saving time adjustments (default: True)") ) ] = True,
    convert_to_utc: Annotated[ bool, typer.Option( help=_("Whether to convert all timestamps to UTC (default: True)") ) ] = True,
    create_deployment_table: Annotated[ bool, typer.Option( help=_("Generate deployment table") )] = True,

    config: Annotated[
    Path,
    typer.Option(
        hidden=True,
        help=_("File to save the report"),
        callback=callback_with_override
    )
    ] = None,
):
    if not collections:
        collections = [entry.name for entry in data_path.iterdir() if entry.is_dir()]
    else:
        collections = [entry.name for entry in data_path.iterdir() if entry.is_dir() and entry.name in collections]

    for col in collections:
        TyperUtils.info(_(f"Processing collection: {col}"))

        import wildintel_tools.ui.typer.wildintel

        report = wildintel_tools.ui.typer.wildintel.check_collections(
            data_path=Path(data_path),
            url = url,
            user = user,
            password = password,
            collections = [col],
            validate_locations = validate_locations,
            max_workers = max_workers)

        _show_report(success_msg=f"Collection {col} passed validation. Proceeding to deployment checks.",
                     error_msg=f"Collection {col} failed validation. Check the report for details. Skipping deployment checks.",
                     report=report)

        if report.is_success():
            col_path = data_path / col
            log_file = col_path / f"{col}_FileTimestampLog.csv"

            if log_file.exists():
                TyperUtils.success(_(f"Read FileTimestampLog fom collection {col}."))

                import wildintel_tools.wildintel
                deployments_csv = wildintel_tools.wildintel._read_field_notes_log(log_file)

                if deployments:
                    deployments_csv = [d for d in deployments_csv if d["name"] in deployments]

                for deployment in deployments_csv:
                    TyperUtils.info(_(f"Processing deployment: {deployment['name']}"))
                    report_deplo = wildintel_tools.ui.typer.wildintel.check_deployments(
                        data_path=Path(data_path),
                        collections=[col],
                        deployments=deployment['name'],
                        extensions=extensions,
                        tolerance_hours=tolerance_hours,
                        max_workers=max_workers,
                    )
                    _show_report(
                        success_msg=_(f"Deployment {deployment['name']} in collection {col} passed validation"),
                        error_msg=_(f"Deployment {deployment['name']} in collection {col} failed preparation for Trapper. Skipping prepare deployment for trapper"),
                        report=report_deplo,
                    )
                    if report_deplo.is_success():
                        TyperUtils.info(_(f"Processing to prepare Deployment {deployment['name']} in collection {col} for trapper."))

                        report_prep = wildintel_tools.ui.typer.wildintel.prepare_collections_for_trapper(
                            data_path=data_path,
                            output_dir=output_path,
                            collections=[col],
                            deployments=[deployment['name']],
                            extensions=extensions,
                            max_workers = max_workers,
                            xmp_info = {
                                "rp_name" : rp_name,
                                "coverage": coverage,
                                "publisher" : publisher,
                                "owner" : owner,
                            },
                            scale_images=True,
                            overwrite=True,
                            create_deployment_table=create_deployment_table,
                            timezone=ZoneInfo(timezone),
                            ignore_dst=ignore_dst,
                            convert_to_utc=convert_to_utc,
                        )
                        _show_report(
                            success_msg=_(f"Deployment {deployment['name']} in collection {col} prepared successfully for Trapper"),
                            error_msg=_(f"Deployment {deployment['name']} in collection {col} failed preparation for Trapper"),
                            report=report_prep)
            else:
                TyperUtils.error(_(f"Log file {log_file} not found in collection {col}. Skipping deployment checks."))

def _show_report(report:"Report", success_msg="Validation completed successfully", error_msg ="There were errors during the validation", output = None):
    """
    Render a report result to console and optionally save it to a YAML file.

    If ``output`` is not provided a temporary YAML file is created in the default
    report directory. Prints a success or error message according to the report status
    and always persists the report to ``output``.

    :param report: Report object with ``get_status``, ``to_yaml`` and ``summary`` methods.
    :type report: Any
    :param success_msg: Message to show on success.
    :type success_msg: str
    :param error_msg: Message to show on failure.
    :type error_msg: str
    :param output: Optional path to write the report YAML; if omitted a temp file is created.
    :type output: pathlib.Path | None
    :returns: None
    """
    if output is None:
        base_dir=TyperUtils.get_default_report_dir()
        Path.mkdir(base_dir, parents=True, exist_ok=True)
        tmp = tempfile.NamedTemporaryFile(delete=False, dir=base_dir, prefix="report_", suffix=".yaml")
        output = Path(tmp.name)
        TyperUtils.debug(f"No output file specified. Using temporary file: {output}")
    if report.get_status() == "success":
        TyperUtils.success(_(f"{success_msg}. Review the report for details {output}."))
    else:
        TyperUtils.console.print(report.summary())
        TyperUtils.error(_(f"{error_msg}. Review the report for details {output}."))

    report.to_yaml(output)