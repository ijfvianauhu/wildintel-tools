from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import SecretStr
from trapper_client.Schemas import TrapperDeploymentList
from trapper_client.TrapperClient import TrapperClient

from wildintel_tools.ui.typer.settings import (
    Settings, ZooniverseSettings, ZooniverseConnectorSettings, get_app_documents_dir,
)
from wildintel_tools.ui.typer.settings_manager import SettingsManager
from wildintel_tools.ui.typer.zooniverse import get_workflows, get_subject_sets
from wildintel_tools.ui.typer.commands.zooniverse import download_ss, export_annotations, validate_subject_set
from wildintel_tools.ui.typer.TyperUtils import TyperUtils
from wildintel_tools.ui.typer.i18n import _
from wildintel_tools.zooniverse.ZooniverseClient import ZooniverseClient


class Wizard(str, Enum):
    importation = "import"
    setup       = "setup"
    export      = "export"
    download    = "download"
    validate    = "validate"


def _print_section(title: str) -> None:
    TyperUtils.console.print()
    TyperUtils.console.print(f"[green]{'━' * 67}[/green]")
    TyperUtils.console.print(f"[green]  {title}[/green]")
    TyperUtils.console.print(f"[green]{'━' * 67}[/green]")


def run_import_wizard(ctx: typer.Context, settings: Settings) -> None:
    from wildintel_tools.ui.typer.commands.zooniverse import importation

    _print_section("Import images from Trapper to Zooniverse")
    TyperUtils.console.print()
    TyperUtils.console.print("[blue]ℹ[/blue] This wizard will guide you through the process of importing a Trapper collection ")
    TyperUtils.console.print("    into a Zooniverse subject set. As a general rule, only blank images and images ")
    TyperUtils.console.print("    that contain animals will be imported.")
    TyperUtils.console.print()

    if not typer.confirm("Continue?"):
        typer.echo("Aborted.")
        return

    trapper_client = TrapperClient(
        base_url=str(settings.GENERAL.host),
        user_name=settings.GENERAL.login,
        user_password=settings.GENERAL.password.get_secret_value(),
        access_token=None,
    )

    rp = trapper_client.research_projects.get_all()
    TyperUtils.console.print()
    rp_selected = TyperUtils.select_box(
        rp.results, id_attr="pk", name_attr="name", label="Select a research project", multi_select=False,
    )

    cp = trapper_client.classification_projects.get_by_research_project(rp_selected.pk)
    if len(cp.results) == 0:
        TyperUtils.fatal(
            f"No classification project found in research project "
            f"{rp_selected.name} ({rp_selected.pk}). Cannot continue."
        )

    TyperUtils.console.print()
    cp_selected = TyperUtils.select_box(
        cp.results, id_attr="pk", name_attr="name", label="Select a classification project", multi_select=False,
    )

    collections = trapper_client.collections.get_by_classification_project(cp_selected.pk)
    TyperUtils.console.print()
    collection_selected = TyperUtils.select_box(
        collections.results, id_attr="collection_pk", name_attr="name", label="Select a collection", multi_select=False,
    )

    TyperUtils.console.print()
    deployments: TrapperDeploymentList = trapper_client.deployments.get_all(
        query={"research_project": rp_selected.pk}
    )
    prefix = f"{collection_selected.name}-".lower()
    filtered = [d for d in deployments.results if d.deployment_id.lower().startswith(prefix)]

    TyperUtils.console.print()
    deployment_selected = TyperUtils.select_box(
        filtered, id_attr="pk", name_attr="deployment_id", label="Select a deployment", multi_select=True,
    )

    if not deployment_selected:
        TyperUtils.fatal("No deployment selected.")

    deployment_pks = [str(d.pk) for d in deployment_selected]
    deployments_str = ",".join(deployment_pks)
    deployments_info = ", ".join([f"{d.deployment_id} ({d.pk})" for d in deployment_selected])

    TyperUtils.console.print()
    default_subjectset_name = (
        f"{rp_selected.name}_{rp_selected.pk}"
        f"_{collection_selected.name}_{collection_selected.collection_pk}"
        f"_{datetime.now():%Y-%m}"
    )
    subjectset_name = typer.prompt("Subject set name", default=default_subjectset_name)

    msg = (
        f"We are going to import the images taken during deployments {deployments_info} "
        f"from collection {collection_selected.name} ({collection_selected.collection_pk}) "
        f"into Zooniverse subject set {subjectset_name}, using detection data from classification project "
        f"{cp_selected.name} ({cp_selected.pk}) "
        f"within research project {rp_selected.name} ({rp_selected.pk}). "
        f"Are you sure?"
    )
    TyperUtils.console.print()

    if not typer.confirm(msg):
        typer.echo("Aborted.")
        return

    TyperUtils.console.print()
    dry_run = typer.confirm(
        "Do you want to run in DRY-RUN mode? "
        "(No images will be downloaded, no subject set will be created and nothing will be uploaded to Zooniverse)",
        default=False,
    )
    if dry_run:
        TyperUtils.console.print("[bold yellow]⚠  DRY-RUN mode enabled.[/bold yellow]")
    TyperUtils.console.print()

    importation(
        ctx,
        collection=collection_selected.collection_pk,
        research_project=rp_selected.pk,
        classification_project=cp_selected.pk,
        deployments_input=deployments_str,
        subjectset_name=subjectset_name,
        n_images_seq=settings.ZOONIVERSE_CONNECTOR.upload_collection_n_images_seq,
        max_interval=settings.ZOONIVERSE_CONNECTOR.upload_collection_max_interval,
        dry_run=dry_run,
    )
    typer.echo("Continuing...")


def run_export_wizard(ctx: typer.Context, settings: Settings) -> None:
    _print_section("Export annotations from a Zooniverse subject set to Trapper")
    TyperUtils.console.print()
    TyperUtils.console.print("[blue]ℹ[/blue] This wizard will guide you through exporting Zooniverse classification")
    TyperUtils.console.print("    results back to Trapper as observations. You will need to select")
    TyperUtils.console.print("    the subject set, the research project and the classification project.")
    TyperUtils.console.print()

    if not typer.confirm("Continue?"):
        typer.echo("Aborted.")
        return

    trapper_client = TrapperClient(
        base_url=str(settings.GENERAL.host),
        user_name=settings.GENERAL.login,
        user_password=settings.GENERAL.password.get_secret_value(),
        access_token=None,
    )
    zooniverse_client = ZooniverseClient(
        project_id=settings.ZOONIVERSE.zooniverse_project_id,
        username=settings.ZOONIVERSE.zooniverse_username,
        password=settings.ZOONIVERSE.zooniverse_password.get_secret_value(),
    )

    TyperUtils.console.print()
    TyperUtils.info("Retrieving workflows from Zooniverse...")
    wfs = get_workflows(zooniverse_client)
    if not wfs:
        TyperUtils.fatal("No workflows found in the Zooniverse project. Cannot continue.")

    wf_selected = TyperUtils.select_box(
        wfs, id_attr="id", name_attr="display_name", label="Select a workflow", multi_select=False,
    )
    TyperUtils.console.print(
        f"[green]✓[/green] Workflow selected: [bold]{wf_selected.display_name}[/bold] (id: {wf_selected.id})"
    )

    TyperUtils.console.print()
    TyperUtils.info("Retrieving subject sets from Zooniverse...")
    subject_sets = get_subject_sets(zooniverse_client)
    if not subject_sets:
        TyperUtils.fatal("No subject sets found in the Zooniverse project. Cannot continue.")

    ss_selected = TyperUtils.select_box(
        subject_sets, id_attr="id", name_attr="display_name", label="Select a subject set", multi_select=False,
    )
    TyperUtils.console.print(
        f"[green]✓[/green] Subject set selected: [bold]{ss_selected.display_name}[/bold] (id: {ss_selected.id})"
    )

    TyperUtils.console.print()
    rp = trapper_client.research_projects.get_all()
    if not rp.results:
        TyperUtils.fatal("No research projects found in Trapper. Cannot continue.")

    rp_selected = TyperUtils.select_box(
        rp.results, id_attr="pk", name_attr="name", label="Select a research project", multi_select=False,
    )
    TyperUtils.console.print(
        f"[green]✓[/green] Research project selected: [bold]{rp_selected.name}[/bold] (id: {rp_selected.pk})"
    )

    cp = trapper_client.classification_projects.get_by_research_project(rp_selected.pk)
    if not cp.results:
        TyperUtils.fatal(
            f"No classification projects found in research project "
            f"{rp_selected.name} ({rp_selected.pk}). Cannot continue."
        )

    TyperUtils.console.print()
    cp_selected = TyperUtils.select_box(
        cp.results, id_attr="pk", name_attr="name", label="Select a classification project", multi_select=False,
    )
    TyperUtils.console.print(
        f"[green]✓[/green] Classification project selected: [bold]{cp_selected.name}[/bold] (id: {cp_selected.pk})"
    )

    collections = trapper_client.collections.get_by_classification_project(cp_selected.pk)
    if not collections.results:
        TyperUtils.fatal(
            f"No collections found in classification project "
            f"{cp_selected.name} ({cp_selected.pk}). Cannot continue."
        )

    TyperUtils.console.print()
    collection_selected = TyperUtils.select_box(
        collections.results, id_attr="collection_pk", name_attr="name",
        label="Select a collection", multi_select=False,
    )

    deployments: TrapperDeploymentList = trapper_client.deployments.get_all(
        query={"research_project": rp_selected.pk}
    )
    prefix = f"{collection_selected.name}-".lower()
    filtered = [d for d in deployments.results if d.deployment_id.lower().startswith(prefix)]

    if not filtered:
        TyperUtils.fatal(
            f"No deployments found in collection {collection_selected.name}. Cannot continue."
        )

    TyperUtils.console.print()
    deployment_selected = TyperUtils.select_box(
        filtered, id_attr="pk", name_attr="deployment_id", label="Select deployment", multi_select=True,
    )

    deployments_str_list = [f"{d.deployment_id} ({d.pk})" for d in deployment_selected]
    TyperUtils.console.print()
    msg = (
        f"We are going to export the annotations from subject set "
        f"{ss_selected.display_name} ({ss_selected.id}) "
        f"using workflow {wf_selected.display_name} ({wf_selected.id}) "
        f"into deployments {', '.join(deployments_str_list)} "
        f"from collection {collection_selected.name} ({collection_selected.collection_pk}) "
        f"of classification project {cp_selected.name} ({cp_selected.pk}) "
        f"within research project {rp_selected.name} ({rp_selected.pk}). "
        f"Are you sure?"
    )

    if not typer.confirm(msg):
        typer.echo("Aborted.")
        return

    default_csv_name = (
        f"zoo_annotations_{wf_selected.id}_{ss_selected.id}"
        f"_{collection_selected.collection_pk}_{cp_selected.pk}"
        f"_{datetime.now():%Y%m%d%H%M}.csv"
    )
    output_dir = get_app_documents_dir() / "zooniverse"
    output_dir.mkdir(parents=True, exist_ok=True)
    default_observations_file = str(output_dir / default_csv_name)
    TyperUtils.console.print()
    observations_filename = typer.prompt("CSV file to save annotations", default=default_observations_file)
    observations_file = Path(observations_filename)

    verbose = typer.confirm("Show detail for each processed media in the progress bar?", default=True)
    save_zoo_annotations = typer.confirm(
        "Save the raw Zooniverse annotations (extracted user opinions) as a separate CSV?", default=True
    )

    TyperUtils.console.print()
    if not typer.confirm("Ready to export. Proceed?"):
        typer.echo("Aborted.")
        return
    TyperUtils.console.print()

    all_selected = len(deployment_selected) == len(filtered)
    deployments_arg = None if all_selected else [d.pk for d in deployment_selected]

    export_annotations(
        ctx,
        wf_id=wf_selected.id,
        ss_id=ss_selected.id,
        classification_project=cp_selected.pk,
        collection=collection_selected.collection_pk,
        deployments=deployments_arg,
        observations_file=observations_file,
        verbose=verbose,
        save_zoo_annotations=save_zoo_annotations,
    )
    typer.echo("Continuing...")


def run_setup_wizard(ctx: typer.Context, settings: Settings, settings_manager: SettingsManager) -> None:
    _print_section("Configure zooniverse module")
    TyperUtils.console.print()
    TyperUtils.console.print("[blue]ℹ[/blue] This wizard will guide you through Zooniverse connection settings. ")
    TyperUtils.console.print()

    if not typer.confirm("Continue?"):
        typer.echo("Aborted.")
        return

    project_name = str(ctx.obj.get("project", "default"))
    try:
        settings = settings_manager.load_settings(project_name)
    except FileNotFoundError:
        settings = None

    username_default = settings.ZOONIVERSE.zooniverse_username if settings else "myuser"
    password_default = settings.ZOONIVERSE.zooniverse_password.get_secret_value() if settings else "mypassword"
    project_id_default = settings.ZOONIVERSE.zooniverse_project_id if settings else "myprojectid"
    seq_default = str(settings.ZOONIVERSE_CONNECTOR.upload_collection_n_images_seq if settings else 5)
    max_interval_default = str(settings.ZOONIVERSE_CONNECTOR.upload_collection_max_interval if settings else 90)
    attempts_default = str(settings.ZOONIVERSE_CONNECTOR.upload_collection_attempts if settings else 5)
    delay_default = str(settings.ZOONIVERSE_CONNECTOR.upload_collection_delay if settings else 15)
    max_per_subject_default = str(
        settings.ZOONIVERSE_CONNECTOR.upload_collection_max_attempts_per_subject if settings else 5
    )
    delay_per_subject_default = str(
        settings.ZOONIVERSE_CONNECTOR.upload_collection_delay_seconds_per_subject if settings else 30
    )
    classified_by_default = (
        settings.ZOONIVERSE_CONNECTOR.annotations_classified_by if settings else "zooniverse@wildintel-project.org"
    )

    zooniverse_username = TyperUtils.prompt_with_default(
        "Enter your Zooniverse username", username_default, ZooniverseSettings, "zooniverse_username"
    )
    zooniverse_password = TyperUtils.prompt_with_default(
        "Enter your Zooniverse password", password_default, ZooniverseSettings, "zooniverse_password",
        show_default=False,
    )
    zooniverse_project_id = TyperUtils.prompt_with_default(
        "Enter your Zooniverse project ID", project_id_default, ZooniverseSettings, "zooniverse_project_id"
    )
    upload_collection_n_images_seq = int(TyperUtils.prompt_with_default(
        "Number of images per upload batch", seq_default,
        ZooniverseConnectorSettings, "upload_collection_n_images_seq",
    ))
    upload_collection_max_interval = int(TyperUtils.prompt_with_default(
        "Maximum interval between upload batches (seconds)", max_interval_default,
        ZooniverseConnectorSettings, "upload_collection_max_interval",
    ))
    upload_collection_attempts = int(TyperUtils.prompt_with_default(
        "Maximum upload attempts per batch", attempts_default,
        ZooniverseConnectorSettings, "upload_collection_attempts",
    ))
    upload_collection_delay = int(TyperUtils.prompt_with_default(
        "Delay between upload attempts (seconds)", delay_default,
        ZooniverseConnectorSettings, "upload_collection_delay",
    ))
    upload_collection_max_attempts_per_subject = int(TyperUtils.prompt_with_default(
        "Maximum attempts per subject", max_per_subject_default,
        ZooniverseConnectorSettings, "upload_collection_max_attempts_per_subject",
    ))
    upload_collection_delay_seconds_per_subject = int(TyperUtils.prompt_with_default(
        "Delay per subject (seconds)", delay_per_subject_default,
        ZooniverseConnectorSettings, "upload_collection_delay_seconds_per_subject",
    ))
    annotations_classified_by = TyperUtils.prompt_with_default(
        "Trapper username for Zooniverse observations (classifiedBy)", classified_by_default,
        ZooniverseConnectorSettings, "annotations_classified_by",
    )

    updates = {
        "ZOONIVERSE.zooniverse_username": zooniverse_username,
        "ZOONIVERSE.zooniverse_password": zooniverse_password,
        "ZOONIVERSE.zooniverse_project_id": zooniverse_project_id,
        "ZOONIVERSE_CONNECTOR.upload_collection_n_images_seq": upload_collection_n_images_seq,
        "ZOONIVERSE_CONNECTOR.upload_collection_max_interval": upload_collection_max_interval,
        "ZOONIVERSE_CONNECTOR.upload_collection_attempts": upload_collection_attempts,
        "ZOONIVERSE_CONNECTOR.upload_collection_delay": upload_collection_delay,
        "ZOONIVERSE_CONNECTOR.upload_collection_max_attempts_per_subject": upload_collection_max_attempts_per_subject,
        "ZOONIVERSE_CONNECTOR.upload_collection_delay_seconds_per_subject": upload_collection_delay_seconds_per_subject,
        "ZOONIVERSE_CONNECTOR.annotations_classified_by": annotations_classified_by,
    }

    val = [
        {"Setting": key, "Value": "********" if "password" in key.lower() else str(value)}
        for key, value in updates.items()
    ]
    TyperUtils.show_table(val, "Settings to update")

    if typer.confirm("Do you want to apply these changes?"):
        settings_manager.update_settings(project_name, updates)
        TyperUtils.console.print(
            f"[bold green]Zooniverse configuration for project '{project_name}' "
            f"saved successfully![/bold green]"
        )
    else:
        TyperUtils.console.print("[bold red]Aborted. No changes were made.[/bold red]")


def run_download_wizard(ctx: typer.Context, settings: Settings) -> None:
    _print_section("Download subjects from a Zooniverse subject set")
    TyperUtils.console.print()
    TyperUtils.console.print("[blue]ℹ[/blue] This wizard will guide you through downloading images from one or more")
    TyperUtils.console.print("    Zooniverse subject sets to a local directory.")
    TyperUtils.console.print()

    if not typer.confirm("Continue?"):
        typer.echo("Aborted.")
        return

    zooniverse_client = ZooniverseClient(
        project_id=settings.ZOONIVERSE.zooniverse_project_id,
        username=settings.ZOONIVERSE.zooniverse_username,
        password=settings.ZOONIVERSE.zooniverse_password.get_secret_value(),
    )

    TyperUtils.console.print()
    TyperUtils.info("Retrieving subject sets from Zooniverse...")
    subject_sets = get_subject_sets(zooniverse_client)
    if not subject_sets:
        TyperUtils.fatal("No subject sets found in the Zooniverse project. Cannot continue.")

    selected = TyperUtils.select_box(
        subject_sets,
        id_attr="id",
        name_attr="display_name",
        label="Select subject set(s) to download",
        multi_select=True,
    )
    if not selected:
        TyperUtils.fatal("No subject set selected.")

    ss_ids = [ss.id for ss in selected]
    TyperUtils.console.print(
        f"[green]✓[/green] Selected {len(ss_ids)} subject set(s): "
        + ", ".join(f"{ss.display_name} ({ss.id})" for ss in selected)
    )

    TyperUtils.console.print()
    default_out = str(Path.home() / "Downloads" / "zooniverse")
    out_dir_str = typer.prompt("Output directory", default=default_out)
    out_put_dir = Path(out_dir_str)

    TyperUtils.console.print()
    max_workers = int(typer.prompt("Number of download threads", default="4"))
    overwrite = typer.confirm("Overwrite existing files?", default=False)
    verbose = typer.confirm("Show detail for each downloaded subject?", default=True)

    TyperUtils.console.print()
    msg = (
        f"We are going to download {len(ss_ids)} subject set(s) "
        f"into '{out_put_dir}' using {max_workers} thread(s). "
        f"Are you sure?"
    )
    if not typer.confirm(msg):
        typer.echo("Aborted.")
        return

    TyperUtils.console.print()
    download_ss(
        ctx,
        ss_ids=ss_ids,
        out_put_dir=out_put_dir,
        max_workers=max_workers,
        overwrite=overwrite,
        verbose=verbose,
    )


def run_validate_wizard(ctx: typer.Context, settings: Settings) -> None:
    _print_section("Validate a Zooniverse subject set against a Trapper collection")
    TyperUtils.console.print()
    TyperUtils.console.print("[blue]ℹ[/blue] This wizard will guide you through validating that the subjects in a")
    TyperUtils.console.print("    Zooniverse export file match the expected media from a Trapper collection.")
    TyperUtils.console.print("    You will need a Zooniverse subjects export CSV/TSV file.")
    TyperUtils.console.print("    You can download it from [bold]https://www.zooniverse.org/lab/{project_id}/data-exports[/bold]")
    TyperUtils.console.print("    under [bold]Request new subject export[/bold].")
    TyperUtils.console.print()

    if not typer.confirm("Continue?"):
        typer.echo("Aborted.")
        return

    subjects_csv_str = typer.prompt("Path to the Zooniverse subjects export CSV/TSV file")
    subjects_csv = Path(subjects_csv_str)
    if not subjects_csv.exists():
        TyperUtils.fatal(f"File not found: {subjects_csv}")

    trapper_client = TrapperClient(
        base_url=str(settings.GENERAL.host),
        user_name=settings.GENERAL.login,
        user_password=settings.GENERAL.password.get_secret_value(),
        access_token=None,
    )

    TyperUtils.console.print()
    rp = trapper_client.research_projects.get_all()
    if not rp.results:
        TyperUtils.fatal("No research projects found in Trapper. Cannot continue.")
    rp_selected, _ = TyperUtils.select_from_list(rp.results, title="Select a research project")

    cp = trapper_client.classification_projects.get_by_research_project(rp_selected.pk)
    if not cp.results:
        TyperUtils.fatal(
            f"No classification projects found in research project "
            f"{rp_selected.name} ({rp_selected.pk}). Cannot continue."
        )
    TyperUtils.console.print()
    cp_selected, _ = TyperUtils.select_from_list(cp.results, title="Select a classification project")

    collections = trapper_client.collections.get_by_classification_project(cp_selected.pk)
    if not collections.results:
        TyperUtils.fatal(
            f"No collections found in classification project "
            f"{cp_selected.name} ({cp_selected.pk}). Cannot continue."
        )
    TyperUtils.console.print()
    collection_selected, _ = TyperUtils.select_from_list(
        collections.results, id_attr="collection_pk", title="Select a collection"
    )

    TyperUtils.console.print()
    ss_id_str = typer.prompt(
        "Subject set ID to filter the CSV (leave blank to include all rows)",
        default="",
    )
    subject_set_id = int(ss_id_str) if ss_id_str.strip() else None

    TyperUtils.console.print()
    deployments = trapper_client.deployments.get_all(
        query={"research_project": rp_selected.pk}
    )
    prefix = f"{collection_selected.name}-".lower()
    filtered = [d for d in deployments.results if d.deployment_id.lower().startswith(prefix)]

    deployment_selected = []
    if filtered:
        TyperUtils.console.print()
        deployment_selected, _ = TyperUtils.select_from_list(
            filtered, name_attr="deployment_id", title="Select deployments to validate (leave empty for all)", multi_select=True
        )

    deployment_pks = [str(d.pk) for d in deployment_selected] if deployment_selected else []
    deployments_str = ",".join(deployment_pks) if deployment_pks else None
    deployments_info = ", ".join(f"{d.deployment_id} ({d.pk})" for d in deployment_selected) if deployment_selected else "all"

    TyperUtils.console.print()
    msg = (
        f"We are going to validate subjects in [bold]{subjects_csv.name}[/bold] "
        f"against collection {collection_selected.name} ({collection_selected.collection_pk}), "
        f"classification project {cp_selected.name} ({cp_selected.pk}), "
        f"research project {rp_selected.name} ({rp_selected.pk}), "
        f"deployments: {deployments_info}"
    )
    if subject_set_id:
        msg += f", subject set ID: {subject_set_id}"
    msg += ". Are you sure?"
    TyperUtils.console.print(msg)
    TyperUtils.console.print()

    if not typer.confirm("Proceed?"):
        typer.echo("Aborted.")
        return

    TyperUtils.console.print()
    validate_subject_set(
        ctx,
        subjects_csv=subjects_csv,
        collection=collection_selected.collection_pk,
        research_project=rp_selected.pk,
        classification_project=cp_selected.pk,
        subject_set_id=subject_set_id,
        deployments_input=deployments_str,
        exclude_deployments_input=None,
        n_images_seq=settings.ZOONIVERSE_CONNECTOR.upload_collection_n_images_seq,
        max_interval=settings.ZOONIVERSE_CONNECTOR.upload_collection_max_interval,
    )


def register_wizard_command(app: typer.Typer, callback_with_override: Any) -> None:
    @app.command(
        "wizard",
        short_help=_("Run a wizard to guide you through completing a task."),
        help=_("Run a wizard to guide you through completing a task."),
    )
    def wizard_command(
        ctx: typer.Context,
        wizard: Annotated[Wizard, typer.Argument(help="Wizard type to run")] = ...,
        config: Annotated[Path, typer.Option(hidden=True, callback=callback_with_override)] = None,
    ) -> None:
        settings: Settings = ctx.obj.get("settings", Settings())
        settings_manager: SettingsManager = ctx.obj.get("setting_manager", SettingsManager())

        if wizard == Wizard.importation:
            run_import_wizard(ctx, settings)
        elif wizard == Wizard.export:
            run_export_wizard(ctx, settings)
        elif wizard == Wizard.setup:
            run_setup_wizard(ctx, settings, settings_manager)
        elif wizard == Wizard.download:
            run_download_wizard(ctx, settings)
        elif wizard == Wizard.validate:
            run_validate_wizard(ctx, settings)
