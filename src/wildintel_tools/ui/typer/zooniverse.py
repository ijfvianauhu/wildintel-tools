from pathlib import Path
from typing import Literal, List, Any, Optional, Dict

from panoptes_client import Workflow
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

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


