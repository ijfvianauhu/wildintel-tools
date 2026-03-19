import json
from typing import Optional, Any,  Tuple

from wildintel_tools.zooniverse.Schemas import SubjectSetResults
from wildintel_tools.ui.typer.TyperUtils import TyperUtils
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.tree import Tree
from rich.table import Table
from rich.console import Console
from rich.panel import Panel
from typing import List
from panoptes_client import Subject, SubjectSet, Classification
import logging
from wildintel_tools.ui.typer.i18n import _


class ZooUtils:
    console = Console()
    logger = logging.getLogger(__name__)

    #
    # Workflows
    #

    @staticmethod
    def show_workflows(workflows, title: str = "Workflows"):
        """
        Display a list of Zooniverse Workflows in a table, showing ID, name, version, and number of subject sets.

        Parameters
        ----------
        workflows : List[Workflow]
            List of Workflow objects.
        title : str
            Title for the table.
        """
        if not workflows:
            TyperUtils.warning(f"[yellow]No workflows to display in '{title}'[/yellow]")
            return

        table = Table(title=title, show_lines=True)
        table.add_column("ID", style="cyan", justify="right")
        table.add_column("Name", style="green")
        table.add_column("Version", style="magenta")
        table.add_column("Status", style="magenta")
        table.add_column("Subject Sets", style="yellow", justify="right")
        table.add_column("Subjects", style="yellow", justify="right")
        table.add_column("Last Export", style="yellow", justify="right")

        for wf in workflows:
            # Intentamos contar los subject sets (puede ser lazy-loaded)
            try:
                subject_sets_count = len(list(wf.links.subject_sets))
                classifications = list(Classification.where(workflow_id=wf.id))
                classifications_count= len(classifications)

            except Exception as e:
                subject_sets_count = 0

            table.add_row(
                str(wf.id),
                wf.display_name or "—",
                str(wf.version) if wf.version else "—",
                str(wf.active),
                str(subject_sets_count),
                str(wf.raw.get("subjects_count", "-")),
                str("not implemented"),
            )

        TyperUtils.console.print(table)
        TyperUtils.info(f"Total workflows: {len(workflows)}")

    @staticmethod
    def show_workflow(workflow,
                      show_raw: bool = False,
        max_choices_preview: int = 10,
        title: Optional[str] = None) -> None:

        """
            Muestra por pantalla un workflow de Zooniverse usando rich.

            Args:
                workflow: dict con la definición completa del workflow (JSON).
                show_raw: si True, muestra al final el JSON formateado.
                max_choices_preview: número máximo de opciones a mostrar por tarea (si hay muchas).
                title: título opcional para la cabecera.
            """

        if not isinstance(workflow, dict):
            try:
                workflow = workflow.raw  # atributo que contiene el JSON completo
            except AttributeError:
                raise TypeError("El objeto recibido no es un dict ni un Workflow válido con atributo .raw")

        root_title = title or f"Workflow: {workflow.get('display_name', workflow.get('id', 'unknown'))}"
        tree = Tree(f":clipboard: [bold blue]{root_title}[/]")

        # Metadatos principales
        meta_tbl = Table.grid(padding=(0, 1))
        meta_tbl.add_column(justify="right", style="bold")
        meta_tbl.add_column()
        meta_tbl.add_row("id", str(workflow.get("id", "")))
        meta_tbl.add_row("display_name", str(workflow.get("display_name", "")))
        meta_tbl.add_row("version", str(workflow.get("version", "")))
        meta_tbl.add_row("active", str(workflow.get("active", "")))
        if workflow.get("tasks"):
            meta_tbl.add_row("n_tasks", str(len(workflow["tasks"])))
        if workflow.get("retirement"):
            meta_tbl.add_row("retirement", "yes")

        meta_tbl.add_row("n_classifications", str(len(list(Classification.where(workflow_id=workflow)))))
        meta_tbl.add_row("n_subject_sets", str(len(list(workflow["links"]["subject_sets"]))))

        tree.add(Panel(meta_tbl, title="Metadatos", expand=False))

        # Descripción (si existe)
        description = workflow.get("description") or workflow.get("display_name")
        if description:
            tree.add(Panel(Markdown(str(description)), title="Descripción", expand=False))

        # Tareas (tasks)
        tasks = workflow.get("tasks", {})
        if tasks:
            tasks_branch = tree.add(f":gear: [bold]Tareas ({len(tasks)})[/]")
            # Ordenar por key para reproducibilidad
            for task_key in sorted(tasks.keys()):
                task = tasks[task_key]
                task_label = f"[bold]{task_key}[/] — {task.get('type', 'unknown')}: {task.get('question', '')}"
                tnode = tasks_branch.add(task_label)

                # Info table por tarea
                t_tbl = Table.grid()
                t_tbl.add_column(style="bold", width=16)
                t_tbl.add_column()
                t_tbl.add_row("type", str(task.get("type", "")))
                t_tbl.add_row("question", str(task.get("question", "")[:200]))
                if "required" in task:
                    t_tbl.add_row("required", str(task.get("required")))
                if "help" in task:
                    t_tbl.add_row("help", str(task.get("help", "")[:200]))
                tnode.add(Panel(t_tbl, expand=False))

                # Tipos con opciones (multiple choice / dropdown / radio / combo)
                if "answers" in task and isinstance(task["answers"], list):
                    a_table = Table(show_header=True, header_style="bold magenta")
                    a_table.add_column("idx", width=4, justify="right")
                    a_table.add_column("label")
                    a_table.add_column("value")
                    for i, ans in enumerate(task["answers"][:max_choices_preview], start=1):
                        label = ans.get("label") if isinstance(ans, dict) else str(ans)
                        value = ans.get("value") if isinstance(ans, dict) else ""
                        a_table.add_row(str(i), str(label), str(value))
                    if len(task["answers"]) > max_choices_preview:
                        a_table.add_row("…", f"(+{len(task['answers']) - max_choices_preview} more)", "")
                    tnode.add(Panel(a_table, title="Opciones", expand=False))

                # Choice maps for complex tasks (e.g., combo, drawing)
                if task.get("type") in ("dropdown", "multiple", "single", "combo", "drawing"):
                    # show any extra keys
                    extras = {k: v for k, v in task.items() if
                              k not in ("type", "question", "answers", "help", "required")}
                    if extras:
                        ex_json = json.dumps(extras, indent=2, ensure_ascii=False)
                        tnode.add(Panel(Syntax(ex_json, "json", theme="monokai", word_wrap=True), title="Extras",
                                        expand=False))
        # Retirement rules
        retirement = workflow.get("retirement")
        if retirement:
            ret_panel = Panel(Syntax(json.dumps(retirement, indent=2, ensure_ascii=False), "json"),
                              title="Retirement rules")
            tree.add(ret_panel)

        # Tutorial / grouping / version info in subject sets
        if workflow.get("subject_sets"):
            ss_branch = tree.add(f":framed_picture: Subject sets ({len(workflow['subject_sets'])})")
            for s in workflow["subject_sets"]:
                label = s.get("display_name", s.get("id", "unknown"))
                ss_branch.add(f"[bold]{label}[/] — id: {s.get('id', '')}")

        # Mostrar árbol
        TyperUtils.console.print(tree)

        # Raw JSON (opcional)
        if show_raw:
            raw = json.dumps(workflow, indent=2, ensure_ascii=False)
            TyperUtils.console.rule("[bold]Raw JSON")
            TyperUtils.console.print(Syntax(raw, "json", word_wrap=True))

    #
    # Subject Sets
    #

    @staticmethod
    def show_subject_sets(subject_sets: list[SubjectSet]):
        """Muestra una tabla con los SubjectSets de Zooniverse."""
        table = Table(title="Zooniverse Subject Sets", show_lines=True)

        # Define las columnshow_cas
        table.add_column("ID", justify="right", style="cyan", no_wrap=True)
        table.add_column("Name", style="green")
        table.add_column("Created", style="yellow")
        table.add_column("Updated", style="magenta")
        table.add_column("Subjects Count", justify="right", style="blue")
        table.add_column("Workflows", justify="right", style="blue")

        for ss in subject_sets:
            # Algunos SubjectSets pueden no tener todos los campos
            created = getattr(ss, "created_at", "—")
            updated = getattr(ss, "updated_at", "—")
            name = getattr(ss, "display_name", "—")
            subject_count = getattr(ss, "set_member_subjects_count", "—")
            workflows=(ss.raw["links"]["workflows"])

            table.add_row(
                str(ss.id),
                name,
                str(created),
                str(updated),
                str(subject_count),
                ",".join(workflows)
            )

        TyperUtils.console.print(table)
        TyperUtils.info(f"Total: {len(subject_sets)}")

    @staticmethod
    def show_subject_set(subject_set: SubjectSet, title: str = "Subject Set Details", raw: bool = False):
        """
        Display a single Zooniverse SubjectSet as a detailed "card".

        Parameters
        ----------
        subject_set : SubjectSet
            The SubjectSet object to display.
        title : str
            Title for the panel.
        raw : bool
            When True, also print the SubjectSet raw JSON formatted (after the table).
        """

        if raw:
            try:
                json_str = json.dumps(subject_set.raw, indent=2, ensure_ascii=False)
                TyperUtils.console.rule("[bold]Raw JSON")
                TyperUtils.console.print(Syntax(json_str, "json", word_wrap=True))
                return
            except Exception as exc:
                TyperUtils.warning(f"Could not render raw subject set JSON: {exc}")

        try:
            subjects_count = getattr(subject_set, "set_member_subjects_count", "—")
        except Exception:
            subjects_count = "Unknown"

        try:
            workflows_count = len(subject_set.raw.get("links")["workflows"])
        except Exception:
            workflows_count = "Unknown"

        table = Table(show_header=False, show_lines=True)
        table.add_row(_("ID"), str(subject_set.id))
        table.add_row(_("Name"), subject_set.display_name or "—")
        table.add_row(_("Created At"), str(subject_set.created_at))
        table.add_row(_("Updated At"), str(subject_set.updated_at))
        table.add_row(_("Number of Subjects"), str(subjects_count))
        table.add_row(_("Number of Workflows"), str(workflows_count))
        table.add_row(_("Description"), subject_set.raw.get("display_name") or "—")

        panel = Panel(table, title=title, expand=False, border_style="green")
        TyperUtils.console.print(panel)


    @staticmethod
    def show_subjects(subjects: List[Subject], title: str = "Subjects"):
        """
        Display a list of Zooniverse Subjects in a table, and show available metadata and location keys.

        Parameters
        ----------
        subjects : List[Subject]
            List of Subject objects.
        title : str
            Title for the table.
        """
        if not subjects:
            TyperUtils.warning(f"[yellow]No subjects to display in '{title}'[/yellow]")
            return

        table = Table(title=title, show_lines=True)
        table.add_column("ID", style="cyan", justify="right")
        table.add_column("Metadata", style="green")
        table.add_column("Locations", style="magenta")
        table.add_column("Classifications", style="magenta")

        all_metadata_keys = set()
        all_location_keys = set()

        for subj in subjects:
            # Metadata
            metadata = getattr(subj, "metadata", {})
            metadata_str = ", ".join(f"{k}: {v}" for k, v in metadata.items())
            all_metadata_keys.update(metadata.keys())

            # Locations
            locations = getattr(subj, "locations", [])
            locations_str = ", ".join(
                f"{k}: {v}" for loc in locations if isinstance(loc, dict) for k, v in loc.items()
            )
            for loc in locations:
                if isinstance(loc, dict):
                    all_location_keys.update(loc.keys())

            # Clas
            cls = list(Classification.where(subject_ids=[subj.id]))
            # Añadir fila de cada subject
            table.add_row(str(subj.id), metadata_str, locations_str)

        # Añadir fila final con atributos disponibles
        #table.add_row(
        #    "[bold yellow]Available Keys[/bold yellow]",
        #    ", ".join(sorted(all_metadata_keys)) if all_metadata_keys else "—",
        #    ", ".join(sorted(all_location_keys)) if all_location_keys else "—",
        #)

        TyperUtils.console.print(table)
        TyperUtils.info(f"Total: {len(subjects)}")

    @staticmethod
    def show_subject(subject: Subject, title: str = "Subject Details", raw: bool = False):
        """
        Display a single Zooniverse Subject as a detailed "card".

        Parameters
        ----------
        subject : Subject
            The Subject object to display.
        title : str
            Title for the panel.
        raw : bool
            When True, print the Subject raw JSON formatted.
        """
        console = Console()

        if raw:
            try:
                json_str = json.dumps(subject.raw, indent=2, ensure_ascii=False)
                TyperUtils.console.rule("[bold]Raw JSON")
                TyperUtils.console.print(Syntax(json_str, "json", word_wrap=True))
                return
            except Exception as exc:
                TyperUtils.warning(f"Could not render raw subject JSON: {exc}")
        try:
            subject_sets_count = len(subject.links.subject_sets)
        except Exception as e:
            subject_sets_count = "Unknown"

        # Mostrar metadata de forma resumida
        metadata_str = ""
        if subject.metadata:
            for key, value in subject.metadata.items():
                metadata_str += f"{key}: {value}\n"
            metadata_str = metadata_str.strip()
        else:
            metadata_str = "—"

        # Ubicaciones (locations) del Subject
        locations_str = ""
        if subject.locations:
            for loc in subject.locations:
                # loc puede ser un dict con tipo y url
                if isinstance(loc, dict):
                    locations_str += f"{loc.get('image/png') or loc.get('image/jpeg') or str(loc)}\n"
                else:
                    locations_str += f"{str(loc)}\n"
            locations_str = locations_str.strip()
        else:
            locations_str = "—"

        table = Table(show_header=False, show_lines=True)
        table.add_row("ID", str(subject.id))
        table.add_row("Created At", str(subject.created_at))
        table.add_row("Updated At", str(subject.updated_at))
        table.add_row("Number of SubjectSets", str(subject_sets_count))
        table.add_row("Locations", locations_str)
        table.add_row("Metadata", metadata_str)

        panel = Panel(table, title=title, expand=False, border_style="blue")
        TyperUtils.console.print(panel)


    @staticmethod
    def show_annotations(annotations: SubjectSetResults, title: str = "Annotations"):
        console = Console()

        table = Table(title="SubjectSet Results", show_lines=True)

        table.add_column("Workflow", style="cyan", no_wrap=True)
        table.add_column("Subject", style="magenta")
        table.add_column("Subject Name", style="magenta")

        table.add_column("Classification ID", style="green")
        table.add_column("User", style="yellow")
        table.add_column("Annotation", style="white")  # <- un único campo
        table.add_column("Retired", style="red")

        # Recorremos todos los workflows
        for workflow_id, workflow_data in annotations.workflows.items():
            # workflow_data.data → Dict[str, List[ClassificationInfo]]
            for subject_id, classifs in workflow_data.data.items():
                # Cada clasificación = una fila
                for c in classifs:
                    # ------------------------------
                    #   Parseo compacto de annotations
                    # ------------------------------
                    # Esperamos: c.annotations = [{'task': 'T3', 'value': [{'choice': ..., 'answers': {'HOWMANY': ...}}]}]
                    ann_str = "—"

                    try:
                        ann = c.annotations[0]["value"][0]
                        choice = ann.get("choice", "unknown")
                        count = ann.get("answers", {}).get("HOWMANY", None)

                        if count:
                            ann_str = f"{choice} ({count})"
                        else:
                            ann_str = choice
                    except Exception:
                        ann_str = "invalid"

                    table.add_row(
                        workflow_id,
                        subject_id,
                        c.subject_name,
                        c.classification_id or "",
                        c.user_name or "",
                        ann_str,
                        "✓" if c.retired else "",
                    )

        console.print(table)

    @staticmethod
    def show_annotations_table(annotations: List[Tuple[int, str]], title: str = "Annotations"):
        """
        Display a list of Zooniverse annotations in a table.

        Parameters
        ----------
        annotations : List[Tuple[int, str]]
            List of tuples (subject_set_id, export_url) returned by get_all().
        title : str
            Title for the table.
        """
        if not annotations:
            TyperUtils.warning(f"[yellow]No annotations to display in '{title}'[/yellow]")
            return

        table = Table(title=title, show_lines=True)
        table.add_column("SubjectSet ID", style="cyan", justify="right")
        table.add_column("Export Available", style="green", justify="center")
        table.add_column("Export URL", style="magenta")

        for subject_set_id, export_url in annotations:
            available = "✅" if export_url else "❌"
            url_display = str(export_url) if export_url else "—"
            # Si la URL es muy larga, se puede truncar
            if len(url_display) > 60:
                url_display = url_display[:57] + "..."
            table.add_row(str(subject_set_id), available, url_display)

        TyperUtils.console.print(table)
        TyperUtils.info(f"Total subject sets: {len(annotations)}")

    @staticmethod
    def show_objects_table(objects: List[Any], title: str = "Objects Table"):
        """
        Displays a table with all public attributes of the given objects.

        Parameters
        ----------
        objects : List[Any]
            List of objects to display in a table. All public attributes will be used as columns.
        title : str, optional
            Title of the table.
        """
        if not objects:
            TyperUtils.warning(f"[yellow]No objects to display in table '{title}'")
            return

        # Obtener atributos públicos del primer objeto
        first_obj = objects[0]
        attrs = [attr for attr in dir(first_obj) if not attr.startswith("_") and not callable(getattr(first_obj, attr))]

        table = Table(title=title, show_lines=True)

        # Crear columnas dinámicamente
        for attr in attrs:
            table.add_column(attr, style="green")

        # Añadir filas
        for obj in objects:
            row = [str(getattr(obj, attr, "—")) for attr in attrs]
            table.add_row(*row)

        TyperUtils.console.print(table)
