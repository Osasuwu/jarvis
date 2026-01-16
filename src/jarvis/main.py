"""Main entry point for Jarvis CLI application."""

import asyncio
import logging
import sys

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from jarvis.config import get_config
from jarvis.core.orchestrator import Orchestrator
from jarvis.llm import GroqProvider
from jarvis.memory import ConversationMemory
from jarvis.tools.builtin import EchoTool
from jarvis.tools.registry import ToolRegistry

app = typer.Typer(
    name="jarvis",
    help="Personal AI Agent with modular tool system",
    add_completion=False,
)

console = Console()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


def _create_orchestrator() -> Orchestrator:
    """Create and initialize the orchestrator."""
    try:
        config = get_config()

        # Initialize LLM Provider
        if not config.llm.groq_api_key:
            console.print(
                "[red]Error: GROQ_API_KEY not set.[/red]\n"
                "Please set it in .env file or environment variable."
            )
            raise typer.Exit(1)

        llm = GroqProvider(
            api_key=config.llm.groq_api_key,
            model=config.llm.model,
        )

        # Initialize Tool Registry
        registry = ToolRegistry()
        registry.register(EchoTool())

        # Initialize Memory
        memory = ConversationMemory()

        # Create Orchestrator
        orchestrator = Orchestrator(
            llm_provider=llm,
            tool_registry=registry,
            memory=memory,
        )

        return orchestrator

    except Exception as e:
        console.print(f"[red]Failed to initialize Jarvis: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def chat(query: str = typer.Argument(None, help="Query to send to Jarvis")) -> None:
    """Send a query to Jarvis or start interactive mode."""
    if not query:
        console.print("[yellow]Interactive mode not yet implemented.[/yellow]")
        console.print("Usage: jarvis chat \"your question here\"")
        return

    console.print(Panel(f"[bold]User:[/bold] {query}", style="blue"))

    # Create orchestrator
    orchestrator = _create_orchestrator()

    # Run query
    try:
        response = asyncio.run(orchestrator.run(query))
        console.print(Panel(Markdown(response), title="[bold green]Jarvis[/bold green]"))

        # Show stats
        stats = orchestrator.get_stats()
        console.print(
            f"\n[dim]Tools: {stats['tools_available']} | "
            f"Model: {stats['llm_model']} | "
            f"Memory: {stats['memory_size']} messages[/dim]"
        )

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def version() -> None:
    """Show Jarvis version."""
    from jarvis import __version__

    console.print(f"[bold]Jarvis AI Agent[/bold] v{__version__}")
    console.print("\n[green]✅ Phase 1:[/green] Core Foundation")
    console.print("[green]✅ Phase 2:[/green] Orchestrator MVP")


@app.command()
def info() -> None:
    """Show current configuration and system info."""
    config = get_config()

    console.print("\n[bold]Jarvis Configuration[/bold]\n")
    console.print(f"LLM Provider: [cyan]{config.llm.provider}[/cyan]")
    console.print(f"Model: [cyan]{config.llm.model}[/cyan]")
    console.print(f"Temperature: [cyan]{config.llm.temperature}[/cyan]")
    console.print(f"Max Iterations: [cyan]{config.agent.max_iterations}[/cyan]")
    console.print(f"Memory Max: [cyan]{config.memory.max_conversation_length}[/cyan]")


if __name__ == "__main__":
    app()
