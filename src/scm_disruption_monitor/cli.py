from __future__ import annotations

from pathlib import Path
from typing import Annotated

import httpx
import typer
from rich.console import Console
from rich.table import Table

from scm_disruption_monitor.laya_client import laya_base_url
from scm_disruption_monitor.monitor import assess_all, load_events

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()

DEFAULT_SAMPLE = Path(__file__).resolve().parents[2] / "data" / "sample_disruptions.json"


@app.command("health")
def health() -> None:
    """Check reachability of the Laya API models endpoint."""
    url = f"{laya_base_url()}/v1/models"
    with httpx.Client(timeout=15.0) as client:
        response = client.get(url)
        response.raise_for_status()
    console.print(f"[green]OK[/green] {url}")


@app.command("analyze")
def analyze(
    sample: Annotated[
        bool,
        typer.Option("--sample/--no-sample", help="Use bundled sample disruption events."),
    ] = True,
    input_path: Annotated[
        Path,
        typer.Option("--input", "-i", help="JSON file with disruption events."),
    ] = DEFAULT_SAMPLE,
    live: Annotated[
        bool,
        typer.Option("--live", help="Call Laya /v1/systemone (requires LAYA_API_KEY)."),
    ] = False,
) -> None:
    """Assess disruption events and print severity recommendations."""
    path = DEFAULT_SAMPLE if sample else input_path
    events = load_events(path)
    results = assess_all(events, live=live)

    table = Table(title="SCM disruption assessments")
    table.add_column("Event")
    table.add_column("Severity")
    table.add_column("Escalate")
    table.add_column("Source")
    table.add_column("Rationale")
    for assessment in results:
        table.add_row(
            assessment.event_id,
            assessment.severity,
            "yes" if assessment.escalate else "no",
            assessment.source,
            assessment.rationale,
        )
    console.print(table)


if __name__ == "__main__":
    app()
