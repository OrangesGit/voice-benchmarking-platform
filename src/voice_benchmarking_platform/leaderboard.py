from __future__ import annotations

import json
from typing import Literal

from rich import box
from rich.console import Console
from rich.table import Table

from voice_benchmarking_platform.models import BenchmarkResult, ScoredResult

SortKey = Literal["composite", "wer", "latency", "cost"]


def _sort_key(s: ScoredResult, by: SortKey) -> float:
    match by:
        case "wer":
            return s.wer if s.wer is not None else float("inf")
        case "latency":
            r = s.result
            return r.ttft_seconds if r.ttft_seconds is not None else r.total_seconds
        case "cost":
            return s.result.cost_usd
        case _:
            return s.composite_score


def render_leaderboard(
    results: list[ScoredResult],
    sort_by: SortKey = "composite",
    console: Console | None = None,
) -> None:
    c = console or Console()
    sorted_results = sorted(results, key=lambda s: _sort_key(s, sort_by))
    for i, s in enumerate(sorted_results):
        s.rank = i + 1

    table = Table(
        title="[bold]STT Provider Benchmark Leaderboard[/bold]",
        box=box.ROUNDED,
        show_lines=True,
        highlight=True,
    )
    table.add_column("Rank", style="bold yellow", justify="center", width=6)
    table.add_column("Provider", style="bold cyan", justify="left", width=18)
    table.add_column("WER", style="green", justify="right", width=8)
    table.add_column("CER", style="green", justify="right", width=8)
    table.add_column("TTFT (s)", style="blue", justify="right", width=10)
    table.add_column("Total (s)", style="blue", justify="right", width=10)
    table.add_column("Confidence", style="magenta", justify="right", width=11)
    table.add_column("Cost (USD)", style="magenta", justify="right", width=12)
    table.add_column("Score", style="bold white", justify="right", width=8)
    table.add_column("Transcript", style="dim", justify="left", min_width=20, max_width=50)

    for s in sorted_results:
        r = s.result
        wer_str = f"{s.wer:.3f}" if s.wer is not None else "N/A"
        cer_str = f"{s.cer:.3f}" if s.cer is not None else "N/A"
        ttft_str = f"{r.ttft_seconds:.3f}" if r.ttft_seconds is not None else "N/A"
        conf_str = f"{r.confidence:.3f}" if r.confidence is not None else "N/A"
        transcript_preview = r.transcript[:80] + ("…" if len(r.transcript) > 80 else "")

        rank_emoji = {1: "🥇", 2: "🥈", 3: "🥉"}.get(s.rank or 0, str(s.rank))

        table.add_row(
            rank_emoji,
            r.provider,
            wer_str,
            cer_str,
            ttft_str,
            f"{r.total_seconds:.3f}",
            conf_str,
            f"${r.cost_usd:.5f}",
            f"{s.composite_score:.4f}",
            transcript_preview,
        )

    c.print()
    c.print(table)
    c.print(f"\n[dim]Sorted by: {sort_by} | Lower score = better[/dim]")


def render_benchmark_result(result: BenchmarkResult, sort_by: SortKey = "composite") -> None:
    c = Console()
    c.print(f"\n[bold]Run ID:[/bold] {result.run_id}  "
            f"[bold]Audio:[/bold] {result.audio_file}")
    if result.ground_truth:
        c.print(f"[bold]Ground Truth:[/bold] [italic]{result.ground_truth}[/italic]")
    else:
        c.print("[bold]Ground Truth:[/bold] [dim]None (latency+cost only scoring)[/dim]")
    render_leaderboard(result.scored_results, sort_by=sort_by, console=c)


def results_to_json(results: list[BenchmarkResult]) -> str:
    return json.dumps([r.model_dump(mode="json") for r in results], indent=2, default=str)
