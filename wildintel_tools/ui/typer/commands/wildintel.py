import tempfile
from functools import wraps

from rich.progress import Progress, TextColumn, BarColumn, TimeElapsedColumn

from wildintel_tools.resouceutils import ResourceExtensionDTO
from wildintel_tools.ui.typer.i18n import _
from wildintel_tools.ui.typer.TyperUtils import TyperUtils
from wildintel_tools.ui.typer.settings import SettingsManager
import wildintel_tools.wildintel as wildintel_processing
from typing_extensions import Annotated
from pathlib import Path
from typing import List


import typer

app = typer.Typer(
    help=_("Includes several utilities to validate and ensure the quality of collections and deployments produced within the WildIntel project"),
    short_help=_("Utilities for managing and validating WildIntel data"))

@app.callback()
def main_callback(ctx: typer.Context,
):
    """
    Esta función se ejecuta antes de cualquier comando.
    Puedes usarla para configurar el contexto global.
    """
    global settings

    settings = ctx.obj.get("settings")

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
    data_path: Annotated[
        Path,
        typer.Argument(

            help=_("Root data path"),
            exists=True,  # debe existir
            file_okay=False,  # no puede ser fichero
            dir_okay=True  # debe ser directorio
        )
    ] = ...,

    collections: Annotated[
        List[str],
        typer.Argument(
            help=_("Collections to process (sub-dirs in root data path)")
        )
    ] = None,

    report_file: Annotated[
         Path,
         typer.Option(
             help=_("File to save the report")
         )
    ] = None,

):
    project_name = ctx.obj.get("project")
    settings_manager: SettingsManager = ctx.obj.get("setting_manager")
    settings = settings_manager.load_settings(project_name)

    if data_path is not None:
        settings.update({"GENERAL.data_dir": data_path}, validate=False)

    settings.validators.validate()

    """for section, values in settings.as_dict().items():
        print(section, values)
       """

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
            nonlocal collection_tasks
            if event.startswith("collection_start:"):
                col_name = event.split(":", 1)[1]
                collection_tasks[col_name] = {
                    "task_collection": progress.add_task(f"Collection {col_name}", total=count),
                    "deployments": {}
                }
            elif event.startswith("deployment_start:"):
                _, col_name, dep_name, dep_total_str = event.split(":", 3)
                dep_total = int(dep_total_str)
                task_collection = collection_tasks[col_name]["task_collection"]
                # Crear la tarea para el deployment
                collection_tasks[col_name]["deployments"][dep_name] = progress.add_task(
                    f"  Deployment {dep_name}", total=dep_total
                )
            elif event.startswith("file_progress:"):
                _, col_name, dep_name = event.split(":", 2)
                task_dep = collection_tasks[col_name]["deployments"][dep_name]
                progress.advance(task_dep, count)
                progress.advance(collection_tasks[col_name]["task_collection"], count)

        report = wildintel_processing.check_collections(
                data_path=settings.GENERAL.data_dir,
                collections=collections,
                progress_callback=on_progress,
        )

    _show_report(report, output=report_file)

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
    data_path: Annotated[
        Path,
        typer.Argument(
            help=_("Root data path"),
            exists=True,  # debe existir
            file_okay=False,  # no puede ser fichero
            dir_okay=True  # debe ser directorio
        )
    ],

    collections: Annotated[
        str,
        typer.Argument(
            help=_("Collections to process (sub-dirs in root data path)")
        )
    ] = None,

    report_file: Annotated[
         Path,
         typer.Option(
             help=_("File to save the report")
         )
    ] = None,

    tolerance_hours: Annotated[
        int,
        typer.Option(
            help=_("Allowed time deviation (in hours) when comparing the first and last image timestamps "
    "against the expected deployment start and end times.")
        )
    ] = None,

    extensions: Annotated[
        List[ResourceExtensionDTO],
        typer.Option(
            help=_("File extension to process")
        )
    ] = None,
):
    project_name = ctx.obj.get("project")
    settings_manager: SettingsManager = ctx.obj.get("setting_manager")
    settings = settings_manager.load_settings(project_name)

    if tolerance_hours is None:
        tolerance_hours = settings.get("WILDINTEL.tolerance_hours", 1)

    TyperUtils.info(_("Checking deployments using tolerance hours: {0}").format(tolerance_hours))

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
                nonlocal collection_tasks
                if event.startswith("collection_start:"):
                    col_name = event.split(":", 1)[1]
                    collection_tasks[col_name] = {
                        "task_collection": progress.add_task(f"Collection {col_name}", total=count),
                        "deployments": {}
                    }
                elif event.startswith("deployment_start:"):
                    _, col_name, dep_name, dep_total_str = event.split(":", 3)
                    dep_total = int(dep_total_str)
                    task_collection = collection_tasks[col_name]["task_collection"]
                    # Crear la tarea para el deployment
                    collection_tasks[col_name]["deployments"][dep_name] = progress.add_task(
                        f"  Deployment {dep_name}", total=dep_total
                    )
                elif event.startswith("file_progress:"):
                    _, col_name, dep_name = event.split(":", 2)
                    task_dep = collection_tasks[col_name]["deployments"][dep_name]
                    progress.advance(task_dep, count)
                    progress.advance(collection_tasks[col_name]["task_collection"], count)

            report = wildintel_processing.check_deployments(
                    data_path=data_path,
                    collections=collections,
                    extensions=extensions,
                    progress_callback=on_progress,
                    tolerance_hours=tolerance_hours
            )
            _show_report(report, output=report_file)

    except Exception as e:
        TyperUtils.error(_("An error occurred during deployment checking: {0}").format(str(e)))


@app.command(
    help=_("Validate the internal structure of a collection by checking that all its deployments are correctly named, contain the expected files, and match their associated metadata. The validation also ensures that deployment folders correspond to the entries defined in the collection's CSV log and that image timestamps fall within the expected date ranges."),
    short_help=_("Validate the integrity and metadata of deployments in a collection."))
def prepare_for_trapper(
    ctx: typer.Context,
    data_path: Annotated[
        Path,
        typer.Argument(
            help=_("Root data path"),
            exists=True,  # debe existir
            file_okay=False,  # no puede ser fichero
            dir_okay=True  # debe ser directorio
        )
    ],

    output_path: Annotated[
        Path,
        typer.Argument(
            help=_("Root data path"),
            exists=True,  # debe existir
            file_okay=False,  # no puede ser fichero
            dir_okay=True  # debe ser directorio
        )
    ],

    collections: Annotated[
        List[str],
        typer.Argument(
            help=_("Collections to process (sub-dirs in root data path)")
        )
    ] = None,

    report_file: Annotated[
        Path,
        typer.Option(
            help=_("File to save the report")
        )
    ] = None,

    deployments: Annotated[
        List[str],
        typer.Option(
            help=_("Deployments to process (sub-dirs in collections path)")
        )
    ] = None,

    extensions: Annotated[
        List[ResourceExtensionDTO],
        typer.Option(
            help=_("File extension to process")
        )
    ] = None,

):
    project_name = ctx.obj.get("project")
    settings_manager: SettingsManager = ctx.obj.get("setting_manager")
    settings = settings_manager.load_settings(project_name)

    xmp_info = {
        "rp_name" : settings.wildintel.rp_name,
        "rp_description ": settings.wildintel.rp_description,
        "publisher" : settings.wildintel.publisher,
        "owner" : settings.wildintel.owner,
    }

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
            nonlocal collection_tasks
            if event.startswith("collection_start:"):
                col_name = event.split(":", 1)[1]
                collection_tasks[col_name] = {
                    "task_collection": progress.add_task(f"Collection {col_name}", total=count),
                    "deployments": {}
                }
            elif event.startswith("deployment_start:"):
                _, col_name, dep_name, dep_total_str = event.split(":", 3)
                dep_total = int(dep_total_str)
                task_collection = collection_tasks[col_name]["task_collection"]
                # Crear la tarea para el deployment
                collection_tasks[col_name]["deployments"][dep_name] = progress.add_task(
                    f"  Deployment {dep_name}", total=dep_total
                )
            elif event.startswith("file_progress:"):
                _, col_name, dep_name = event.split(":", 2)
                task_dep = collection_tasks[col_name]["deployments"][dep_name]
                progress.advance(task_dep, count)
            elif event.startswith("deployment_complete:"):
                col_name, dep_name = event.split(":")[1:3]
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

def _show_report(report, success_msg="Validation completed successfully", error_msg ="There were errors during the validation", output = None):
    if output is None:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".yaml")
        print(tmp)
        print(report)
        output = Path(tmp.name)
        print(output)
        TyperUtils.console.print(f"No output file specified. Using temporary file: {output}")

    if report.get_status() == "success":
        TyperUtils.success(_(f"{success_msg}. Review the report for details {output}."))
        TyperUtils.console.print(report.summary())
    else:
        TyperUtils.error(_(f"{error_msg}. Please check the report {output}."))

    report.to_yaml(output)
