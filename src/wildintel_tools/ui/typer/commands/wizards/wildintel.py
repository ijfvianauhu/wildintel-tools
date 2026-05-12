from enum import Enum
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import typer
from trapper_client.TrapperClient import TrapperClient
from typing_extensions import Annotated

import wildintel_tools.ui.typer.wildintel as wildintel_ui
from wildintel_tools.ui.typer.TyperUtils import TyperUtils
from wildintel_tools.ui.typer.i18n import _
from wildintel_tools.ui.typer.settings import GeneralSettings, WildIntelSettings, Settings
from wildintel_tools.ui.typer.settings_manager import SettingsManager


class Wizard(str, Enum):
    config = "config"
    setup = "setup"
    import_deployment = "import_deployment"


def _print_section(title: str) -> None:
    TyperUtils.console.print()
    TyperUtils.console.print(f"[green]{'━' * 67}[/green]")
    TyperUtils.console.print(f"[green]  {title}[/green]")
    TyperUtils.console.print(f"[green]{'━' * 67}[/green]")


def run_setup_wizard(ctx: typer.Context, settings: Settings, settings_manager: SettingsManager) -> None:
    _print_section("Configure WildINTEL connection and project settings")
    TyperUtils.console.print()
    TyperUtils.console.print("[blue]ℹ[/blue] This wizard will guide you through the initial configuration of the application.")
    TyperUtils.console.print("    You will set the Trapper server URL, your login credentials, the project,")
    TyperUtils.console.print("    and the WildINTEL-specific metadata fields.")
    TyperUtils.console.print()

    if not typer.confirm("Continue?"):
        typer.echo("Aborted.")
        return

    project_name = str(ctx.obj.get("project", "default"))

    host_default = settings.GENERAL.host if settings else "https://wildintel-trap.uhu.es/"
    login_default = settings.GENERAL.login if settings else "user@example.com"
    password_default = settings.GENERAL.password.get_secret_value() if settings else ""
    project_id_default = str(settings.GENERAL.project_id) if settings else "123"
    data_dir_default = str(settings.GENERAL.data_dir) if settings else str(
        Path.home() / ".wildintel-tools/collections"
    )

    _print_section("Trapper connection")
    TyperUtils.console.print()

    while True:
        host = TyperUtils.prompt_with_default(
            "Enter the Trapper instance URL", host_default, GeneralSettings, "host"
        )
        login = TyperUtils.prompt_with_default(
            "Enter your email login", login_default, GeneralSettings, "login"
        )
        password = TyperUtils.prompt_with_default(
            "Enter your password", password_default, GeneralSettings, "password",
            show_default=False,
        )

        try:
            trapper_client = TrapperClient(
                base_url=str(host),
                user_name=login,
                user_password=password,
                access_token=None,
            )
            cp = trapper_client.classification_projects.get_all()
            TyperUtils.console.print("[green]✓[/green] Connected to Trapper successfully.")
            break
        except Exception as e:
            TyperUtils.error(
                _("Could not connect to Trapper with the provided credentials: {0}").format(str(e))
            )
            if not typer.confirm(_("Do you want to try again?"), default=True):
                typer.echo("Aborted.")
                return
            host_default = str(host)
            login_default = str(login)
            password_default = str(password)

    TyperUtils.console.print()
    cp_selected = TyperUtils.select_box(
        cp.results, id_attr="pk", name_attr="name",
        label=f"Select a classification project [default: {project_id_default}]",
        multi_select=False,
    )
    project_id = getattr(cp_selected, "pk", project_id_default)

    data_dir = TyperUtils.prompt_with_default(
        "Enter the directory for project collections", data_dir_default, GeneralSettings, "data_dir"
    )

    _print_section("WildINTEL metadata")
    TyperUtils.console.print()

    rp_name_default = settings.WILDINTEL.rp_name if settings else "WildINTEL"
    coverage_default = settings.WILDINTEL.coverage if settings else "Doñana National Park"
    output_dir_default = str(settings.WILDINTEL.output_dir) if settings else str(
        Path.home() / ".wildintel-tools/readycollections"
    )
    timezone_default = settings.WILDINTEL.timezone if settings else "UTC"

    rp_name = TyperUtils.prompt_with_default(
        "Enter the research project name", rp_name_default, WildIntelSettings, "rp_name"
    )
    coverage = TyperUtils.prompt_with_default(
        "Enter the coverage area", coverage_default, WildIntelSettings, "coverage"
    )
    output_dir = TyperUtils.prompt_with_default(
        "Enter the directory for processed collections", output_dir_default, WildIntelSettings, "output_dir"
    )
    timezone = TyperUtils.prompt_with_default(
        "Enter the timezone (e.g. UTC, Europe/Madrid)", timezone_default, WildIntelSettings, "timezone"
    )

    updates = {
        "GENERAL.host": host,
        "GENERAL.login": login,
        "GENERAL.password": password,
        "GENERAL.project_id": int(project_id),
        "GENERAL.data_dir": str(data_dir),
        "WILDINTEL.rp_name": rp_name,
        "WILDINTEL.coverage": coverage,
        "WILDINTEL.output_dir": str(output_dir),
        "WILDINTEL.timezone": timezone,
    }

    val = [
        {"Setting": key, "Value": "********" if "password" in key.lower() else str(value)}
        for key, value in updates.items()
    ]
    TyperUtils.show_table(val, "Settings to update")

    if typer.confirm("Do you want to apply these changes?"):
        settings_manager.update_settings(project_name, updates)
        TyperUtils.console.print(
            f"[bold green]Configuration for project '{project_name}' saved successfully "
            f"at {settings_manager.get_settings_path(project_name)}[/bold green]"
        )
    else:
        TyperUtils.console.print("[bold red]Aborted. No changes were made.[/bold red]")


def run_import_deployment_wizard(ctx: typer.Context, settings: Settings) -> None:
    _print_section("Import a new deployment")
    TyperUtils.console.print()
    TyperUtils.console.print("[blue]ℹ[/blue] This wizard will guide you through importing images from a local folder")
    TyperUtils.console.print("    into a new deployment directory, ready for processing with WildINTEL.")
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

    _print_section("Research project and location")
    TyperUtils.console.print()

    rp = trapper_client.research_projects.get_all()
    if not rp.results:
        TyperUtils.fatal("No research projects found in Trapper. Cannot continue.")
    TyperUtils.console.print()
    rp_selected = TyperUtils.select_box(
        rp.results, id_attr="pk", name_attr="name", label="Select a research project", multi_select=False,
    )

    revision_number = TyperUtils.prompt_with_default(
        "Enter the revision number", "1", GeneralSettings, "project_id"
    )
    revision_number = int(revision_number)

    locations = trapper_client.locations.get_all()
    if not locations.results:
        TyperUtils.fatal("No locations found in Trapper. Cannot continue.")
    TyperUtils.console.print()
    loc_selected = TyperUtils.select_box(
        locations.results, id_attr="pk", name_attr="location_id", label="Select a location", multi_select=False,
    )

    _print_section("Deployment folder")
    TyperUtils.console.print()

    base_dir = Path(settings.GENERAL.data_dir) / f"R{revision_number:04d}".upper()
    base_dir.mkdir(parents=True, exist_ok=True)

    revision_name = f"R{revision_number:04d}".upper()
    sub_dir_name = f"{revision_name}-{loc_selected.location_id}".upper()
    sub_dir = base_dir / sub_dir_name
    sub_dir.mkdir(parents=True, exist_ok=True)

    TyperUtils.console.print(f"[green]✓[/green] Deployment folder: [bold]{sub_dir}[/bold]")

    _print_section("Source images")
    TyperUtils.console.print()

    source_images_input = typer.prompt(_("Enter the path containing the images to import"))
    source_images_dir = Path(source_images_input).expanduser()

    if not source_images_dir.exists() or not source_images_dir.is_dir():
        TyperUtils.error(_("The provided images path does not exist or is not a directory."))
        return

    try:
        source_resolved = source_images_dir.resolve()
        destination_resolved = sub_dir.resolve()
    except OSError as e:
        TyperUtils.error(_("Could not resolve the provided path: {0}").format(str(e)))
        return

    if source_resolved == destination_resolved or destination_resolved.is_relative_to(source_resolved):
        TyperUtils.error(
            _("The source images directory cannot be the deployment directory or one of its parent directories.")
        )
        return

    timezone_name = getattr(settings.WILDINTEL, "timezone", "UTC")
    ignore_dst = getattr(settings.WILDINTEL, "ignore_dst", False)

    try:
        tz = ZoneInfo(str(timezone_name))
    except Exception:
        tz = ZoneInfo("UTC")

    TyperUtils.console.print()
    msg = (
        f"We are going to import images from [bold]{source_images_dir}[/bold] "
        f"into [bold]{sub_dir}[/bold] "
        f"under research project [bold]{rp_selected.name}[/bold] "
        f"using timezone [bold]{timezone_name}[/bold]. Are you sure?"
    )
    TyperUtils.console.print(msg)
    TyperUtils.console.print()

    if not typer.confirm("Proceed?"):
        typer.echo("Aborted.")
        return

    log_file = base_dir / f"{revision_name}_FileTimestampLog.csv"

    try:
        report = wildintel_ui.import_deployment(
            source_dir=source_images_dir,
            destination_dir=sub_dir,
            deployment_name=sub_dir_name,
            log_file=log_file,
            timezone=tz,
            ignore_dst=ignore_dst,
        )
    except Exception as e:
        TyperUtils.error(str(e))
        return

    csv_entries = report.successes.get(sub_dir_name, [])
    csv_entry = next((e for e in csv_entries if e.get("action") == "csv_log"), None)
    TyperUtils.display_report(report)

    if csv_entry:
        TyperUtils.info(
            _("Date range: {0} → {1}  |  files: {2}, folders: {3}").format(
                csv_entry.get("start_dt", "?"),
                csv_entry.get("end_dt", "?"),
                csv_entry.get("copied_files", "?"),
                csv_entry.get("copied_dirs", "?"),
            )
        )

    TyperUtils.console.print("[bold green]Deployment imported successfully.[/bold green]")


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

        if wizard == Wizard.config or wizard == Wizard.setup:
            run_setup_wizard(ctx, settings, settings_manager)
        elif wizard == Wizard.import_deployment:
            run_import_deployment_wizard(ctx, settings)
