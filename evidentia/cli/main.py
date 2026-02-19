"""Evidentia CLI — command-line entry point."""

from __future__ import annotations

import asyncio

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from evidentia import __version__

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="evidentia")
def cli() -> None:
    """Evidentia — A verifiable intelligence layer for research workflows."""


@cli.command()
@click.argument("query")
@click.option("--tools", "-t", default=None, help="Comma-separated list of tools to use.")
@click.option("--max-steps", default=20, help="Maximum plan steps.")
@click.option("--output", "-o", default=None, help="Output file path (JSON).")
def query(query: str, tools: str | None, max_steps: int, output: str | None) -> None:
    """Run a research query through the Evidentia agent."""
    console.print(Panel(f"[bold]Query:[/bold] {query}", title="Evidentia", border_style="blue"))

    async def _run() -> None:
        from evidentia.agent.factory import build_agent
        from evidentia.core.logging import setup_logging

        setup_logging(log_level="INFO")

        try:
            agent = build_agent()
        except Exception as exc:
            console.print(f"[red]Failed to initialize agent: {exc}[/red]")
            console.print("[yellow]Set OPENAI_API_KEY or ANTHROPIC_API_KEY in your .env[/yellow]")
            return

        console.print("[dim]Agent is thinking...[/dim]\n")
        result = await agent.run(query)

        if result.success:
            console.print(Panel("[green]Completed[/green]", border_style="green"))
        else:
            console.print(Panel("[red]Failed[/red]", border_style="red"))

        if result.summary:
            console.print(f"\n[bold]Summary:[/bold] {result.summary}")

        for i, claim in enumerate(result.claims, 1):
            tree = Tree(f"[bold]Claim {i}:[/bold] {claim.statement}")
            tree.add(f"Confidence: {claim.confidence.value}")
            for c in claim.citations:
                tree.add(f"Source: {c.title} — {c.url or c.doi or ''}")
            console.print(tree)

        console.print(f"\n[dim]Tool calls: {result.total_tool_calls} | Iterations: {result.total_iterations}[/dim]")

        if output:
            import json as json_mod

            with open(output, "w") as f:
                json_mod.dump(result.to_dict(), f, indent=2, default=str)
            console.print(f"[dim]Saved to {output}[/dim]")

    asyncio.run(_run())


@cli.command()
@click.argument("run_id")
def trace(run_id: str) -> None:
    """View the execution trace of a past run."""
    console.print(Panel(f"Run trace: {run_id}", title="Trace Viewer", border_style="green"))
    # TODO: Fetch from run store
    console.print("[yellow]Run store not yet connected.[/yellow]")


@cli.command("export")
@click.argument("run_id")
@click.option("--format", "-f", "fmt", type=click.Choice(["json", "bibtex", "markdown", "latex"]), default="json")
def export_run(run_id: str, fmt: str) -> None:
    """Export a run's results in the specified format."""
    console.print(f"Exporting run {run_id} as {fmt}...")
    # TODO: Implement exporters
    console.print("[yellow]Export not yet implemented.[/yellow]")


@cli.command()
def tools() -> None:
    """List all available tools."""
    table = Table(title="Available Tools")
    table.add_column("Name", style="cyan")
    table.add_column("Category", style="green")
    table.add_column("Description")
    table.add_column("Auth Required", justify="center")

    # Default tool listing
    default_tools = [
        ("web_search", "public_api", "Search the web for relevant pages", "Yes"),
        ("arxiv_search", "public_api", "Search arXiv for academic papers", "No"),
        ("semantic_scholar", "public_api", "Search Semantic Scholar for papers", "No"),
        ("doi_lookup", "public_api", "Resolve DOI to citation metadata", "No"),
        ("python_sandbox", "local_execution", "Execute Python code in sandbox", "No"),
    ]

    for name, cat, desc, auth in default_tools:
        table.add_row(name, cat, desc, auth)

    console.print(table)


@cli.command()
@click.option("--host", default="0.0.0.0", help="Bind host.")
@click.option("--port", default=8000, help="Bind port.")
def serve(host: str, port: int) -> None:
    """Start the Evidentia API server."""
    console.print(
        Panel(
            f"Starting Evidentia server on {host}:{port}",
            title="Server",
            border_style="blue",
        )
    )
    import uvicorn

    uvicorn.run("evidentia.api.server:app", host=host, port=port, reload=True)


@cli.group()
def db() -> None:
    """Database management commands."""


@db.command()
def migrate() -> None:
    """Run database migrations."""
    console.print("[yellow]Migrations not yet configured. Set up Alembic first.[/yellow]")


if __name__ == "__main__":
    cli()
