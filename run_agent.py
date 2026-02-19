"""Run the Evidentia research agent.

Usage:
    python run_agent.py "What are the latest advances in protein folding?"
    python run_agent.py "Compare transformer and LSTM architectures for NLP"

Requires:
    Set OPENAI_API_KEY or ANTHROPIC_API_KEY in .env or environment.
    Set LLM_PROVIDER to "openai" or "anthropic".
"""

from __future__ import annotations

import asyncio
import json
import sys

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

console = Console()


async def main(query: str) -> None:
    from evidentia.agent.factory import build_agent
    from evidentia.core.logging import setup_logging

    setup_logging(log_level="INFO")

    console.print(Panel(f"[bold]{query}[/bold]", title="Research Query", border_style="blue"))
    console.print()

    # Build the agent
    try:
        agent = build_agent()
    except Exception as exc:
        console.print(f"[red]Failed to initialize agent: {exc}[/red]")
        console.print("\n[yellow]Make sure you have set your API key:[/yellow]")
        console.print("  export OPENAI_API_KEY=sk-...")
        console.print("  export LLM_PROVIDER=openai")
        console.print("\n  OR\n")
        console.print("  export ANTHROPIC_API_KEY=sk-ant-...")
        console.print("  export LLM_PROVIDER=anthropic")
        return

    # Run the agent
    console.print("[dim]Agent is thinking...[/dim]\n")
    result = await agent.run(query)

    # ── Display results ──────────────────────────────────────────
    if result.success:
        console.print(Panel("[green]Agent completed successfully[/green]", border_style="green"))
    else:
        console.print(Panel("[red]Agent failed[/red]", border_style="red"))

    # Summary
    if result.summary:
        console.print("\n[bold]Summary[/bold]")
        console.print(Markdown(result.summary))

    # Claims
    if result.claims:
        console.print(f"\n[bold]Claims ({len(result.claims)})[/bold]\n")
        for i, claim in enumerate(result.claims, 1):
            confidence_color = {
                "high": "green",
                "medium": "yellow",
                "low": "red",
                "conflicting": "magenta",
            }.get(claim.confidence.value, "white")

            tree = Tree(f"[bold]Claim {i}:[/bold] {claim.statement}")
            tree.add(f"[{confidence_color}]Confidence: {claim.confidence.value}[/{confidence_color}]")

            if claim.citations:
                citations_branch = tree.add("[bold]Citations[/bold]")
                for c in claim.citations:
                    cite_text = c.title
                    if c.authors:
                        cite_text += f" — {', '.join(c.authors[:3])}"
                    if c.url:
                        cite_text += f"\n  {c.url}"
                    if c.doi:
                        cite_text += f"\n  DOI: {c.doi}"
                    citations_branch.add(cite_text)

            if claim.evidence_spans:
                evidence_branch = tree.add("[bold]Evidence[/bold]")
                for e in claim.evidence_spans:
                    evidence_branch.add(f"[dim]{e.text[:200]}[/dim]")

            if claim.conflicting_evidence:
                conflict_branch = tree.add("[bold magenta]Conflicting Evidence[/bold magenta]")
                for e in claim.conflicting_evidence:
                    conflict_branch.add(f"[magenta]{e.text[:200]}[/magenta]")

            console.print(tree)
            console.print()

    # Stats
    stats = Table(title="Run Statistics", show_header=False)
    stats.add_column("Metric", style="bold")
    stats.add_column("Value")
    stats.add_row("Tool Calls", str(result.total_tool_calls))
    stats.add_row("Iterations", str(result.total_iterations))
    stats.add_row("Elapsed", f"{result.elapsed_seconds:.1f}s")
    stats.add_row("Claims", str(len(result.claims)))
    ev = result.evidence_summary
    stats.add_row("Evidence Fragments", str(ev.get("total_evidence_fragments", 0)))
    stats.add_row("Coverage", f"{ev.get('coverage', 0):.0%}")
    console.print(stats)

    # Export full result as JSON
    import uuid
    run_id = uuid.uuid4().hex[:8]
    with open(f"run_{run_id}.json", "w") as f:
        json.dump(result.to_dict(), f, indent=2, default=str)
    console.print(f"\n[dim]Full trace saved to run_{run_id}.json[/dim]")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        console.print("[yellow]Usage: python run_agent.py \"<your research query>\"[/yellow]")
        console.print("\nExamples:")
        console.print('  python run_agent.py "What are the latest advances in protein folding?"')
        console.print('  python run_agent.py "Compare BERT and GPT architectures"')
        console.print('  python run_agent.py "What evidence exists for dark matter?"')
        sys.exit(1)

    query = " ".join(sys.argv[1:])
    asyncio.run(main(query))
