import asyncio
from asyncio import Runner
from collections import defaultdict
from pathlib import Path
from typing import List, Iterable, Callable
from zoneinfo import ZoneInfo

from rich.progress import Progress, TextColumn, BarColumn, TimeElapsedColumn, TaskProgressColumn
from trapper_client.TrapperClient import TrapperClient

from wildintel_tools.reports import Report
from wildintel_tools.resouceutils import ResourceExtensionDTO
from wildintel_tools.ui.typer.TyperUtils import TyperUtils
import wildintel_tools.wildintel

def check_collections(
    data_path: Path,
    url:str,
    user:str,
    password:str,
    collections: List[str] = [],
    validate_locations: bool = True,
    max_workers: int = 4,
    show_progress: bool = True,
) -> Report:

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

        report = wildintel_tools.wildintel.check_collections(
                data_path=Path(data_path),
                collections=collections,
                url = url,
                user = user,
                password = password,
                validate_locations = validate_locations,
                max_workers=max_workers,
                progress_callback=on_progress if show_progress else None,
        )

    return report

def check_deployments(
        data_path: Path,
        collections: List[str] = None,
        deployments: List[str] = None,
        extensions: List[ResourceExtensionDTO] = None,
        tolerance_hours: int = 1,
        max_workers:int =4,
        show_progress: bool = True,
) -> Report:
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

        report = wildintel_tools.wildintel.check_deployments(
            data_path=Path(data_path),
            collections=collections,
            extensions=extensions,
            progress_callback=on_progress if show_progress else None,
            max_workers=max_workers,
            tolerance_hours=tolerance_hours,
            deployments=deployments
        )

    return report

def prepare_collections_for_trapper(
    data_path: Path,
    output_dir: Path,
    collections: list[str] = None,
    deployments: list[str] = None,
    extensions: list[ResourceExtensionDTO] = None,
    max_workers: int = 4,
    xmp_info : dict = None,
    scale_images: bool = True,
    overwrite: bool = False,
    create_deployment_table: bool = True,
    timezone: ZoneInfo = ZoneInfo("UTC"),
    ignore_dst=True,
    convert_to_utc= True,
    show_progress: bool = True,

) -> Report:
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
                _, col_name, dep_name, file_name = event.split(":", 3)
                task_dep = collection_tasks[col_name]["deployments"][dep_name]
                progress.advance(task_dep, count)
            elif event.startswith("deployment_complete:"):
                _, col_name, dep_name = event.split(":", 2)
                progress.advance(collection_tasks[col_name]["task_collection"], 1)

        return wildintel_tools.wildintel.prepare_collections_for_trapper(
                data_path=data_path,
                output_dir=output_dir,
                collections=collections,
                deployments=deployments,
                extensions=extensions,
                progress_callback=on_progress if show_progress else None,
                max_workers=max_workers,
                xmp_info=xmp_info,
                scale_images=scale_images,
                overwrite=overwrite,
                create_deployment_table=create_deployment_table,
                timezone=timezone,
                ignore_dst=ignore_dst,
                convert_to_utc=convert_to_utc
        )

def create_trapper_package(
    data_path : Path,
    output_path: Path,
    collections: List[str],
    deployments: List[str],
    extensions: List[ResourceExtensionDTO],
    project_id: int,
    overwrite: bool,
    timezone:str = "UTC",
    ignore_dst: bool = True,
    max_workers:  int = 4,
    max_zip_size: int = 500,
):
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
                _, col_name = event.split(":", 1)
                collection_tasks[col_name] = {
                    "task_collection": progress.add_task(f"Collection {col_name}", total=count),
                    "deployments": {},
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

        report = wildintel_tools.wildintel.create_trapper_package(
            data_path,
            output_path,
            collections,
            deployments,
            extensions,
            project_id,
            overwrite,
            timezone,
            ignore_dst,
            max_workers,
            max_zip_size,
            on_progress)
        # report = dpg.run(max_workers = 4, progress_callback=on_progress)
        return report

def upload_trapper_package(
        output_path: Path,
        collections: List[str],
        deployments: List[str],
        trapper_client: TrapperClient = None,
        trigger: bool = True,
        remove_zip: bool = True,
):
    TyperUtils.debug(f"Uploading collections {','.join([c for c in collections])} to Trapper")

    from rich.progress import (
        Progress,
        TextColumn,
        BarColumn,
        TimeElapsedColumn,
    )

    collection_tasks = {}

    progress = Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        "[progress.percentage]{task.percentage:>3.0f}%",
        TaskProgressColumn(),
        TimeElapsedColumn(),
    )

    def callback(event: str, count: int):
        if event.startswith("collection_start:"):
            _, col = event.split(":", 1)
            collection_tasks[col] = {
                "collection": progress.add_task(
                    f"Collection {col}", total=count
                ),
                "deployments": {},
            }

        elif event.startswith("deployment_start:"):
            _, col, dep = event.split(":", 2)
            task = progress.add_task(
                f"  Deployment {dep}", total=count
            )
            collection_tasks[col]["deployments"][dep] = task

        elif event.startswith("file_progress:"):
            _, col, dep = event.split(":", 2)
            progress.advance(
                collection_tasks[col]["deployments"][dep],
                count,
            )

        elif event.startswith("deployment_complete:"):
            _, col, dep = event.split(":", 2)
            progress.advance(
                collection_tasks[col]["collection"], 1
            )

    with progress:
        with Runner() as runner:
            report = runner.run(
                wildintel_tools.wildintel.upload_trapper_package(
                    output_path=output_path,
                    collections=collections,
                    deployments=deployments,
                    trapper_client=trapper_client,
                    trigger=trigger,
                    remove_zip=remove_zip,
                    progress_callback=callback,
                )
            )

    return report