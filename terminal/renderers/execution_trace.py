"""Rich renderer for Agent Adda execution traces."""
from __future__ import annotations

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from terminal.execution_trace import ExecutionTrace, TraceEvent


def _event_detail(event: TraceEvent, *, expanded: bool) -> str:
    parts: list[str] = []
    if event.row_count is not None:
        parts.append(f"rows: {event.row_count}")
    if event.before_count is not None or event.after_count is not None:
        parts.append(f"{event.before_count} -> {event.after_count}")
    if event.artifact_path:
        parts.append(event.artifact_path)
    if event.detail:
        parts.append(event.detail)
    if event.error:
        parts.append(f"error: {event.error}")
    if expanded and event.metadata:
        parts.append(", ".join(f"{k}={v}" for k, v in sorted(event.metadata.items())))
    return " | ".join(parts) if parts else "-"


def render_execution_trace(
    console: Console,
    trace: ExecutionTrace,
    *,
    expanded: bool = False,
) -> None:
    """Render an execution trace to a Rich console."""
    title = "Execution Trail"
    subtitle = trace.command or trace.workflow_kind

    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold cyan")
    table.add_column("Step", style="bold", min_width=18)
    table.add_column("Status", min_width=10)
    table.add_column("Details", min_width=50)

    visible_events = [
        event
        for event in trace.events
        if expanded or event.event_type not in {"workflow_started", "workflow_completed"}
    ]
    if not visible_events:
        visible_events = trace.events

    for event in visible_events:
        table.add_row(
            event.label,
            str(event.status or "-"),
            _event_detail(event, expanded=expanded),
        )

    summary = trace.summary_counts()
    footer = (
        f"workflow={trace.workflow_kind} | status={trace.status} | "
        f"tools ok={summary['tools_ok']} failed={summary['tools_failed']} | "
        f"verifications pass={summary['verification_pass']} fail={summary['verification_fail']}"
    )
    console.print(Panel(table, title=f"[bold cyan]{title}[/bold cyan]", subtitle=subtitle, border_style="cyan"))
    console.print(f"[dim]{footer}[/dim]")

