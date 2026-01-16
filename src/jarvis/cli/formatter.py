"""Rich-based output formatter for pretty printing."""

import json
from typing import Any

from rich.console import Console
from rich.syntax import Syntax
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress
from rich.markup import escape


class OutputFormatter:
    """Format and display output with Rich library."""

    def __init__(self):
        """Initialize formatter with console."""
        self.console = Console()

    def print_header(self, title: str, subtitle: str = "") -> None:
        """Print a formatted header."""
        if subtitle:
            content = f"{title}\n[dim]{subtitle}[/dim]"
        else:
            content = title

        self.console.print(
            Panel(
                content,
                style="bold blue",
                expand=False,
                padding=(1, 2),
            )
        )

    def print_success(self, message: str) -> None:
        """Print success message."""
        self.console.print(f"[green]✓[/green] {message}")

    def print_error(self, message: str) -> None:
        """Print error message."""
        self.console.print(f"[red]✗[/red] {message}")

    def print_warning(self, message: str) -> None:
        """Print warning message."""
        self.console.print(f"[yellow]⚠[/yellow] {message}")

    def print_info(self, message: str) -> None:
        """Print info message."""
        self.console.print(f"[cyan]ℹ[/cyan] {message}")

    def print_code(self, code: str, language: str = "python", line_numbers: bool = True) -> None:
        """Print formatted code block."""
        syntax = Syntax(
            code,
            language,
            theme="monokai",
            line_numbers=line_numbers,
            word_wrap=True,
        )
        self.console.print(syntax)

    def print_json(self, data: Any, indent: int = 2) -> None:
        """Print formatted JSON."""
        json_str = json.dumps(data, indent=indent, ensure_ascii=False)
        syntax = Syntax(json_str, "json", theme="monokai", line_numbers=False)
        self.console.print(syntax)

    def print_table(
        self,
        data: list[dict[str, Any]],
        title: str = "",
        columns: list[str] | None = None,
    ) -> None:
        """Print data as formatted table."""
        if not data:
            self.print_warning("No data to display")
            return

        # Auto-detect columns if not provided
        if columns is None:
            columns = list(data[0].keys()) if data else []

        table = Table(title=title, show_header=True, header_style="bold cyan")

        for col in columns:
            table.add_column(col, style="dim")

        for row in data:
            values = [str(row.get(col, "")) for col in columns]
            table.add_row(*values)

        self.console.print(table)

    def print_list(self, items: list[str], title: str = "") -> None:
        """Print formatted list."""
        if title:
            self.console.print(f"[bold cyan]{title}[/bold cyan]")

        for item in items:
            self.console.print(f"  • {escape(str(item))}")

    def print_section(self, title: str, content: str = "") -> None:
        """Print a section with title."""
        self.console.print(f"\n[bold blue]{'=' * 50}[/bold blue]")
        self.console.print(f"[bold blue]{title}[/bold blue]")
        self.console.print(f"[bold blue]{'=' * 50}[/bold blue]")
        if content:
            self.console.print(content)

    def print_panel(self, content: str, title: str = "", style: str = "blue") -> None:
        """Print content in a panel."""
        self.console.print(
            Panel(
                content,
                title=title,
                style=style,
                expand=True,
                padding=(1, 2),
            )
        )

    def print_progress_bar(self, total: int, description: str = "Processing") -> Progress:
        """Create and return a progress bar."""
        progress = Progress()
        progress.add_task(description, total=total)
        return progress

    def clear_screen(self) -> None:
        """Clear the console screen."""
        self.console.clear()

    def print_rule(self, title: str = "") -> None:
        """Print a horizontal rule."""
        from rich.rule import Rule

        self.console.print(Rule(title))

    def print_tree(self, label: str, children: dict[str, list[str]]) -> None:
        """Print hierarchical tree structure."""
        from rich.tree import Tree

        tree = Tree(label, guide_style="bold bright_blue")

        for parent, items in children.items():
            parent_node = tree.add(f"[bold]{parent}[/bold]")
            for item in items:
                parent_node.add(item)

        self.console.print(tree)

    def input_prompt(self, prompt: str, default: str = "") -> str:
        """Get user input with formatted prompt."""
        if default:
            display = f"{prompt} [{dim}default: {default}{escape('[/dim')}]: "
        else:
            display = f"{prompt}: "

        return self.console.input(display) or default

    def confirm(self, message: str, default: bool = True) -> bool:
        """Get yes/no confirmation from user."""
        suffix = " [Y/n]" if default else " [y/N]"
        response = self.console.input(f"{message}{suffix}: ").lower().strip()

        if response:
            return response in ("y", "yes")
        return default

    def print_dict(self, data: dict[str, Any], title: str = "") -> None:
        """Print dictionary in key-value format."""
        if title:
            self.console.print(f"[bold cyan]{title}[/bold cyan]")

        for key, value in data.items():
            formatted_value = json.dumps(value) if not isinstance(value, str) else value
            self.console.print(f"  [bold]{key}:[/bold] {escape(str(formatted_value))}")
