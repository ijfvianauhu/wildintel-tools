from rich.console import Console
from rich.panel import Panel
from rich.json import JSON
from rich.tree import Tree

import logging

class EpicollectUtils:
    console = Console()
    logger = logging.getLogger(__name__)


    @staticmethod
    def show_public_project(data, title="[bold cyan]project[/]"):
        panel = Panel(JSON.from_data(data), title=title, border_style="cyan")
        console = Console()
        console.print(panel)

    @staticmethod
    def show_private_project(project_info, title="[bold cyan]project[/]"):
        from rich.console import Console
        from rich.table import Table

        console = Console()

        data = project_info.get("data")

        if isinstance(data, dict):
            project = data.get("project")
        elif isinstance(data, list) and len(data) > 0:
            project = data[0].get("project")
        else:
            console.print("[red]No se pudo encontrar project en 'data'[/]")
            return

        if not project:
            console.print("[red]No se pudo extraer el diccionario 'project'[/]")
            return

        # --- MOSTRAR INFORMACIÓN GENERAL ---
        console.print(f"[bold cyan]Project:[/] {project['name']} ({project['ref']})")
        console.print(f"[bold]Slug:[/] {project['slug']}")
        console.print(f"[bold]Access:[/] {project.get('access', 'unknown')}")
        console.print(f"[bold]Status:[/] {project.get('status', 'unknown')}")
        console.print(f"[bold]Description:[/] {project.get('description', '')}")
        console.print(f"[bold]Homepage:[/] {project.get('homepage', '')}")
        console.print(f"[bold]Created at:[/] {project.get('created_at', '')}")

        # --- MOSTRAR FORMS ---
        forms = project.get("forms", [])
        for form in forms:
            console.print(f"\n[bold magenta]Form:[/] {form['name']} ({form['ref']})")

            table = Table(show_header=True, header_style="bold blue")
            table.add_column("Input Ref", style="dim", width=36)
            table.add_column("Question")
            table.add_column("Type")
            table.add_column("Default")
            table.add_column("Possible Answers")

            for input_item in form.get("inputs", []):
                possible_answers = input_item.get("possible_answers", [])

                if isinstance(possible_answers, list):
                    answers = ", ".join(a.get("answer", "") for a in possible_answers)
                elif isinstance(possible_answers, dict):
                    answers = ", ".join(v.get("map_to", "") for v in possible_answers.values())
                else:
                    answers = ""

                table.add_row(
                    input_item.get("ref", ""),
                    input_item.get("question", ""),
                    input_item.get("type", ""),
                    str(input_item.get("default", "")),
                    answers,
                )

            console.print(table)


    def print_nested_entries(data, title="Estructura"):
        """
        Muestra un diccionario anidado de sitios → sesiones → fechas → entradas
        usando Rich en formato árbol.
        """
        console = Console()

        root = Tree(f"[bold cyan]{title}[/]")

        def add_to_tree(tree, obj):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    branch = tree.add(f"[bold yellow]{key}[/]")
                    add_to_tree(branch, value)
            elif isinstance(obj, list):
                list_branch = tree.add(f"[magenta]Lista ({len(obj)} elementos)[/]")
                for i, item in enumerate(obj):
                    item_branch = list_branch.add(f"[magenta]Ítem {i}[/]")
                    add_to_tree(item_branch, item)
            else:
                tree.add(f"[green]{obj}[/]")

        add_to_tree(root, data)
        console.print(root)
