"""Main entry point for Jarvis CLI application."""

import typer

app = typer.Typer(
    name="jarvis",
    help="Personal AI Agent with modular tool system",
    add_completion=False,
)


@app.command()
def chat(query: str = typer.Argument(None, help="Query to send to Jarvis")) -> None:
    """Start an interactive chat session with Jarvis or send a single query."""
    # TODO: Phase 2 - Implement orchestrator integration
    typer.echo("🚧 Jarvis is under construction!")
    typer.echo("Phase 0 (Setup) complete. Core functionality coming in Phase 1-2.")
    if query:
        typer.echo(f"\nYou asked: {query}")
        typer.echo("✨ This will be answered once the orchestrator is ready!")


@app.command()
def version() -> None:
    """Show Jarvis version."""
    from jarvis import __version__

    typer.echo(f"Jarvis AI Agent v{__version__}")


@app.command()
def config() -> None:
    """Show current configuration."""
    # TODO: Phase 1 - Load and display configuration
    typer.echo("📋 Configuration management coming in Phase 1")


if __name__ == "__main__":
    app()
