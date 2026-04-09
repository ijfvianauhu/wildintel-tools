from pathlib import Path
from typing import Literal, List, Any, Optional, Dict
import re

from panoptes_client import Workflow
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from trapper_client.TrapperClient import TrapperClient

from wildintel_tools.zooniverse.TrapperZooniverseConnector import TrapperZooniverseConnector
from wildintel_tools.reports import Report
from wildintel_tools.ui.typer.TyperUtils import TyperUtils
from wildintel_tools.zooniverse.ZooniverseClient import ZooniverseClient


def check_connection(zooniverse_client: ZooniverseClient):
    """
    Verifies the connection to the Zooniverse API using the provided credentials.

    :param api_url: Base URL of the Zooniverse API.
    :type api_url: str
    :param user_name: Username or email used for authentication.
    :type user_name: str
    :param user_password: User password for authentication.
    :type user_password: str
    :raises Exception: If the connection fails or authentication is invalid.
    :return: None
    :rtype: None
    """
    zooniverse_client.connect()

def get_workflows(zooniverse_client:ZooniverseClient, id:int=None, query:dict[str, Any]=None) -> List[Workflow]:
    """
    Verifies the connection to the Zooniverse API using the provided credentials.
    :param zooniverse_client: ZooniverseClient instance.
    :type  zooniverse_client: ZooniverseClient
    :param id: Optional workflow ID to fetch a specific workflow.
    :type id: int
    :raises Exception: If the connection fails or authentication is invalid.
    :return: None
    :rtype: None
    """
    try:
        zooniverse_client.connect()

        if id is not None:
            ok = zooniverse_client.workflows.get_by_id(id)
        else:
            ok = zooniverse_client.workflows.get_all(query=query)
        return ok
    except Exception as e:
        msg = f"Failed to connect to Zooniverse API. Check your settings: {str(e)}"
        #logger.error(msg)
        raise Exception(msg)


def get_subject_sets(zooniverse_client:ZooniverseClient, ss_id = None, query: Optional[Dict[str, Any]] = None
                                ,with_exports:bool=False, wf_id=None) -> Any:
    """
    Retrieves subject sets from the Zooniverse API based on the provided parameters.
    :param zooniverse_client: ZooniverseClient instance.
    :type  zooniverse_client: ZooniverseClient
    :param ss_id: Optional subject set ID to fetch a specific subject set.
    :type ss_id: int
    :param query: Optional dictionary of query parameters to filter subject sets.
    :type query: dict[str, Any]
    :param with_exports: If True, retrieves subject sets that have exports available.
    :type with_exports: bool
    :param wf_id: Optional workflow ID to fetch subject sets associated with a specific workflow.
    :type wf_id: int
    :raises Exception: If the connection fails or authentication is invalid.
    :return: Subject sets matching the specified criteria.
    :rtype: Any

    """
    try:
        if ss_id is not None:
            ss = zooniverse_client.subjectsets.get_by_id(ss_id)
        elif wf_id:
            ss = zooniverse_client.subjectsets.get_subject_sets_from_workflow(wf_id, query=query)
        else:
            if with_exports:
                ss=zooniverse_client.subjectsets.with_exports()
            else:
                ss=zooniverse_client.subjectsets.get_all(query=query)
        return ss

    except Exception as e:
        msg = f"Failed to connect to Zooniverse API: {str(e)}"
        #logger.error(msg)
        raise Exception(msg)

def upload_collection( tzc : TrapperZooniverseConnector,
        collection: int,
        deployments: list[int] | None,
        blacklisted_deployments: list[int] | None,
        cproject: int,
        subjectset_name: str,
        n_images_seq: int,
        max_interval: int,
        attempts: int,
        delay: int,
        max_attempts_per_subject: int,
        delay_seconds_per_subject: int,
        dry_run: bool = False,
) -> Report :

    TyperUtils.debug(f"Starting upload_collection with values:{locals().items()}")
    with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
    ) as progress:

        # Registro dinámico de tareas
        task_registry = {}

        def get_or_create_task(task_name: str, total=None, description=None):
            """
            Crea la tarea si no existe. Si existe, la devuelve.
            """
            if task_name not in task_registry:
                desc = description or task_name.replace("_", " ").title()
                task_id = progress.add_task(desc, total=total)
                task_registry[task_name] = task_id
            return task_registry[task_name]

        def progress_callback(
                task_name: str,
                state: str,
                advance: int = 1,
                total: int | None = None,
                description: str | None = None,
                set_total: bool = False,
                item_name:str = None,
                item_status: Literal["start", "end", "fail"] | None = None,
                item_description: str | None = None
        ):
            """
            Callback flexible que soporta:
            - tareas determinadas   (con total)
            - tareas indeterminadas (total=None)
            - cambio de total a posteriori
            - añadir descripciones personalizadas
            """
            task_id = get_or_create_task(task_name, total, description)

            if set_total and total is not None:
                progress.update(task_id, total=total)

            # --- Estados ---
            if state == "start":
                new_desc = f"🟢  {description or task_name.replace('_', ' ').title()}"
                progress.update(task_id, description=new_desc)

            elif state == "end":
                new_desc = f"✔️  {description or task_name.replace('_', ' ').title()}"
                progress.update(task_id, completed=progress.tasks[task_id].total or 1,
                                description=new_desc)
                progress.stop_task(task_id)

            elif state == "fail":
                new_desc = f"❌  {description or task_name.replace('_', ' ').title()}"
                progress.update(task_id, description=new_desc)
                progress.stop_task(task_id)
                return  # no seguir avanzando

            if item_name is not None:
                status_messages = {
                    "start": f"[yellow]→ {item_name}: {item_description}"
                    if item_description
                    else f"[yellow]→ Starting processing item {item_name}",
                    "end": f"[green]✓ {item_name}: {item_description}"
                    if item_description
                    else f"[green]✓ Finished processing item {item_name}",
                    "fail": f"[red]✗ {item_name}: {item_description}"
                    if item_description
                    else f"[red]✗ Failed processing {item_name}",
                }

                message = status_messages.get(item_status)

                if message:
                    progress.log(message)

                progress.advance(task_id, advance)

        report = tzc.upload_collection(
             subjectset_name=subjectset_name,
             collection=collection,
             deployments=deployments,
             blacklisted_deployments=blacklisted_deployments,
             classification_project=cproject,
             n_images_seq=n_images_seq,
             max_interval=max_interval,
             attempts=attempts,
             delay=delay,
             max_attempts_per_subject=max_attempts_per_subject,
             delay_seconds_per_subject=delay_seconds_per_subject,
             progress_callback=progress_callback,
             dry_run=dry_run,
        )

    return report

def update_subject_metadata(
    zooniverse_client: ZooniverseClient,
    subject_set_id: int,
    global_metadata: Optional[Dict[str, Any]] = None,
    per_subject_metadata: Optional[Dict[str, Dict[str, Any]]] = None,
    max_workers: int = 1,
) -> Report:
    """
    Update the metadata of every subject inside a SubjectSet, showing a Rich progress bar.

    :param zooniverse_client: Authenticated ZooniverseClient instance.
    :param subject_set_id: ID of the SubjectSet whose subjects will be updated.
    :param global_metadata: Key-value pairs applied to every subject.
    :param per_subject_metadata: Mapping ``{subject_id: {key: value}}`` for per-subject updates.
    :param max_workers: Number of parallel threads (default 1 → sequential).
    :returns: Report with successes and errors.
    :rtype: Report
    """
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
    ) as progress:
        task = progress.add_task("Updating subjects...", total=None)

        def _callback(event: str, sid, name, total=None, step=None):
            if total is not None:
                progress.update(task, total=total)
            if event == "start":
                progress.update(task, description=f"[cyan]→ {name}")
            elif event == "end":
                progress.advance(task, 1)
                progress.update(task, description=f"[green]✓ {name}")
            elif event == "fail":
                progress.advance(task, 1)
                progress.update(task, description=f"[red]✗ {name}")

        report = zooniverse_client.subjects.update_metadata(
            subject_set_id=subject_set_id,
            global_metadata=global_metadata,
            per_subject_metadata=per_subject_metadata,
            max_workers=max_workers,
            callback=_callback,
        )

    return report


def update_subject_metadata_from_trapper(
    tzc: TrapperZooniverseConnector,
    subject_set_id: int,
    classification_project: int,
    dry_run: bool = False,
) -> Report:
    """
    Update subject metadata in Zooniverse using Trapper as source, with progress UI.
    """
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
    ) as progress:
        task_registry: Dict[str, int] = {}

        def get_or_create_task(task_name: str, total=None, description=None):
            if task_name not in task_registry:
                task_registry[task_name] = progress.add_task(description or task_name.replace("_", " ").title(), total=total)
            return task_registry[task_name]

        def progress_callback(
            task_name: str,
            state: str,
            advance: int = 1,
            total: int | None = None,
            description: str | None = None,
            set_total: bool = False,
            item_name: str | None = None,
            item_status: Literal["start", "end", "fail"] | None = None,
            item_description: str | None = None,
        ):
            task_id = get_or_create_task(task_name, total, description)

            if set_total and total is not None:
                progress.update(task_id, total=total)

            if state == "start":
                progress.update(task_id, description=f"🟢  {description or task_name.replace('_', ' ').title()}")
            elif state == "end":
                progress.update(task_id, completed=progress.tasks[task_id].total or 1,
                                description=f"✔️  {description or task_name.replace('_', ' ').title()}")
                progress.stop_task(task_id)
                return
            elif state == "fail":
                progress.update(task_id, description=f"❌  {description or task_name.replace('_', ' ').title()}")
                progress.stop_task(task_id)
                return

            if item_name is not None:
                status_messages = {
                    "start": f"[yellow]→ {item_name}: {item_description}" if item_description else f"[yellow]→ Starting {item_name}",
                    "end": f"[green]✓ {item_name}: {item_description}" if item_description else f"[green]✓ Finished {item_name}",
                    "fail": f"[red]✗ {item_name}: {item_description}" if item_description else f"[red]✗ Failed {item_name}",
                }
                message = status_messages.get(item_status)
                if message:
                    progress.log(message)
                progress.advance(task_id, advance)

        report = tzc.update_subject_metadata(
            subjectset_id=subject_set_id,
            classification_project=classification_project,
            progress_callback=progress_callback,
            dry_run=dry_run,
        )

    return report


def _extract_subject_filename(subject: Any) -> str | None:
    metadata = getattr(subject, "metadata", {}) or {}
    for key in ("Filename", "filename", "file_name", "name", "display_name"):
        value = metadata.get(key)
        if value:
            return str(value)

    # Fallback a atributos del subject si el metadata no trae nombre.
    for attr in ("display_name", "name"):
        value = getattr(subject, attr, None)
        if value:
            return str(value)
    return None


def _extract_media_id_from_filename(filename: str) -> int | None:
    basename = Path(filename).name

    # Formato más habitual en el proyecto: <media_id>_x_...
    match = re.match(r"(\d+)(?=_x_)", basename)
    if match:
        return int(match.group(1))

    # Fallback: primer bloque numérico del nombre.
    fallback = re.search(r"(\d+)", basename)
    if fallback:
        return int(fallback.group(1))

    return None


def build_subject_metadata_from_trapper(
    zooniverse_client: ZooniverseClient,
    trapper_client: TrapperClient,
    subject_set_id: int,
    classification_project: int,
) -> Dict[str, Dict[str, Any]]:
    """
    Build per-subject metadata dict from Trapper media data.

    It extracts ``media_id`` from each subject filename and queries Trapper to get
    the media record, then maps key fields into Zooniverse subject metadata.
    """
    subjects = zooniverse_client.subjects.get_by_subjectset(subject_set_id)
    per_subject_metadata: Dict[str, Dict[str, Any]] = {}

    for subject in subjects:
        sid = str(getattr(subject, "id", ""))
        filename = _extract_subject_filename(subject)
        if not filename:
            TyperUtils.warning(f"Subject {sid}: filename not found in metadata, skipping.")
            continue

        media_id = _extract_media_id_from_filename(filename)
        if media_id is None:
            TyperUtils.warning(f"Subject {sid}: could not extract media_id from filename '{filename}', skipping.")
            continue

        media_list = trapper_client.media.get_by_media_id(classification_project, media_id)
        results = getattr(media_list, "results", []) or []
        if not results:
            TyperUtils.warning(f"Subject {sid}: no Trapper media found for media_id={media_id}, skipping.")
            continue

        media = results[0]
        base_url = str(trapper_client.base_url)
        if not base_url.endswith("/"):
            base_url = base_url + "/"

        metadata = {
            "media_id": getattr(media, "mediaID", media_id),
            "deployment_id": getattr(media, "deploymentID", None),
            "capture_method": getattr(media, "captureMethod", None),
            "timestamp": str(getattr(media, "timestamp", "")),
            "file_name": getattr(media, "fileName", None),
            "file_public": getattr(media, "filePublic", None),
            "file_type": getattr(media, "fileMediatype", None),
            "file_path": getattr(media, "filePath", None),
            "external_id": f"{base_url}:media:{media_id}",
            "preview": f"{base_url}storage/resource/media/{media_id}/pfile/",
            "link": f"{base_url}storage/resource/media/{media_id}/file/",
            "thumbnail": f"{base_url}storage/resource/media/{media_id}/tfile/",
            "origin": base_url,
            "source": "trapper",
        }

        exif_data = getattr(media, "exifData", None)
        if exif_data is not None:
            metadata["exif_data"] = exif_data

        # Limpiar nulos para no sobreescribir metadatos existentes con None.
        per_subject_metadata[sid] = {k: v for k, v in metadata.items() if v is not None and v != ""}

    return per_subject_metadata


def public_annotations(tzc : TrapperZooniverseConnector, cp_id:int, collection_id: int, subjectset_id: int
                       , wf_id: int, observations_file:Path = None):
    results = tzc.upload_annotations(
        subjectset_id,
        wf_id,
        collection_id,
        cp_id,
        observations_file,
        None,
        None
    )

    return results


