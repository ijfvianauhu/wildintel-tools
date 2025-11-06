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

import json
import tempfile

from dynaconf import Dynaconf
from rich.progress import Progress, TextColumn, BarColumn, TimeElapsedColumn
from typer_config import conf_callback_factory
import logging
from wildintel_tools.resouceutils import ResourceExtensionDTO
from wildintel_tools.ui.typer.i18n import _
from wildintel_tools.ui.typer.TyperUtils import TyperUtils, HierarchicalProgress
import wildintel_tools.wildintel as wildintel_processing
from typing_extensions import Annotated
from pathlib import Path
from typing import List

import typer

app = typer.Typer(
    help=_("Includes several utilities to validate and ensure the quality of collections and deployments produced within the WildIntel project"),
    short_help=_("Utilities for managing and validating WildIntel data"))

# 🔹 Loader que recibe la ruta completa del archivo
def dynaconf_loader(file_path: str) -> dict:
    """
    Load a Dynaconf-compatible configuration from a JSON string.

    Note:
        Although its name suggests a path loader, this function expects a JSON
        string and returns a Python ``dict`` usable by ``typer_config`` and Dynaconf.

    :param file_path: JSON string containing the configuration.
    :type file_path: str
    :returns: Parsed configuration dictionary.
    :rtype: dict
    :raises json.JSONDecodeError: If the input is not valid JSON.
    """
    return json.loads(file_path)

# 🔹 Callback base
base_conf_callback = conf_callback_factory(dynaconf_loader)

# 🔹 Callback dinámico que usa otro parámetro (base_path)
def dynamic_dynaconf_callback(ctx, param, value):
    """
    Dynamic callback that injects runtime defaults into Typer parameters.

    Serializes the runtime settings from ``ctx.obj["settings"]`` and delegates
    loading to the base configuration callback. It also fills CLI parameters
    when omitted by the user, using project settings:
    ``data_path``, ``tolerance_hours``, ``output_path``, ``owner``, ``publisher``,
    ``coverage``, ``rp_name``, ``user``, ``url`` y ``password``.

    :param ctx: Typer/Click context.
    :type ctx: typer.Context
    :param param: Parameter associated with the callback.
    :type param: click.Parameter
    :param value: Current value of the processed parameter.
    :type value: Any
    :returns: Result of the underlying base configuration callback.
    :rtype: Any
    """
    settings : Dynaconf = ctx.obj.get("settings", {}).as_dict()
    json_str = json.dumps(settings, default=str)
    a=base_conf_callback(ctx, param, json_str)

    settings = ctx.default_map.copy() if ctx.default_map else {}

    for key, value in ctx.params.items():
        if key == "data_path":
            if value is None:
                ctx.params[key] = settings["GENERAL"]["data_dir"]
        elif key == "tolerance_hours":
            if value is None:
                ctx.params[key] = settings["WILDINTEL"]["tolerance_hours"]
        elif key == "output_path":
            if value is None:
                ctx.params[key] = settings["WILDINTEL"]["output_dir"]
        elif key == "owner":
            if value is None:
                ctx.params[key] = settings["WILDINTEL"]["owner"]
        elif key == "publisher":
            if value is None:
                ctx.params[key] = settings["WILDINTEL"]["publisher"]
        elif key == "coverage":
            if value is None:
                ctx.params[key] = settings["WILDINTEL"]["coverage"]
        elif key == "rp_name":
            if value is None:
                ctx.params[key] = settings["WILDINTEL"]["rp_name"]
        elif key == "user":
            if value is None:
                ctx.params[key] = settings["GENERAL"]["login"]
        elif key == "url":
            if value is None:
                ctx.params[key] = settings["GENERAL"]["host"]
        elif key == "password":
            if value is None:
                ctx.params[key] = settings["GENERAL"]["password"]

    return a

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
    short_help=_("Validate collection and deployment folder naming conventions")
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
         callback=dynamic_dynaconf_callback
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

        with Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            "[progress.percentage]{task.percentage:>3.0f}%",
            TimeElapsedColumn(),
        ) as progress:
            collection_tasks = {}

            # Callback que la función llamará
            def on_progress(event: str, count: int):
                """
                Progress callback used to render nested progress bars.

                The event string indicates the stage:
                ``collection_start:<COLLECTION>``, ``deployment_start:<COLLECTION>:<DEPLOYMENT>:<TOTAL>``,
                ``file_progress:<COLLECTION>:<DEPLOYMENT>``.

                :param event: Event identifier with context tokens.
                :type event: str
                :param count: Amount of progress to advance.
                :type count: int
                :returns: None
                """
                nonlocal collection_tasks
                if event.startswith("collection_start:"):
                    _, col_name = event.split(":", 1)
                    collection_tasks[col_name] = {
                        "task_collection": progress.add_task(f"Collection {col_name}", total=count),
                        "deployments": {}
                    }
                elif event.startswith("deployment_start:"):
                    _, col_name, dep_name = event.split(":", 2)
                    collection_tasks[col_name]["deployments"][dep_name] = progress.add_task(
                        f"  Deployment {dep_name}", total=count
                    )
                elif event.startswith("file_progress:"):
                    _, col_name, dep_name, filename = event.split(":", 3)
                    task_dep = collection_tasks[col_name]["deployments"][dep_name]
                    progress.advance(task_dep, count)
                    progress.advance(collection_tasks[col_name]["task_collection"], count)
                elif event.startswith("deployment_complete:"):
                    _,col_name, dep_name = event.split(":", 2)
                    progress.advance(collection_tasks[col_name]["task_collection"], 1)

            report = wildintel_processing.check_collections(
                    data_path=Path(data_path),
                    collections=collections,
                    url = url,
                    user = user,
                    password = password,
                    validate_locations = validate_locations,
                    max_workers=max_workers,
                    progress_callback=on_progress,
            )

        _show_report(report, output=report_file)
    except Exception as e:
        TyperUtils.error(_("An error occurred during collection checking: {0}").format(str(e)))

@app.command(
    help=_(
        "Validates the structure and content of deployment folders within the specified collections. "
        "Checks that image files exist, follow the expected chronological order, and that their "
        "timestamps are within the expected start and end ranges. Also generates a '.validated' "
        "file for successfully verified deployments."
    ),
    short_help=_("Validate deployment folders and image timestamp consistency")
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
            callback=dynamic_dynaconf_callback
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
        with Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            "[progress.percentage]{task.percentage:>3.0f}%",
            TimeElapsedColumn(),
        ) as progress:

            # Mapa para almacenar tareas de colecciones y deployments
            collection_tasks = {}

            # Callback que la función llamará
            def on_progress(event: str, count: int):
                """
                Progress callback used to render nested progress bars.

                Event forms:
                ``collection_start:<COLLECTION>``, ``deployment_start:<COLLECTION>:<DEPLOYMENT>:<TOTAL>``,
                ``file_progress:<COLLECTION>:<DEPLOYMENT>``, ``deployment_complete:<COLLECTION>:<DEPLOYMENT>``.
                """
                nonlocal collection_tasks
                if event.startswith("collection_start:"):
                    _, col_name = event.split(":", 1)
                    if col_name not in collection_tasks:
                        collection_tasks[col_name] = {
                            "task_collection": progress.add_task(f"Collection {col_name}", total=count),
                            "deployments": {}
                        }
                elif event.startswith("deployment_start:"):
                    _, col_name, dep_name  = event.split(":", 2)
                    collection_tasks[col_name]["deployments"][dep_name] = progress.add_task(
                        f"  Deployment {dep_name}", total=count
                    )
                elif event.startswith("file_progress:"):
                    _, col_name, dep_name, file_name = event.split(":", 3)
                    task_dep = collection_tasks[col_name]["deployments"][dep_name]
                    progress.advance(task_dep, count)
                elif event.startswith("deployment_complete:"):
                    _, col_name, dep_name = event.split(":",2)
                    progress.advance(collection_tasks[col_name]["task_collection"], 1)

            report = wildintel_processing.check_deployments(
                    data_path=Path(data_path),
                    collections=collections,
                    extensions=extensions,
                    progress_callback=on_progress,
                    max_workers=max_workers,
                    tolerance_hours=tolerance_hours,
                    deployments=deployments
            )
        _show_report(report, output=report_file)

    except Exception as e:
        raise e
        TyperUtils.error(_("An error occurred during deployment checking: {0}").format(str(e)))

@app.command(
    help=_("Validate the internal structure of a collection by checking that all its deployments are correctly named, contain the expected files, and match their associated metadata. The validation also ensures that deployment folders correspond to the entries defined in the collection's CSV log and that image timestamps fall within the expected date ranges."),
    short_help=_("Validate the integrity and metadata of deployments in a collection."))
def prepare_for_trapper(
    ctx: typer.Context,
    data_path: Annotated[ Path, typer.Option( help=_("Root data path"), exists=True,  file_okay=False,  dir_okay=True ) ]=None,
    output_path: Annotated[ Path,typer.Option(help=_("Root output path"),exists=True,file_okay=False,  dir_okay=True)] = None,
    collections: Annotated[ List[str], typer.Argument(help=_("Collections to process (sub-dirs in root data path)"))] = None,
    report_file: Annotated[Path, typer.Option(help=_("File to save the report"))] = None,
    deployments: Annotated[List[str], typer.Option( help=_("Deployments to process (sub-dirs in collections path)"))] = None,
    extensions: Annotated[List[ResourceExtensionDTO], typer.Option(help=_("File extension to process"))] = None,
    owner: Annotated[str, typer.Option(help=_("Resource owner"))] = None,
    publisher: Annotated[str, typer.Option(help=_("Resource publisher"))] = None,
    coverage: Annotated[str, typer.Option( help=_("Resource publisher") ) ] = None,
    rp_name: Annotated[str, typer.Option( help=_("Research project name") ) ] = None,

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
        with Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            "[progress.percentage]{task.percentage:>3.0f}%",
            TimeElapsedColumn(),
        ) as progress:

            # Mapa para almacenar tareas de colecciones y deployments
            collection_tasks = {}

            def on_progress(event: str, count: int):
                """
                Progress callback used to render nested progress bars.

                Event forms:
                ``collection_start:<COLLECTION>``, ``deployment_start:<COLLECTION>:<DEPLOYMENT>:<TOTAL>``,
                ``file_progress:<COLLECTION>:<DEPLOYMENT>``, ``deployment_complete:<COLLECTION>:<DEPLOYMENT>``.
                """
                nonlocal collection_tasks
                if event.startswith("collection_start:"):
                    _,col_name = event.split(":", 1)
                    collection_tasks[col_name] = {
                        "task_collection": progress.add_task(f"Collection {col_name}", total=count),
                        "deployments": {}
                    }
                elif event.startswith("deployment_start:"):
                    _, col_name, dep_name = event.split(":", 2)
                    collection_tasks[col_name]["deployments"][dep_name] = progress.add_task(
                        f"  Deployment {dep_name}", total=count
                    )
                elif event.startswith("file_progress:"):
                    _, col_name, dep_name, file_name = event.split(":", 3)
                    task_dep = collection_tasks[col_name]["deployments"][dep_name]
                    progress.advance(task_dep, count)
                elif event.startswith("deployment_complete:"):
                    _, col_name, dep_name = event.split(":", 2)
                    progress.advance(collection_tasks[col_name]["task_collection"], 1)

            report = wildintel_processing.prepare_collections_for_trapper(
                    data_path=data_path,
                    output_dir=output_path,
                    collections=collections,
                    extensions=extensions,
                    deployments=deployments,
                    progress_callback=on_progress,
                    max_workers = 4,
                    xmp_info = xmp_info
            )

        _show_report(report, output=report_file)
    except Exception as e:
        TyperUtils.error(_("An error occurred during preparing collections fot trapper: {0}").format(str(e)))

@app.command(
    help=_("Run a pipeline of check collections, check deployments, and prepare for trapper steps."),
    short_help=_("Run a pipeline of check collections, check deployments, and prepare for trapper steps."))
def pipeline(
    ctx: typer.Context,
    data_path: Annotated[ Path, typer.Option( help=_("Root data path"), exists=True,  file_okay=False,  dir_okay=True ) ]=None,
    output_path: Annotated[ Path,typer.Option(help=_("Root output path"),exists=True,file_okay=False,  dir_okay=True)] = None,
    collections: Annotated[ List[str], typer.Argument(help=_("Collections to process (sub-dirs in root data path)"))] = None,
    report_file: Annotated[Path, typer.Option(help=_("File to save the report"))] = None,
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

    config: Annotated[
    Path,
    typer.Option(
        hidden=True,
        help=_("File to save the report"),
        callback=dynamic_dynaconf_callback
    )
    ] = None,
):
    check_collections(ctx, collections,data_path, report_file, url, user,
            password,
            token,
            validate_locations,
            max_workers,
            config)

    check_deployments(
            ctx,
            collections,
            data_path,
            report_file,
            tolerance_hours,
            extensions,
            max_workers,
            config
    )

    prepare_for_trapper(ctx,data_path, output_path, collections, report_file, deployments, extensions,owner,publisher, coverage,
    rp_name, config)

def _show_report(report, success_msg="Validation completed successfully", error_msg ="There were errors during the validation", output = None):
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
        TyperUtils.console.print(f"No output file specified. Using temporary file: {output}")
    if report.get_status() == "success":
        TyperUtils.success(_(f"{success_msg}. Review the report for details {output}."))
        TyperUtils.console.print(report.summary())
    else:
        TyperUtils.error(_(f"{error_msg}. Please check the report {output}."))

    report.to_yaml(output)