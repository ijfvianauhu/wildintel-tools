import csv
import json
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional, Any, List

import typer
from panoptes_client.panoptes import PanoptesAPIException
from trapper_client.TrapperClient import TrapperClient

from wildintel_tools.ui.typer.ZooUtils import ZooUtils
from wildintel_tools.ui.typer.settings import Settings
from wildintel_tools.ui.typer.zooniverse import (
    check_connection,
    get_workflows,
    get_subject_sets,
    update_subject_metadata_from_trapper,
    public_annotations,
    download_subjectsets,
    check_subject_metadata as _check_subject_metadata,
    make_progress,
    make_progress_callback,
)
from wildintel_tools.zooniverse.TrapperZooniverseConnector import TrapperZooniverseConnector
from wildintel_tools.zooniverse.ZooniverseClient import ZooniverseClient
from wildintel_tools.ui.typer.TyperUtils import TyperUtils
from wildintel_tools.ui.typer.i18n import _

app = typer.Typer(
    help=_("Includes command to upload medias from Trapper to Zooniverse and import Annotations from Zooniverse to "
           "Trapper"),
    short_help=_("Utilities for managing and validating WildIntel data"))

_MEDIA_ID_RE = re.compile(r":media:(\d+)\s*$")


def _extract_media_id_from_url(url: str) -> Optional[int]:
    """Extract Trapper media_id from an origin/external_id URL like ``https://host/:media:12345``."""
    if not url:
        return None
    m = _MEDIA_ID_RE.search(url.strip())
    return int(m.group(1)) if m else None


def _iter_subject_rows(csv_path: Path, subject_set_id: Optional[int] = None):
    """Yield parsed rows from a Zooniverse subjects export (CSV or TSV), optionally filtered by subject_set_id."""
    with open(csv_path, newline="", encoding="utf-8") as f:
        first_line = f.readline()
        f.seek(0)
        delimiter = "\t" if "\t" in first_line else ","
        reader = csv.DictReader(f, delimiter=delimiter)
        for row in reader:
            if subject_set_id is not None:
                try:
                    if int(row.get("subject_set_id", "").strip()) != subject_set_id:
                        continue
                except (ValueError, TypeError):
                    continue
            yield row


def _media_id_from_row(row: dict) -> Optional[int]:
    """Return the Trapper media_id from a subject row, checking origin then external_id."""
    raw = row.get("metadata", "")
    try:
        metadata = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    for key in ("origin", "external_id"):
        mid = _extract_media_id_from_url(metadata.get(key, "") or "")
        if mid is not None:
            return mid
    return None

def _parse_uploaded_media_ids(csv_path: Path, subject_set_id: Optional[int] = None) -> set[int]:
    """Read a Zooniverse subjects export and return the set of Trapper media IDs already uploaded."""
    return {
        mid
        for row in _iter_subject_rows(csv_path, subject_set_id)
        if (mid := _media_id_from_row(row)) is not None
    }

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
def main_callback(ctx: typer.Context):
    """
    Typer callback executed before any command in this application.

    Initializes shared ``zooniverse_client``, ``trapper_client`` and ``connector``
    from the active settings and stores them in ``ctx.obj`` for every sub-command.
    """
    ctx.ensure_object(dict)
    settings: Settings = ctx.obj.get("settings", Settings())
    try:
        zooniverse_client = ZooniverseClient(
            project_id=settings.ZOONIVERSE.zooniverse_project_id,
            username=settings.ZOONIVERSE.zooniverse_username,
            password=settings.ZOONIVERSE.zooniverse_password.get_secret_value(),
        )
        trapper_client = TrapperClient(
            base_url=str(settings.GENERAL.host),
            user_name=settings.GENERAL.login,
            user_password=settings.GENERAL.password.get_secret_value(),
            access_token=None,
        )
        ctx.obj["zooniverse_client"] = zooniverse_client
        ctx.obj["trapper_client"] = trapper_client
        ctx.obj["connector"] = TrapperZooniverseConnector(zooniverse_client, trapper_client)
    except Exception:
        pass

@app.command(help=_("Test connection to Zooniverse server instance ") ,
             short_help=_("Test connection to Zooniverse server instance") + " (alias: tc)",
             rich_help_panel=_("Helpers")
)
def test_connection(ctx: typer.Context,
        zooniverse_username: str = typer.Option( None, "--zooniverse-username", "--zu",
                                                help=_("Username to authenticate with the Trapper server")),
        zooniverse_password: str = typer.Option(
            None, "--zooniverse-password", "--zp", help=_("Password for the specified user (use only if no access token is provided)")
        ),
        zooniverse_project_id: str = typer.Option(
            None, "--zooniverse-project-id", "--zP", help=_("Zooniverse project ID to connect to (e.g., '12345' or 'owner/project-name')")
        ),

        config: Annotated[Path,typer.Option(hidden=True,help=_("File to save the report"),
                callback=callback_with_override
            )
        ] = None,
    ):
    """
    Test the connection to Zooniverse server (API).

    Performs a check using ``check_trapper_connection`` and reports the result
    to the console.

    Args:
        ctx (Typer.Context): Typer context (expects `settings`).
        zooniverse_username (str, optional): Username to authenticate with the Trapper server.
        zooniverse_password (str, optional): Password for the specified user (use only if no access token is provided).
        zooniverse_project_id (str, optional): Zooniverse project ID to connect to (e.g., '12345' or 'owner/project-name').
        config (Path, optional): Internal configuration option (dynamic callback).
    """

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
    short_help=_("Retrieve workflows from a Zooniverse project") + " (alias: wf)",
    rich_help_panel=_("Helpers")
)
def workflows(ctx: typer.Context,
              wf_id: Annotated[Optional[str], typer.Argument( help=("Workflow ID or list (comma/space separated). Use '-' to read from stdin"))] = None,
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

    Args:
        ctx (typer.Context): Typer context (expects `settings`).
        wf_id (list[int] | int ): Workflow ID or list (comma/space separated).
        pipeline (bool): If True, outputs only workflow IDs separated by commas (for shell pipelines).
        query_param (List[str]):
        raw (bool): Whether to display raw JSON output instead of a formatted table.
        config (Path, optional): Internal configuration option (dynamic callback).

    :raises Exception: If any check raises, the error is logged.

    """

    zooniverse_client: ZooniverseClient = ctx.obj["zooniverse_client"]

    ids = TyperUtils.parse_id_list(wf_id, allow_stdin=True, param_name="wf_id") or []

    TyperUtils.info(_(f"Retrieving workflows from Zooniverse project {zooniverse_client.project_id} with id {', '.join(str(i) for i in ids)}"))
    query = TyperUtils.parse_query_params(query_param)
    wfs = []
    for wid in ids or [None]:
        result = get_workflows(zooniverse_client, wid, query=query)
        wfs.extend(result if isinstance(result, list) else [result])

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
    rich_help_panel="Helpers"
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

    wf_id: Annotated[
        int,
        typer.Option("--workflow", "--wf", help="Subjectset ids linked to a workflow with this ID will be retrieved")
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

    Args:
        ctx (Typer.Context): Typer context (expects `settings`).
        ss_id (list[int] | int): Subjectset ID or list (comma/space separated).
        pipeline (bool): Output only subjectsets IDs linked to a pipeline.
        query_param: Query key-value pair (comma/space separated).
        wf_id (int): Subjectset ID or list (comma/space separated).
        raw (bool): Display each subjectset with formatted JSON.
        config (pathlib.Path | None):
    """

    zooniverse_client: ZooniverseClient = ctx.obj["zooniverse_client"]

    try:
        ss_ids = TyperUtils.parse_id_list(ss_id, allow_stdin=True, param_name="ss_id") or []
        TyperUtils.info(_(f"Retrieving Zoooniverse subjectset(s) {', '.join(str(i) for i in ss_ids) if ss_ids else 'all'} from project  {zooniverse_client.project_id}"))
        query = TyperUtils.parse_query_params(query_param)

        results = []
        if ss_ids:
            for sid in ss_ids:
                res = get_subject_sets(zooniverse_client, sid, query=query, with_exports=None, wf_id=wf_id)
                if isinstance(res, list):
                    results.extend(res)
                else:
                    results.append(res)
        else:
            results = get_subject_sets(zooniverse_client, None, query=query, with_exports=None, wf_id=wf_id)

        if pipeline:
            ids_csv = ",".join(str(ss.id) for ss in results if getattr(ss, "id", None) is not None)
            typer.echo(ids_csv)
            return
        if len(results) == 1:
            ZooUtils.show_subject_set(results[0], raw=raw)
        else:
            ZooUtils.show_subject_sets(results)
    except Exception as e:
        TyperUtils.fatal(_(f"Failed retrieving Zoooniverse subjectset info: {str(e)}"))

app.command(name="ss", hidden=True, help="Alias for subjectsets") (subjectsets)

@app.command(
    help=_("Retrieve a specific subject (image) from a Zooniverse project" + "(alias: sbj)"),
    short_help=_("Retrieve a subject" + "(alias: sbj)"),
    rich_help_panel="Helpers"
)
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
        int, typer.Option("--ss", "--subjectset-id", "--ss-id", help=("Subjectset ID. Only subjects of this subjectset will be retrieved"))
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
    zooniverse_client: ZooniverseClient = ctx.obj["zooniverse_client"]

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
    help=_(
        "Update subject metadata in a Zooniverse subject set using Trapper data. "
        "The command extracts media_id from each subject filename, queries Trapper "
        "for that media in the selected classification project, and updates the "
        "subject metadata with the returned media fields."
    ),
    short_help=_("Update subject metadata in a subject set (alias: um)"),
)
def update_metadata(
    ctx: typer.Context,
    ss_id: Annotated[int, typer.Argument(help=_("Subject set ID whose subjects will be updated"))],
    classification_project: Annotated[
        int,
        typer.Option(
            "--cp",
            help=_("Trapper classification project ID used to look up media by media_id."),
        ),
    ] = ...,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help=_("Simulate the process: metadata is resolved but no subject is updated in Zooniverse."),
            show_default=True,
        ),
    ] = False,
    attempts: Annotated[
        int,
        typer.Option("--attempts", help=_("Maximum retry attempts per subject when resolving/updating metadata.")),
    ] = 3,
    delay_seconds: Annotated[
        int,
        typer.Option("--delay-seconds", help=_("Seconds to wait between retries for a failed subject.")),
    ] = 5,
    max_workers: Annotated[
        int,
        typer.Option("--max-workers", help=_("Number of parallel workers. Default 1 (sequential). Increase carefully: Zooniverse rate-limits concurrent requests.")),
    ] = 1,
    white_list: Annotated[
        Optional[str],
        typer.Option(
            "--white-list",
            help=_("Comma or space separated list of subject IDs to process. Only these subjects will be updated."),
        ),
    ] = None,
    black_list: Annotated[
        Optional[str],
        typer.Option(
            "--black-list",
            help=_("Comma or space separated list of subject IDs to skip. These subjects will not be updated."),
        ),
    ] = None,
    config: Annotated[
        Path,
        typer.Option(hidden=True, help=_("Configuration file"), callback=callback_with_override),
    ] = None,
) -> None:
    """
    Update the metadata of all subjects in a Zooniverse subject set.

    :param ctx: Typer context.
    :param ss_id: Subject set ID.
    :param classification_project: Trapper classification project ID.
    :param attempts: Retry attempts per subject.
    :param delay_seconds: Delay between retries in seconds.
    :param config: Internal configuration option (dynamic callback).
    """
    connector: TrapperZooniverseConnector = ctx.obj["connector"]
    TyperUtils.info(_(f"Updating metadata for subjects in subject set {ss_id} using Trapper data..."))

    white_list_ids = TyperUtils.parse_id_list(white_list, allow_stdin=False) if white_list else None
    black_list_ids = TyperUtils.parse_id_list(black_list, allow_stdin=False) if black_list else None

    if dry_run:
        TyperUtils.console.print()
        TyperUtils.console.print("[bold yellow]⚠  DRY-RUN mode: metadata will be resolved but no subject will be updated in Zooniverse.[/bold yellow]")
    if white_list_ids:
        TyperUtils.console.print(f"[cyan]⬜ White-list:[/cyan] only {len(white_list_ids)} subject(s) will be processed: {white_list_ids}")
    if black_list_ids:
        TyperUtils.console.print(f"[cyan]⬛ Black-list:[/cyan] {len(black_list_ids)} subject(s) will be skipped: {black_list_ids}")
    if dry_run or white_list_ids or black_list_ids:
        TyperUtils.console.print()

    try:
        report = update_subject_metadata_from_trapper(
            tzc=connector,
            subject_set_id=ss_id,
            classification_project=classification_project,
            dry_run=dry_run,
            white_list=white_list_ids,
            black_list=black_list_ids,
            attempts=attempts,
            delay_seconds=delay_seconds,
            max_workers=max_workers,
        )
    except Exception as e:
        TyperUtils.fatal(_(f"Failed to update metadata for subject set {ss_id}: {e}"))
        return

    TyperUtils.success(_(f"Metadata update completed for subject set {ss_id}."))
    report_file = TyperUtils.save_report(report)
    TyperUtils.console.print()
    TyperUtils.display_report(report)
    TyperUtils.success(_(f"Report saved at: {report_file}"))

app.command(name="um", hidden=True, help=_("Alias for update-metadata")) (update_metadata)


@app.command(
    name="export",
    short_help=_("Export Zooniverse annotations back to Trapper (alias: exp)."),
    help=_(
        "Export the classification results of a Zooniverse subject set back to Trapper as observations. "
        "Requires a workflow ID (--wf), a subject set ID (--ss), a collection ID (--collection) "
        "and a classification project ID (--cp)."
    ),
)
def export_annotations(
    ctx: typer.Context,
    wf_id: Annotated[
        int,
        typer.Option(
            "--wf", "--workflow",
            help=_("Zooniverse workflow ID whose classifications will be exported."),
        ),
    ] = ...,
    ss_id: Annotated[
        int,
        typer.Option(
            "--ss", "--subject-set",
            help=_("Zooniverse subject set ID to export annotations from."),
        ),
    ] = ...,
    classification_project: Annotated[
        int,
        typer.Option(
            "--cp", "--classification-project",
            help=_("Trapper classification project ID where observations will be created."),
        ),
    ] = ...,
    collection: Annotated[
        int,
        typer.Option(
            "--collection", "--c",
            help=_("Trapper collection ID linked to the classification project."),
        ),
    ] = ...,
    deployments: Annotated[
        List[int],
        typer.Option(
            "--deployments", "--d",
            help=_("Trapper deployments ID linked to the classification project."),
        ),
    ] = None,

    observations_file: Annotated[
        Optional[Path],
        typer.Option(
            "--observations-file",
            "-of",
            help=_("Optional path to save the raw observations file before uploading to Trapper."),
        ),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose/--no-verbose", help=_("Show detail for each processed media in the progress bar")),
    ] = True,
    save_zoo_annotations: Annotated[
        bool,
        typer.Option(
            "--save-zoo-annotations/--no-save-zoo-annotations",
            help=_("Save the raw Zooniverse annotations (extracted user opinions) as a separate CSV alongside the observations file."),
        ),
    ] = True,
    config: Annotated[
        Path,
        typer.Option(hidden=True, help=_("Configuration file"), callback=callback_with_override),
    ] = None,
) -> None:
    """
    Export Zooniverse annotations to Trapper.

    Reads the classification results for *ss_id* / *wf_id* from Zooniverse and
    pushes them as observations into the Trapper *classification_project* /
    *collection*.

    :param ctx: Typer context.
    :param wf_id: Zooniverse workflow ID.
    :param ss_id: Zooniverse subject set ID.
    :param classification_project: Trapper classification project ID.
    :param collection: Trapper collection ID.
    :param observations_file: Optional path to persist the raw observations file.
    :param config: Internal configuration option (dynamic callback).
    """
    connector: TrapperZooniverseConnector = ctx.obj["connector"]
    trapper_client: TrapperClient = ctx.obj["trapper_client"]

    if observations_file is None:
        deps_str = "-".join(str(d) for d in deployments) if deployments else "all"
        timestamp = datetime.now().strftime("%Y%m%d%H%M")
        filename = f"wildintel_observations_wf{wf_id}_ss{ss_id}_cp{classification_project}_col{collection}_dep{deps_str}_{timestamp}.csv"
        observations_file = Path(tempfile.gettempdir()) / filename

    TyperUtils.info(
        _(
            f"Exporting annotations — workflow {wf_id}, subject set {ss_id}, "
            f"collection {collection}, classification project {classification_project}…"
        )
    )

    if observations_file is None:
        observations_file = Path(
            f"zoo_annotations_{wf_id}_{ss_id}_{classification_project}_{collection}"
            f"_{datetime.now():%Y%m%d%H%M}.csv"
        )

    try:
        report = public_annotations(
            tzc=connector,
            cp_id=classification_project,
            collection_id=collection,
            subjectset_id=ss_id,
            wf_id=wf_id,
            observations_file=observations_file,
            deployments=deployments,
            verbose=verbose,
            save_zoo_annotations=save_zoo_annotations,
        )
    except Exception as e:
        TyperUtils.fatal(_(f"Failed to export annotations: {e}"))
        return

    TyperUtils.success(_(f"Annotations exported successfully from subject set {ss_id}."))
    TyperUtils.success(_(f"Csv file was saved as  {observations_file}."))
    TyperUtils.info(_(
        f"To import the CSV into Trapper, go to:\n"
        f"  {trapper_client.base_url}/media_classification/classification/import/\n"
        f"and upload '{observations_file.name}' checking only the option 'Import expert classifications'."
    ))



    report_file = TyperUtils.save_report(report)
    TyperUtils.console.print()
    TyperUtils.display_report(report)
    TyperUtils.success(_(f"Report saved at: {report_file}"))

    import_url = str(trapper_client.base_url).rstrip("/") + "/media_classification/classification/import/"
    TyperUtils.console.print()
    TyperUtils.console.print(f"[bold]CSV file:[/bold] [cyan]{observations_file}[/cyan]")
    TyperUtils.console.print(f"[bold]Import it at:[/bold] [link={import_url}]{import_url}[/link]")
    TyperUtils.console.print()
    TyperUtils.console.print("[bold red]⚠  IMPORTANT:[/bold red] [bold]The import MUST be performed logged in as Trapper Zooniverse user[/bold] "                             
                             f"Using a different account will cause the import to fail or produce incorrect results.")


app.command(name="exp", hidden=True, help=_("Alias for export")) (export_annotations)


@app.command(
    help=_("Download subjects (images) from one or more Zooniverse subject sets (alias: dl_ss)."),
    short_help=_("Download subject set(s) (alias: dl_ss)"),
    rich_help_panel="Helpers"
)
def download_ss(
    ctx: typer.Context,
    ss_ids: Annotated[List[int], typer.Argument(help=_("One or more subject set IDs"))],
    out_put_dir: Annotated[
        Optional[Path],
        typer.Option("--output-dir", "-o", help=_("Directory where downloaded images will be saved")),
    ] = None,
    max_workers: Annotated[int, typer.Option("--max-workers", help=_("Number of parallel download threads"))] = 4,
    overwrite: Annotated[bool, typer.Option("--overwrite", help=_("Overwrite existing files"))] = False,
    verbose: Annotated[bool, typer.Option("--verbose/--no-verbose", help=_("Show detail for each downloaded subject"))] = True,
    black_list: Annotated[
        Optional[str],
        typer.Option(
            "--exclude-subjects", "--black-list",
            help=_("Comma or space separated list of subject IDs to always skip."),
        ),
    ] = None,
    white_list: Annotated[
        Optional[str],
        typer.Option(
            "--white-list",
            help=_("Comma or space separated list of subject IDs to download. "
                   "When provided, only these subjects are downloaded (blacklist still applies)."),
        ),
    ] = None,
    config: Annotated[
        Path, typer.Option(hidden=True, help=_("Configuration file"), callback=callback_with_override)
    ] = None,
) -> None:
    zooniverse_client: ZooniverseClient = ctx.obj["zooniverse_client"]

    if out_put_dir is None:
        out_put_dir = Path(tempfile.mkdtemp(prefix="bulk_download_"))

    excluded_ids = TyperUtils.parse_id_list(black_list, allow_stdin=False) if black_list else None
    included_ids = TyperUtils.parse_id_list(white_list, allow_stdin=False) if white_list else None

    TyperUtils.info(_(f"Downloading {len(ss_ids)} subject set(s) into {out_put_dir}…"))
    if included_ids:
        TyperUtils.console.print(f"[cyan]✅ Whitelist: only {len(included_ids)} subject(s) will be downloaded[/cyan]")
    if excluded_ids:
        TyperUtils.console.print(f"[cyan]⛔ Blacklist: {len(excluded_ids)} subject(s) will be skipped[/cyan]")

    try:
        reports = download_subjectsets(
            zooniverse_client,
            ss_ids=ss_ids,
            out_put_dir=out_put_dir,
            max_workers=max_workers,
            overwrite=overwrite,
            verbose=verbose,
            exclude_subjects=excluded_ids,
            include_subjects=included_ids,
        )
    except Exception as e:
        TyperUtils.fatal(_(f"Download failed: {e}"))
        return

    report_files = []
    for report in reports:
        report_files.append(TyperUtils.save_report(report))
        TyperUtils.display_report(report)

    TyperUtils.success(_(f"Downloads complete. Reports saved in: {', '.join(str(f) for f in report_files)}"))

app.command(name="dl_ss", hidden=True, help=_("Alias for download_ss")) (download_ss)


@app.command("import",
         short_help=_("Import all media (images) from a Trapper collection to a Zooniverse subject set"),
         help=_("Import all media (images) from a specific Trapper collection to a designated Zooniverse subject set"))
def importation(
    ctx: typer.Context,
    collection: Annotated[int, typer.Argument(help=("Collection ID"))] = ...,
    subjectset_name: Annotated[str, typer.Argument(help="Name of the Subject Set to create or use")] = None,
    research_project: Annotated[
        int,
        typer.Option(
            "--rp", "--research-project",
            help=_("ID of the research project linked to the classificarion project."),
        ),
    ] = None,
    classification_project: Annotated[
        int,
        typer.Option(
            "--cp", "--classification-project",
        help=_("ID of the classification project linked to the collection."),
    ),
    ] = None,

    deployments_input: Annotated[
        Optional[str],
        typer.Option(
            "--deployments",
            "--d",
            help=_("Deployment IDs (comma or space separated). Use '-' to read from stdin."),
        ),
    ] = None,
    exclude_deployments_input: Annotated[
        Optional[str],
        typer.Option(
            "--exclude-deployments",
            "--ed",
            help=_("Deployment IDs to skip (same format as --deployments)."),
        ),
    ] = None,
    n_images_seq: Annotated[int, typer.Option("--n-images-seq", help="Number of images per sequence")] = None,
    max_interval: Annotated[
        int, typer.Option("--max-interval", help="Maximum interval between images in a sequence (seconds)")
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help=_("Simulate the process: no images are downloaded, no subject set is created and nothing is uploaded to Zooniverse."),
        ),
    ] = False,
    exclude_subjects: Annotated[
        Optional[Path],
        typer.Option(
            "--exclude-subjects",
            help=_(
                "Path to a Zooniverse subjects export CSV/TSV. Media whose Trapper media_id is found in the "
                "'origin' or 'external_id' field of this file will not be uploaded. "
                "Obtain it at https://www.zooniverse.org/lab/{project_id}/data-exports "
                "under 'Request new subject export'."
            ),
        ),
    ] = None,
    media_input: Annotated[
        Optional[str],
        typer.Option(
            "--media",
            "--m",
            help=_("Media IDs to upload (comma or space separated). Only these media will be uploaded. Use '-' to read from stdin."),
        ),
    ] = None,
    exclude_media_input: Annotated[
        Optional[str],
        typer.Option(
            "--exclude-media",
            "--em",
            help=_("Media IDs to skip (comma or space separated). These media will never be uploaded. Use '-' to read from stdin."),
        ),
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
    connector: TrapperZooniverseConnector = ctx.obj["connector"]
    trapper_client: TrapperClient = ctx.obj["trapper_client"]
    settings: Settings = ctx.obj.get("settings", Settings())

    deployments = TyperUtils.parse_id_list(deployments_input, allow_stdin=False)
    excluded_deployments = TyperUtils.parse_id_list(exclude_deployments_input, allow_stdin=False)
    media_ids = TyperUtils.parse_id_list(media_input, allow_stdin=True, param_name="--media")
    excluded_media_ids = TyperUtils.parse_id_list(exclude_media_input, allow_stdin=True, param_name="--exclude-media")

    TyperUtils.debug(f"Uploading collection {collection} to Zooniverse")

    if not research_project or not classification_project or not collection:
        TyperUtils.fatal(f"No research project or classification project or collection defined.")

    # Find research project
    rp_obj = trapper_client.research_projects.get_by_id(research_project)
    if len(rp_obj.results) == 0:
        TyperUtils.fatal(f"No research project found with id {research_project}.")
    rp_selected = rp_obj.results[0]

    # Find classification project
    cp_obj = trapper_client.classification_projects.get_all_by_research_project(research_project)
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

    if dry_run:
        TyperUtils.console.print()
        TyperUtils.console.print("[bold yellow]⚠  DRY-RUN mode: no images will be downloaded, no subject set will be created and nothing will be uploaded to Zooniverse.[/bold yellow]")
        TyperUtils.console.print()

    uploaded_media_ids: set[int] = set()
    if exclude_subjects is not None:
        if not exclude_subjects.exists():
            TyperUtils.fatal(f"Exclude-subjects file not found: {exclude_subjects}")
        uploaded_media_ids = _parse_uploaded_media_ids(exclude_subjects)
        TyperUtils.info(_(f"Excluding {len(uploaded_media_ids)} already-uploaded media IDs from {exclude_subjects.name}"))

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
            dry_run=dry_run,
            uploaded_media_ids=uploaded_media_ids or None,
            media_ids=media_ids,
            excluded_media_ids=excluded_media_ids,
            max_workers=settings.ZOONIVERSE_CONNECTOR.upload_collection_max_workers or 4,
        )

        TyperUtils.success(f"Collection {collection} uploaded to Zooniverse subject set '{subjectset_name}'")
        report_file = TyperUtils.save_report(report)
        TyperUtils.console.print("\n")
        TyperUtils.display_report(report)
        TyperUtils.success(_(f"Report saved at: {report_file}"))

    except Exception as e:
        raise e
        TyperUtils.error(f"Error uploading collection {collection}: {str(e)}")


@app.command(
    help=_("List Trapper media IDs already uploaded to a subject set, from a Zooniverse subjects export file."),
    short_help=_("List uploaded media IDs from a subjects export"),
)
def uploaded_media(
    ctx: typer.Context,
    subjects_csv: Annotated[
        Path,
        typer.Argument(help=_(
            "Path to the Zooniverse subjects export CSV/TSV file. "
            "To obtain it, go to https://www.zooniverse.org/lab/{project_id}/data-exports "
            "(replace {project_id} with your Zooniverse project ID), "
            "click 'Request new subject export' and download the generated file."
        )),
    ],
    subject_set_id: Annotated[
        Optional[int],
        typer.Option("--subject-set-id", "--ss", "--ss-id", help=_("Filter by subject set ID. If omitted, all rows are included.")),
    ] = None,
    pipeline: Annotated[
        bool,
        typer.Option("--pipeline", help=_("Output only media IDs separated by newlines (for shell pipelines).")),
    ] = False,
    unresolved: Annotated[
        bool,
        typer.Option("--unresolved", help=_("Show only subjects for which no media_id could be extracted.")),
    ] = False,
    only_duplicated: Annotated[
        bool,
        typer.Option("--only-duplicated", help=_("Show only media_ids that appear more than once.")),
    ] = False,
) -> None:
    """
    Read a Zooniverse subjects export file and print the Trapper media IDs that have already been uploaded.

    Media IDs are extracted from the ``origin`` or ``external_id`` field in ``metadata`` using the pattern ``/:media:<id>``.
    Use --unresolved to list subjects for which no media_id could be found.
    """
    if not subjects_csv.exists():
        TyperUtils.fatal(f"File not found: {subjects_csv}")

    ss_label = f" — subject set {subject_set_id}" if subject_set_id else ""

    if unresolved:
        unmatched = TrapperZooniverseConnector.unmatched_subject_id(subjects_csv, subject_set_id)

        if pipeline:
            for sid in unmatched:
                typer.echo(sid)
            return

        from rich.table import Table
        table = Table(title=f"[yellow]Subjects without media_id{ss_label}[/yellow]", show_lines=False)
        table.add_column("subject_id", style="yellow", justify="right")
        for sid in unmatched:
            table.add_row(str(sid))
        TyperUtils.console.print(table)
        TyperUtils.console.print(f"[yellow]{len(unmatched)} subjects without resolvable media_id[/yellow]")
        return

    if only_duplicated:
        duplicated = TrapperZooniverseConnector.duplicated_media_id(subjects_csv, subject_set_id)
        sorted_mids = sorted(duplicated)

        if pipeline:
            for mid in sorted_mids:
                typer.echo(mid)
            return

        from rich.table import Table
        table = Table(title=f"Duplicated media IDs{ss_label}", show_lines=False)
        table.add_column("media_id", style="cyan", justify="right")
        table.add_column("count", style="yellow", justify="right")
        for mid in sorted_mids:
            table.add_row(str(mid), str(len(duplicated[mid])))
        TyperUtils.console.print(table)
        TyperUtils.info(_(f"{len(sorted_mids)} duplicated media IDs found"))
        return

    media_map = TrapperZooniverseConnector.uploaded_media_id(subjects_csv, subject_set_id)

    sorted_mids = sorted(media_map)

    if pipeline:
        for mid in sorted_mids:
            typer.echo(mid)
        return

    from rich.table import Table
    table = Table(title=f"Uploaded media IDs{ss_label}", show_lines=False)
    table.add_column("media_id", style="cyan", justify="right")
    for mid in sorted_mids:
        table.add_row(str(mid))
    TyperUtils.console.print(table)
    TyperUtils.info(_(f"{len(sorted_mids)} media IDs found"))


@app.command(
    name="check-subject-set",
    help=_(
        "Validate a Zooniverse subject set against a Trapper collection. "
        "Follows the same selection logic as 'import' but without downloading or uploading. "
        "Reports missing media (expected but absent), extra media (uploaded but unexpected), "
        "and subjects with incorrect metadata."
    ),
    short_help=_("Validate a subject set against a Trapper collection"),
    rich_help_panel="Validation"
)
def validate_subject_set(
    ctx: typer.Context,
    subjects_csv: Annotated[
        Path,
        typer.Argument(help=_(
            "Path to the Zooniverse subjects export CSV/TSV file. "
            "To obtain it, go to https://www.zooniverse.org/lab/{project_id}/data-exports "
            "and click 'Request new subject export'."
        )),
    ],
    collection: Annotated[int, typer.Argument(help=_("Collection ID in Trapper."))] = ...,
    research_project: Annotated[
        int,
        typer.Option("--rp", "--research-project", help=_("ID of the research project.")),
    ] = None,
    classification_project: Annotated[
        int,
        typer.Option("--cp", "--classification-project", help=_("ID of the classification project linked to the collection.")),
    ] = None,
    subject_set_id: Annotated[
        Optional[int],
        typer.Option("--subject-set-id", "--ss", "--ss-id", help=_("Filter the CSV by subject set ID. If omitted, all rows are included.")),
    ] = None,
    deployments_input: Annotated[
        Optional[str],
        typer.Option("--deployments", "--d", help=_("Deployment IDs (comma or space separated). If omitted, auto-detected from collection name.")),
    ] = None,
    exclude_deployments_input: Annotated[
        Optional[str],
        typer.Option("--exclude-deployments", "--ed", help=_("Deployment IDs to skip (same format as --deployments).")),
    ] = None,
    n_images_seq: Annotated[int, typer.Option("--n-images-seq", help=_("Number of images per sequence."))] = None,
    max_interval: Annotated[int, typer.Option("--max-interval", help=_("Maximum interval between images in a sequence (seconds)."))] = None,
    config: Annotated[Path, typer.Option(hidden=True, callback=callback_with_override)] = None,
) -> None:
    """
    Validate a Zooniverse subject set against a Trapper collection.

    Follows the exact same media-selection logic as the 'import' command (deployments,
    sequences, public-only, human-filtered) but contacts neither the downloader nor
    the uploader.  Produces three sections:

    - **Missing**: media_ids Trapper expects to see in Zooniverse but are absent from the CSV.
    - **Extra**: media_ids present in the CSV that are not part of the expected set.
    - **Metadata issues**: subjects whose metadata fields are incomplete or unparseable.
    """
    if not subjects_csv.exists():
        TyperUtils.fatal(f"File not found: {subjects_csv}")

    connector: TrapperZooniverseConnector = ctx.obj["connector"]
    trapper_client: TrapperClient = ctx.obj["trapper_client"]

    if not research_project or not classification_project or not collection:
        TyperUtils.fatal("No research project, classification project or collection defined.")

    # Validate that the collection exists in the given classification project
    cp_obj = trapper_client.classification_projects.get_all_by_research_project(research_project)

    cp_selected = next((obj for obj in cp_obj.results if obj.pk == classification_project), None)
    if not cp_selected:
        TyperUtils.fatal(f"Classification project {classification_project} not found in research project {research_project}.")

    collections_obj = trapper_client.collections.get_by_classification_project(classification_project)
    collection_selected = next((obj for obj in collections_obj.results if obj.collection_pk == collection), None)
    if not collection_selected:
        TyperUtils.fatal(f"Collection {collection} not found in classification project {classification_project}.")

    deployments = TyperUtils.parse_id_list(deployments_input, allow_stdin=False)
    excluded_deployments = TyperUtils.parse_id_list(exclude_deployments_input, allow_stdin=False)

    n_images_seq = n_images_seq or 5
    max_interval = max_interval or 90

    TyperUtils.info(_(f"Validating collection {collection} against {subjects_csv.name}…"))

    with make_progress() as progress:
        progress_callback = make_progress_callback(progress)
        result = connector.validate_subject_set(
            subjects_csv=subjects_csv,
            collection=collection,
            classification_project=classification_project,
            subject_set_id=subject_set_id,
            deployments=deployments,
            blacklisted_deployments=excluded_deployments,
            n_images_seq=n_images_seq,
            max_interval=max_interval,
            progress_callback=progress_callback,
        )

    from rich.table import Table
    ss_label = f" — subject set {subject_set_id}" if subject_set_id else ""

    # --- Missing ---
    missing = sorted(result["missing"])
    if missing:
        t = Table(title=f"[red]Missing media IDs{ss_label}[/red]", show_lines=False)
        t.add_column("media_id", style="red", justify="right")
        for mid in missing:
            t.add_row(str(mid))
        TyperUtils.console.print(t)
        TyperUtils.console.print(f"[red]{len(missing)} media IDs expected by Trapper but absent from the subject set[/red]")
    else:
        TyperUtils.success(_("No missing media IDs — all expected media are present in the subject set."))

    TyperUtils.console.print()

    # --- Extra ---
    extra = sorted(result["extra"])
    if extra:
        uploaded = result["uploaded"]
        t = Table(title=f"[yellow]Extra media IDs{ss_label}[/yellow]", show_lines=False)
        t.add_column("media_id", style="yellow", justify="right")
        t.add_column("subject_id", style="dim", justify="right")
        for mid in extra:
            t.add_row(str(mid), str(uploaded.get(mid, "—")))
        TyperUtils.console.print(t)
        TyperUtils.console.print(f"[yellow]{len(extra)} media IDs present in the subject set but not expected by Trapper[/yellow]")
    else:
        TyperUtils.success(_("No extra media IDs — the subject set contains no unexpected media."))

    TyperUtils.console.print()

    # --- Duplicated ---
    duplicated = result["duplicated"]
    if duplicated:
        t = Table(title=f"[red]Duplicated media IDs{ss_label}[/red]", show_lines=False)
        t.add_column("media_id", style="red", justify="right")
        t.add_column("subject_ids", style="yellow")
        for mid in sorted(duplicated):
            t.add_row(str(mid), ", ".join(str(s) for s in duplicated[mid]))
        TyperUtils.console.print(t)
        TyperUtils.console.print(f"[red]{len(duplicated)} media IDs uploaded more than once[/red]")
    else:
        TyperUtils.success(_("No duplicated media IDs."))

    TyperUtils.console.print()

    # --- Unmatched ---
    unmatched = result["unmatched"]
    if unmatched:
        t = Table(title=f"[red]Subjects without media ID{ss_label}[/red]", show_lines=False)
        t.add_column("subject_id", style="red", justify="right")
        for sid in unmatched:
            t.add_row(str(sid))
        TyperUtils.console.print(t)
        TyperUtils.console.print(f"[red]{len(unmatched)} subjects with no extractable media ID[/red]")
    else:
        TyperUtils.success(_("No unmatched subjects — all subjects have a valid media ID."))

    TyperUtils.console.print()

    # --- Metadata issues ---
    meta_issues = result["metadata_issues"]
    if meta_issues:
        t = Table(title=f"[red]Metadata issues{ss_label}[/red]", show_lines=True)
        t.add_column("subject_id", style="cyan", justify="right")
        t.add_column("media_id", style="green", justify="right")
        t.add_column("issues", style="red")
        for r in meta_issues:
            t.add_row(
                str(r["subject_id"]),
                str(r["media_id"]) if r["media_id"] is not None else "[red]—[/red]",
                "; ".join(r["issues"]),
            )
        TyperUtils.console.print(t)
        TyperUtils.console.print(f"[red]{len(meta_issues)} subjects with metadata issues[/red]")
    else:
        TyperUtils.success(_("All subjects have valid metadata."))

    TyperUtils.console.print()

    # --- Summary ---
    total_expected = len(result["expected"])
    total_uploaded = len(result["uploaded"])
    TyperUtils.console.print(
        f"Summary: [cyan]{total_expected}[/cyan] expected · "
        f"[cyan]{total_uploaded}[/cyan] uploaded · "
        f"[red]{len(missing)}[/red] missing · "
        f"[yellow]{len(extra)}[/yellow] extra · "
        f"[red]{len(duplicated)}[/red] duplicated · "
        f"[red]{len(unmatched)}[/red] unmatched · "
        f"[red]{len(meta_issues)}[/red] metadata issues"
    )


@app.command(
    help=_("Validate metadata fields of every subject in a Zooniverse subjects export file."),
    short_help=_("Check subject metadata from a subjects export"),
    rich_help_panel="Validation"
)
def check_metadata(
    ctx: typer.Context,
    subjects_csv: Annotated[
        Path,
        typer.Argument(help=_(
            "Path to the Zooniverse subjects export CSV/TSV file. "
            "To obtain it, go to https://www.zooniverse.org/lab/{project_id}/data-exports "
            "(replace {project_id} with your Zooniverse project ID), "
            "click 'Request new subject export' and download the generated file."
        )),
    ],
    subject_set_id: Annotated[
        Optional[int],
        typer.Option("--subject-set-id", "--ss", "--ss-id", help=_("Filter by subject set ID. If omitted, all rows are included.")),
    ] = None,
    all_subjects: Annotated[
        bool,
        typer.Option("--all", help=_("Show all subjects, not only those with issues.")),
    ] = False,
    pipeline: Annotated[
        bool,
        typer.Option("--pipeline", help=_("Output only subject_ids with issues separated by newlines (for shell pipelines).")),
    ] = False,
) -> None:
    """
    Read a Zooniverse subjects export file and check that every subject has complete, valid metadata.

    Required metadata fields: external_id, preview, link, thumbnail, origin, license, image_name.
    The command also verifies that a Trapper media_id can be extracted from external_id or origin.
    """
    if not subjects_csv.exists():
        TyperUtils.fatal(f"File not found: {subjects_csv}")

    results = _check_subject_metadata(subjects_csv, subject_set_id)
    invalid = [r for r in results if r["issues"]]
    ss_label = f" — subject set {subject_set_id}" if subject_set_id else ""

    if pipeline:
        for r in invalid:
            typer.echo(r["subject_id"])
        return

    from rich.table import Table

    display = results if all_subjects else invalid
    table = Table(
        title=f"Subject metadata check{ss_label}",
        show_lines=True,
    )
    table.add_column("subject_id", style="cyan", justify="right")
    table.add_column("subject_set_id", style="dim", justify="right")
    table.add_column("media_id", style="green", justify="right")
    table.add_column("issues", style="red")

    for r in display:
        issues_text = "; ".join(r["issues"]) if r["issues"] else "[green]OK[/green]"
        table.add_row(
            str(r["subject_id"]),
            str(r["subject_set_id"]),
            str(r["media_id"]) if r["media_id"] is not None else "[red]—[/red]",
            issues_text,
        )

    TyperUtils.console.print(table)

    total = len(results)
    n_invalid = len(invalid)
    if n_invalid == 0:
        TyperUtils.success(_(f"All {total} subjects have valid metadata"))
    else:
        TyperUtils.console.print(
            f"[red]{n_invalid}[/red] of {total} subjects have metadata issues"
        )


@app.command(
    name="check-missing-media",
    help=_(
        "Find media IDs that Trapper expects in Zooniverse but are absent from a subjects export CSV. "
        "Follows the same selection logic as 'import' (deployments, sequences, public-only, human-filtered)."
    ),
    short_help=_("Check for media IDs missing from a subjects export"),
    rich_help_panel="Validation",
)
def check_missing_media(
    ctx: typer.Context,
    subjects_csv: Annotated[
        Path,
        typer.Argument(help=_(
            "Path to the Zooniverse subjects export CSV/TSV file. "
            "To obtain it, go to https://www.zooniverse.org/lab/{project_id}/data-exports "
            "and click 'Request new subject export'."
        )),
    ],
    collection: Annotated[int, typer.Argument(help=_("Collection ID in Trapper."))],
    research_project: Annotated[
        int,
        typer.Option("--rp", "--research-project", help=_("ID of the research project.")),
    ] = None,
    classification_project: Annotated[
        int,
        typer.Option("--cp", "--classification-project", help=_("ID of the classification project linked to the collection.")),
    ] = None,
    subject_set_id: Annotated[
        Optional[int],
        typer.Option("--subject-set-id", "--ss", "--ss-id", help=_("Filter the CSV by subject set ID. If omitted, all rows are included.")),
    ] = None,
    deployments_input: Annotated[
        Optional[str],
        typer.Option("--deployments", "--d", help=_("Deployment IDs (comma or space separated). If omitted, auto-detected from collection name.")),
    ] = None,
    exclude_deployments_input: Annotated[
        Optional[str],
        typer.Option("--exclude-deployments", "--ed", help=_("Deployment IDs to skip.")),
    ] = None,
    n_images_seq: Annotated[int, typer.Option("--n-images-seq", help=_("Number of images per sequence."))] = None,
    max_interval: Annotated[int, typer.Option("--max-interval", help=_("Maximum interval between images in a sequence (seconds)."))] = None,
    pipeline: Annotated[
        bool,
        typer.Option("--pipeline", help=_("Output only missing media_ids separated by newlines (for shell pipelines).")),
    ] = False,
    config: Annotated[Path, typer.Option(hidden=True, callback=callback_with_override)] = None,
) -> None:
    """
    Compute the set of media_ids Trapper expects in Zooniverse and report those absent from the CSV.
    """
    if not subjects_csv.exists():
        TyperUtils.fatal(f"File not found: {subjects_csv}")

    connector: TrapperZooniverseConnector = ctx.obj["connector"]
    trapper_client: TrapperClient = ctx.obj["trapper_client"]

    if not research_project or not classification_project or not collection:
        TyperUtils.fatal("No research project, classification project or collection defined.")

    cp_obj = trapper_client.classification_projects.get_all_by_research_project(research_project)
    cp_selected = next((obj for obj in cp_obj.results if obj.pk == classification_project), None)
    if not cp_selected:
        TyperUtils.fatal(f"Classification project {classification_project} not found in research project {research_project}.")

    collections_obj = trapper_client.collections.get_by_classification_project(classification_project)
    collection_selected = next((obj for obj in collections_obj.results if obj.collection_pk == collection), None)
    if not collection_selected:
        TyperUtils.fatal(f"Collection {collection} not found in classification project {classification_project}.")

    deployments = TyperUtils.parse_id_list(deployments_input, allow_stdin=False)
    excluded_deployments = TyperUtils.parse_id_list(exclude_deployments_input, allow_stdin=False)
    n_images_seq = n_images_seq or 5
    max_interval = max_interval or 90

    TyperUtils.info(_(f"Checking missing media for collection {collection} against {subjects_csv.name}…"))

    with make_progress() as progress:
        progress_callback = make_progress_callback(progress)
        missing = connector.missing_media_id(
            subjects_csv=subjects_csv,
            collection=collection,
            classification_project=classification_project,
            subject_set_id=subject_set_id,
            deployments=deployments,
            blacklisted_deployments=excluded_deployments,
            n_images_seq=n_images_seq,
            max_interval=max_interval,
            progress_callback=progress_callback,
        )

    if pipeline:
        for mid in sorted(missing):
            typer.echo(mid)
        return

    from rich.table import Table

    ss_label = f" — subject set {subject_set_id}" if subject_set_id else ""

    if not missing:
        TyperUtils.success(_(f"No missing media IDs{ss_label} — all expected media are present in the CSV."))
        return

    table = Table(title=f"[red]Missing media IDs{ss_label}[/red]", show_lines=False)
    table.add_column("media_id", style="red", justify="right")
    for mid in sorted(missing):
        table.add_row(str(mid))

    TyperUtils.console.print(table)
    TyperUtils.console.print(
        f"[red]{len(missing)}[/red] media ID(s) expected by Trapper but absent from the CSV"
    )


@app.command(
    name="check-duplicated-media",
    help=_("Find media IDs that appear more than once in a Zooniverse subjects export CSV."),
    short_help=_("Check for duplicate media IDs in a subjects export"),
    rich_help_panel="Validation",
)
def check_duplicated_media(
    ctx: typer.Context,
    subjects_csv: Annotated[
        Path,
        typer.Argument(help=_(
            "Path to the Zooniverse subjects export CSV/TSV file. "
            "To obtain it, go to https://www.zooniverse.org/lab/{project_id}/data-exports "
            "and click 'Request new subject export'."
        )),
    ],
    subject_set_id: Annotated[
        Optional[int],
        typer.Option("--subject-set-id", "--ss", "--ss-id", help=_("Filter by subject set ID. If omitted, all rows are included.")),
    ] = None,
    pipeline: Annotated[
        bool,
        typer.Option("--pipeline", help=_("Output only duplicated media_ids separated by newlines (for shell pipelines).")),
    ] = False,
) -> None:
    """
    Read a Zooniverse subjects export and report every media_id that is linked to more
    than one subject_id (i.e. the same Trapper media was uploaded multiple times).
    """
    if not subjects_csv.exists():
        TyperUtils.fatal(f"File not found: {subjects_csv}")

    connector: TrapperZooniverseConnector = ctx.obj["connector"]

    with make_progress() as progress:
        progress_callback = make_progress_callback(progress)
        duplicates = connector.duplicated_media_id(subjects_csv, subject_set_id, progress_callback)

    if pipeline:
        for mid in sorted(duplicates):
            typer.echo(mid)
        return

    from rich.table import Table

    ss_label = f" — subject set {subject_set_id}" if subject_set_id else ""

    if not duplicates:
        TyperUtils.success(_(f"No duplicate media IDs found{ss_label}."))
        return

    table = Table(
        title=f"[red]Duplicate media IDs{ss_label}[/red]",
        show_lines=False,
    )
    table.add_column("media_id", style="red", justify="right")
    table.add_column("subject_ids", style="yellow")

    for mid in sorted(duplicates):
        sids = duplicates[mid]
        table.add_row(str(mid), ", ".join(str(s) for s in sids))

    TyperUtils.console.print(table)
    TyperUtils.console.print(
        f"[red]{len(duplicates)}[/red] media ID(s) appear in more than one subject"
    )


@app.command(
    name="check-unmatched-subjects",
    help=_("Find subjects in a Zooniverse subjects export that have no extractable Trapper media ID."),
    short_help=_("Check for subjects without a linked media ID"),
    rich_help_panel="Validation",
)
def check_unmatched_subjects(
    ctx: typer.Context,
    subjects_csv: Annotated[
        Path,
        typer.Argument(help=_(
            "Path to the Zooniverse subjects export CSV/TSV file. "
            "To obtain it, go to https://www.zooniverse.org/lab/{project_id}/data-exports "
            "and click 'Request new subject export'."
        )),
    ],
    subject_set_id: Annotated[
        Optional[int],
        typer.Option("--subject-set-id", "--ss", "--ss-id", help=_("Filter by subject set ID. If omitted, all rows are included.")),
    ] = None,
    pipeline: Annotated[
        bool,
        typer.Option("--pipeline", help=_("Output only unmatched subject_ids separated by newlines (for shell pipelines).")),
    ] = False,
) -> None:
    """
    Read a Zooniverse subjects export and list every subject_id from which
    no Trapper media_id can be extracted (missing or malformed metadata).
    """
    if not subjects_csv.exists():
        TyperUtils.fatal(f"File not found: {subjects_csv}")

    connector: TrapperZooniverseConnector = ctx.obj["connector"]

    with make_progress() as progress:
        progress_callback = make_progress_callback(progress)
        unmatched = connector.unmatched_subject_id(subjects_csv, subject_set_id, progress_callback)

    if pipeline:
        for sid in unmatched:
            typer.echo(sid)
        return

    from rich.table import Table

    ss_label = f" — subject set {subject_set_id}" if subject_set_id else ""

    if not unmatched:
        TyperUtils.success(_(f"No unmatched subjects found{ss_label}."))
        return

    table = Table(
        title=f"[red]Subjects without media ID{ss_label}[/red]",
        show_lines=False,
    )
    table.add_column("subject_id", style="red", justify="right")

    for sid in unmatched:
        table.add_row(str(sid))

    TyperUtils.console.print(table)
    TyperUtils.console.print(
        f"[red]{len(unmatched)}[/red] subject(s) with no extractable media ID"
    )


from wildintel_tools.ui.typer.commands.wizards.zooniverse import register_wizard_command
register_wizard_command(app, callback_with_override)
