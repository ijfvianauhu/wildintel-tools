import tempfile
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional, Any, List

import typer
from panoptes_client.panoptes import PanoptesAPIException
from trapper_client.TrapperClient import TrapperClient

from wildintel_tools.ui.typer.ZooUtils import ZooUtils
from wildintel_tools.ui.typer.settings import Settings
from wildintel_tools.ui.typer.zooniverse import check_connection, get_workflows, get_subject_sets
from wildintel_tools.zooniverse.TrapperZooniverseConnector import TrapperZooniverseConnector
from wildintel_tools.zooniverse.ZooniverseClient import ZooniverseClient
from wildintel_tools.ui.typer.TyperUtils import TyperUtils
from wildintel_tools.ui.typer.i18n import _

app = typer.Typer(
    help=_("Includes command to upload medias from Trapper to Zooniverse and import Annotations from Zooniverse to Trapper"),
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
    "trapper_password": ("TRAPPER", "trapper_password"),
    "trapper_user": ("TRAPPER", "trapper_username"),
    "max_interval": ("ZOONIVERSE_CONNECTOR","upload_collection_max_interval"),
    "n_images_seq": ("ZOONIVERSE_CONNECTOR","upload_collection_n_images_seq"),
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

@app.command(help=_("Test connection to Zooniverse server instance ") ,
             short_help=_("Test connection to Zooniverse server instance") + " (alias: tc)")
def test_connection(ctx: typer.Context,
                    zooniverse_username: str = typer.Option(None,
                                                            help=_("Username to authenticate with the Trapper server")),
                    zooniverse_password: str = typer.Option(
                        None, help=_("Password for the specified user (use only if no access token is provided)")
                    ),
                    zooniverse_project_id: str = typer.Option(
                        None, help=_("Zooniverse project ID to connect to (e.g., '12345' or 'owner/project-name')")
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
    Test the connection to Zooniverse server (API).

    Performs a check using ``check_trapper_connection`` and reports the result
    to the console.

    :param ctx: Typer context.
    :type ctx: typer.Context
    :param config: Internal configuration option (dynamic callback).
    :type config: pathlib.Path | None
    :raises Exception: If the connection fails a fatal message is logged.
    """
    settings:Settings = ctx.obj.get("settings", {})

    zooniverse_client = ZooniverseClient(
        project_id=zooniverse_project_id,
        username=zooniverse_username,
        password=zooniverse_password,
    )

    try:
        TyperUtils.info(_(f"Testing Zooniverse API connection {zooniverse_username}..."))
        check_connection(zooniverse_client)
        TyperUtils.success(_("Zooniverse API connection successful!"))
    except PanoptesAPIException as e:
        TyperUtils.error(_(f"Failed to connect to Zooniverse API. Check your settings."))
    except Exception as e:
        TyperUtils.fatal(_(f"Unexcepted error: {str(e)}"))

app.command(name="tc", help=_("Alias for test-connection"), hidden=True) (test_connection)

@app.command(
    help=_("Retrieve workflows from a Zooniverse project."
            " If a project ID is provided, only workflows for that project will be retrieved."
            ),
    short_help=_("Retrieve workflows from a Zooniverse project") + " (alias: wf)")
def workflows(ctx: typer.Context,
              wf_id: Annotated[Optional[str], typer.Argument(help=("Workflow ID or list (comma/space separated). Use '-' to read from stdin"))] = None,
              pipeline: Annotated[
                  bool,
                  typer.Option("--pipeline", help=_("Output only workflows IDs separated by commas (for shell pipelines)"))
              ] = False,
              query_param: Annotated[
                    List[str],
                    typer.Option(
                        "--query-param",
                        help=_("Query key-value pair, repeatable. Example: --query-param active=true --query-param launched=true"),
                    ),
              ] = None,

              raw: Annotated[
                  bool,
                  typer.Option(help=_("Display raw JSON output instead of formatted table"))
              ] = False,

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
    Display Zooniverse workflows.

    :param ctx: Typer context (must contain ``project`` and ``setting_manager``).
    :type ctx: typer.Context
    :param wf_id: Workflow ID to retrieve (optional).
    :type wf_id: int | None
    :param raw: Whether to display raw JSON output instead of a formatted table.
    :type raw: bool
    :param config: Internal configuration option (dynamic callback).
    :type config: pathlib.Path | None
    :raises Exception: If any check raises, the error is logged.

    """

    settings: Settings = ctx.obj.get("settings", {})

    zooniverse_client = ZooniverseClient(
        project_id=settings.ZOONIVERSE.zooniverse_project_id,
        username=settings.ZOONIVERSE.zooniverse_username,
        password=settings.ZOONIVERSE.zooniverse_password.get_secret_value()
    )

    ids = TyperUtils.parse_id_list(wf_id, allow_stdin=True, param_name="wf_id") or []

    TyperUtils.info(_(f"Retrieving workflows from Zooniverse project {zooniverse_client.project_id} with id {', '.join(str(i) for i in ids)}"))
    query = TyperUtils.parse_query_params(query_param)
    wfs = []
    if ids:
        for wid in ids:
            result = get_workflows(zooniverse_client, wid, query=query)
            wfs.extend(result if isinstance(result, list) else [result])
    else:
        wfs = get_workflows(zooniverse_client, None, query=query)

    if pipeline:
        ids_csv = ",".join(str(w.id) for w in wfs if getattr(w, "id", None) is not None)
        print(ids_csv)
    else:
        if len(wfs) == 1:
            ZooUtils.show_workflow(wfs[0], raw)
        else:
            ZooUtils.show_workflows(wfs)

app.command(name="wf", hidden=True, help=_("Alias for workflows")) (workflows)

@app.command(help=_(
        "Retrieve subject sets from a Zooniverse project. "
        "If a workflow ID is provided, only the subject sets linked to that workflow will be retrieved."
    ) + " (alias: ss)",
    short_help=_("Retrieve all or workflow-specific subject sets from a Zooniverse project" + " (alias: ss)"),
)
def subjectsets(ctx: typer.Context,
    ss_id: Annotated[Optional[str], typer.Argument(help=("Subjectset ID or list (comma/space separated). Use '-' to read from stdin"))] = None,
    pipeline: Annotated[
                    bool,
                    typer.Option("--pipeline", help=_("Output only subjectsets IDs separated by commas (for shell pipelines)"))
                ] = False,

    query_param: Annotated[
                    List[str],
                    typer.Option(
                        "--query-param",
                        help=_("Query key-value pair, repeatable. Example: --query-param active=true --query-param launched=true"),
                    ),
    ] = None,

    exports: Annotated[
        bool,
        typer.Option(help="Only print subjectsets with exports")
    ] = False,

    wf_id: Annotated[
        int,
        typer.Option(help="Subjectset ids linked to a workflow with this ID will be retrieved")
    ] = None,

    raw: Annotated[
        bool,
        typer.Option("--raw", help=_("Display each subjectset with formatted JSON"))
    ] = False,

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
    Retrieve subject sets from a Zooniverse project

    :param ctx: Typer context.
    :type ctx: typer.Context
    :param ss_id: SubjectSet ID to filter subject sets (optional).
    :type ss_id: int | None
    :param exports: Whether to filter subject sets with exports only.
    :type exports: bool
    :param wf_id: Workflow ID to filter subject sets (optional).
    :type wf_id: int | None
    :param config: Internal configuration option (dynamic callback).
    :type config: pathlib.Path | None
    :raises Exception: If retrieval fails a fatal message is logged.
    """

    settings: Settings = ctx.obj.get("settings", {})

    zooniverse_client = ZooniverseClient(
        project_id=settings.ZOONIVERSE.zooniverse_project_id,
        username=settings.ZOONIVERSE.zooniverse_username,
        password=settings.ZOONIVERSE.zooniverse_password.get_secret_value()
    )

    try:
        ss_ids = TyperUtils.parse_id_list(ss_id, allow_stdin=True, param_name="ss_id") or []
        TyperUtils.info(_(f"Retrieving Zoooniverse subjectset(s) {', '.join(str(i) for i in ss_ids) if ss_ids else 'all'} from project  {zooniverse_client.project_id}"))
        query = TyperUtils.parse_query_params(query_param)

        results = []
        if ss_ids:
            for sid in ss_ids:
                res = get_subject_sets(zooniverse_client, sid, query=query, with_exports=exports, wf_id=wf_id)
                if isinstance(res, list):
                    results.extend(res)
                else:
                    results.append(res)
        else:
            results = get_subject_sets(zooniverse_client, None, query=query, with_exports=exports, wf_id=wf_id)

        if pipeline:
            ids_csv = ",".join(str(ss.id) for ss in results if getattr(ss, "id", None) is not None)
            print(ids_csv)
        else:
            if len(results) == 1:
                ZooUtils.show_subject_set(results[0], raw=raw)
            else:
                ZooUtils.show_subject_sets(results)
    except Exception as e:
        TyperUtils.fatal(_(f"Failed retrieving Zoooniverse subjectset info: {str(e)}"))

app.command(name="ss", hidden=True, help="Alias for subjectsets") (subjectsets)

@app.command(
    help=_("Retrieve a specific subject (image) from a Zooniverse project" + "(alias: sbj)"),
    short_help=_("Retrieve a subject" + "(alias: sbj)"))
def subjects(
    ctx: typer.Context,
    id: Annotated[Optional[str], typer.Argument(help=("Subject ID or list (comma/space separated). Use '-' to read from stdin"))] = None,
    pipeline: Annotated[
        bool, typer.Option("--pipeline", help=_("Output only subject IDs separated by commas (for shell pipelines)"))
    ] = False,
    query_param: Annotated[
        List[str],
        typer.Option(
            "--query-param",
            help=_(
                "Query key-value pair, repeatable. Example: --query-param retired=true --query-param metadata.foo=bar"
            ),
        ),
    ] = None,
    subjectset_id: Annotated[
        int, typer.Option("--subjectset-id", "--ss-id", help=("Subjectset ID. Only subjects of this subjectset will be retrieved"))
    ] = None,
    raw: bool = typer.Option(False, help=_("If a single subject is returned, show its raw JSON")),
    config: Annotated[
        Path, typer.Option(hidden=True, help=_("File to save the report"), callback=callback_with_override)
    ] = None,
):
    """
    Retrieve subjects from Zooniverse and display them.

    Args:
        ctx: Typer context.
        id: Subject ID (single subject mode).
        subjectset_id: SubjectSet ID (multiple subjects mode).
        pipeline: If True, prints subject IDs separated by commas.
        query_param: Extra query parameters in key=value format (repeatable).
        raw: If True, prints raw JSON output.
        config: Internal configuration option (dynamic callback).
    """
    settings: Settings = ctx.obj.get("settings", Settings())
    zooniverse_client = ZooniverseClient(
        project_id=settings.ZOONIVERSE.zooniverse_project_id,
        username=settings.ZOONIVERSE.zooniverse_username,
        password=settings.ZOONIVERSE.zooniverse_password.get_secret_value(),
    )

    if id is None and subjectset_id is None:
        TyperUtils.fatal(_("Debe indicar el identificador del subject o el subjectset_id."))
        return
    if id is not None and subjectset_id is not None:
        TyperUtils.fatal(_("No puede combinar subject IDs con subjectset_id en la misma llamada."))
        return

    try:
        subjects: list = []
        if id is not None:
            ids = TyperUtils.parse_id_list(id, allow_stdin=True, param_name="id") or []
            TyperUtils.info(_(f"Getting subject(s) {', '.join(str(i) for i in ids)} from Zooniverse project {zooniverse_client.project_id}"))
            for sid in ids:
                subjects.append(zooniverse_client.subjects.get_by_id(sid))
        else:
            TyperUtils.info(_(f"Getting subjects from subjectset {subjectset_id} in project {zooniverse_client.project_id}"))
            subjects = zooniverse_client.subjects.get_by_subjectset(subjectset_id)

        if pipeline:
            ids_csv = ",".join(str(getattr(s, "id", "")) for s in subjects if getattr(s, "id", None) is not None)
            typer.echo(ids_csv)
            return

        if len(subjects) == 1:
            ZooUtils.show_subject(subjects[0], title="Subject", raw=raw)
        else:
            ZooUtils.show_subjects(subjects, title="Subjects")

    except Exception as e:
        TyperUtils.error(str(e))
app.command(name="sbj", hidden=True, help="Alias for subjects") (subjects)

@app.command(
    help=_("Download subjects (images) from a Zooniverse subjetset (alias: dl_ss)."),
    short_help=_("Download a subjectset (alias: dl_ss)"))
def download_ss(
    ctx: typer.Context,
    ss_ids: Annotated[List[int], typer.Argument(help=_("Subjectset ID"))] = ...,
    out_put_dir: Annotated[Path, typer.Option(help=_("Directory where the downloaded images will be saved"))] = None,
    max_workers: Annotated[int, typer.Option(help=_("Maximum number of threads to use"))] = 4,
    overwrite: Annotated[bool, typer.Option(help=_("Maximum number of threads to use"))] = False,
    config: Annotated[
        Path, typer.Option(hidden=True, help=_("File to save the report"), callback=callback_with_override)
    ] = None,
):
    """
    Download subjects from a Zooniverse subject set.

    :param ctx: Typer context.
    :type ctx: typer.Context
    :param ss_id: Subjectset ID to download subjects from.
    :type ss_id: int
    :param out_put_dir: Directory to save downloaded subjects. If not provided, a temporary directory is used.
    :type out_put_dir: pathlib.Path | None
    :param max_workers: Maximum number of threads to use for downloading subjects.
    :type max_workers: int
    :param config: Internal configuration option (dynamic callback).
    :type config: pathlib.Path | None
    :raises Exception: If retrieval fails a fatal message is logged.
    """
    settings = ctx.obj.get("settings", {})
    trapper_client = ctx.obj.get("trapper_client")
    zooniverse_client = ctx.obj.get("zooniverse_client")
    reports_files = []

    TyperUtils.debug(f"Downloading subjectsets {ss_ids} from Zooniverse project {zooniverse_client.project_id}")

    if out_put_dir is None:
        out_put_dir = tempfile.mkdtemp(prefix="bulk_download_")
    else:
        out_put_dir.mkdir(parents=True, exist_ok=True)

    for ss_id in ss_ids:
        try:
            TyperUtils.info(_(f"Retrieving subjects from {zooniverse_client.project_id}, subject set {ss_id}..."))
            ss = zooniverse_client.subjectsets.get_by_id(ss_id)

            try:
                num_subjects = int(getattr(ss, "set_member_subjects_count", 0) or 0)
                total = num_subjects if num_subjects > 0 else None
            except Exception:
                total = None

            TyperUtils.info(_(f"Subjectset {ss_id} has {total} subjects."))

            report = TyperUtils.progress_bar(
                zooniverse_client.subjectsets.download,
                (ss_id, Path(out_put_dir) / str(ss_id), max_workers, overwrite),
                None,
                _(f"[cyan]Downloading subjects from subjectset {ss_id}..."),
                total=total,
                use_subtasks=False,
            )

            TyperUtils.success(_(f"Subjects downloaded successfully in {out_put_dir}!"))
            report_output_file = TyperUtils.report_save(report)
            reports_files.append(report_output_file)
        except Exception as e:
            TyperUtils.error(str(e))

        TyperUtils.success(_(f"Reports saved in  {', '.join(map(str, reports_files))}!"))

app.command(name="dl_ss", hidden=True, help=_("Alias for download_ss")) (download_ss)


@app.command("import",
         short_help=_("Import all media (images) from a Trapper collection to a Zooniverse subject set"),
         help=_("Import all media (images) from a specific Trapper collection to a designated Zooniverse subject set"))
# @use_yaml_config(section=["upload_collection"], default_value=config_manager.ensure_config_file())
def importation(
    ctx: typer.Context,
    collection: Annotated[int, typer.Argument(help=("Collection ID"))] = ...,
    subjectset_name: Annotated[str, typer.Argument(help="Name of the Subject Set to create or use")] = None,
    research_project: Annotated[
        int,
        typer.Option(
            "--rp",
            help=_("ID of the research project linked to the classificarion project."),
        ),
    ] = None,
    classification_project: Annotated[
        int,
        typer.Option(
            "--cp",
        help=_("ID of the classification project linked to the collection."),
    ),
    ] = None,

    deployments_input: Annotated[
        Optional[str],
        typer.Option(
            "--deployments",
            "-d",
            help=_("Deployment IDs (comma or space separated). Use '-' to read from stdin."),
        ),
    ] = None,
    exclude_deployments_input: Annotated[
        Optional[str],
        typer.Option(
            "--exclude-deployments",
            "-x",
            help=_("Deployment IDs to skip (same format as --deployments)."),
        ),
    ] = None,
    n_images_seq: Annotated[int, typer.Option("--n-images-seq", help="Number of images per sequence")] = None,
    max_interval: Annotated[
        int, typer.Option("--max-interval", help="Maximum interval between images in a sequence (seconds)")
    ] = None,
    config: Annotated[Path, typer.Option(hidden=True, callback=callback_with_override)] = None,
) -> None:
    """
    Upload all media collectisubjectson from Trapper to Zooniverse.

    This command uploads media collections from Trapper to a specified Zooniverse project.
    It retrieves collections from Trapper, processes them, and uploads the media files
    to Zooniverse, creating or updating subject sets as necessary.

    Args:
        ctx (typer.Context): The Typer context object, used to share information across commands.

    """

    settings: Settings = ctx.obj.get("settings", Settings())
    zooniverse_client = ZooniverseClient(
        project_id=settings.ZOONIVERSE.zooniverse_project_id,
        username=settings.ZOONIVERSE.zooniverse_username,
        password=settings.ZOONIVERSE.zooniverse_password.get_secret_value(),
    )

    trapper_client=TrapperClient(
        base_url=str(settings.GENERAL.host),
        user_name=settings.GENERAL.login,
        user_password=settings.GENERAL.password.get_secret_value(),
        access_token=None,
    )

    connector:TrapperZooniverseConnector = TrapperZooniverseConnector(zooniverse_client,trapper_client)
    logger = ctx.obj["logger"]
    _ = ctx.obj["_"]

    deployments = TyperUtils.parse_id_list(deployments_input, allow_stdin=False)
    excluded_deployments=TyperUtils.parse_id_list(exclude_deployments_input, allow_stdin=False)

    TyperUtils.debug(f"Uploading collection {collection} to Zooniverse project {settings.ZOONIVERSE.zooniverse_project_id}")

    if not research_project or not classification_project or not collection:
        TyperUtils.fatal(f"No research project or classification project or collection defined.")

    # Find research project
    rp_obj = trapper_client.research_projects.get_by_id(research_project)
    if len(rp_obj.results) == 0:
        TyperUtils.fatal(f"No research project found with id {research_project}.")
    rp_selected = rp_obj.results[0]

    # Find classification project
    cp_obj = trapper_client.classification_projects.get_by_research_project(research_project)
    cp_selected = next((obj for obj in cp_obj.results if obj.pk == classification_project), None)
    if not cp_selected:
        TyperUtils.fatal(f"No classification project found with id {classification_project} in research_project {research_project}.")

    # Find collection
    collections_obj = trapper_client.collections.get_by_classification_project(classification_project)
    collection_selected = next((obj for obj in collections_obj.results if obj.collection_pk == collection), None)
    if not collection_selected:
        TyperUtils.fatal(f"No collection {collection} found in  classification project {classification_project}")

    if subjectset_name is None:
        subjectset_name = f"{rp_selected.name}_{rp_selected.pk}_{collection_selected.name}_{collection_selected.collection_pk}_{datetime.now():%Y-%m}"

    #logger.debug(f"Using subjectset name: {subjectset_name}")

    import wildintel_tools.ui.typer.zooniverse

    try:
        report = wildintel_tools.ui.typer.zooniverse.upload_collection(
            tzc = connector,
            subjectset_name=subjectset_name,
            collection=collection,
            deployments=deployments,
            blacklisted_deployments=excluded_deployments,
            cproject=classification_project,
            n_images_seq=n_images_seq,
            max_interval=max_interval,
            attempts=5,
            delay=15,
            max_attempts_per_subject=5,
            delay_seconds_per_subject=15,
        )

        TyperUtils.success(f"Collection {collection} uploaded to Zooniverse subject set '{subjectset_name}'")
        report_file = TyperUtils.save_report(report)
        TyperUtils.console.print("\n")
        TyperUtils.display_report(report)
        TyperUtils.success(_(f"Report saved at: {report_file}"))

    except Exception as e:
        raise e
        TyperUtils.error(f"Error uploading collection {collection}: {str(e)}")

from enum import Enum

class Wizard(str, Enum):
    importation = "import"

@app.command("wizard",
         short_help=_("Run a wizard to guide you through completing a task."),
         help=_("Run a wizard to guide you through completing a task."))
# @use_yaml_config(section=["upload_collection"], default_value=config_manager.ensure_config_file())
def wizard_command(
    ctx: typer.Context,
    wizard: Annotated[Wizard, typer.Argument(help=("Collection ID"))] = ...,
    config: Annotated[Path, typer.Option(hidden=True, callback=callback_with_override)] = None,
) -> None:
    settings: Settings = ctx.obj.get("settings", Settings())

    trapper_client = TrapperClient(
        base_url=str(settings.GENERAL.host),
        user_name=settings.GENERAL.login,
        user_password=settings.GENERAL.password.get_secret_value(),
        access_token=None
    )

    if (wizard == Wizard.importation):
        msg = ("This wizard will guide you through the process of importing a Trapper collection into a"
               " Zooniverse subject set. As a general rule, only images that contain animals will be imported.")

        if typer.confirm(msg):
            # select research_project
            rp = trapper_client.research_projects.get_all()
            rp_selected, key = TyperUtils.select_from_list(rp.results, title="Select a research project")
            # select cp
            cp = trapper_client.classification_projects.get_by_research_project(rp_selected.pk)
            cp_selected, key = TyperUtils.select_from_list(cp.results, title="Select a classification project")
            # select collection
            collections = trapper_client.collections.get_by_classification_project(cp_selected.pk)
            collection_selected, key = TyperUtils.select_from_list(collections.results, id_attr="collection", title="Select a collection")

            msg = (
                f"We are going to import the images from collection {collection_selected.pk}-{collection_selected.name} "
                f"into Zooniverse, taking into account the detection data from classification project {cp_selected.pk}-{cp_selected.name} "
                f"within research project {rp_selected.pk}-{rp_selected.name}. Are you sure?")
            if typer.confirm(msg):
                importation(ctx,
                            collection=collection_selected.pk,
                            research_project=rp_selected.pk,
                            classification_project=cp_selected.pk)

                typer.echo("Continuing...")
            else:
                typer.echo("Aborted.")
        else:
            typer.echo("Aborted.")



