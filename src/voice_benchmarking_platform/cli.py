from __future__ import annotations

import asyncio
import csv
import json
import os
import sys
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console

from voice_benchmarking_platform.benchmark import BenchmarkRunner
from voice_benchmarking_platform.leaderboard import render_benchmark_result, render_leaderboard, results_to_json
from voice_benchmarking_platform.models import BenchmarkConfig, BenchmarkResult

load_dotenv()

console = Console()


def _build_runner(
    provider_names: str,
    wer_weight: float,
    latency_weight: float,
    cost_weight: float,
    concurrency: int,
) -> BenchmarkRunner:
    from voice_benchmarking_platform.providers.registry import get_provider_by_name

    config = BenchmarkConfig(
        wer_weight=wer_weight,
        latency_weight=latency_weight,
        cost_weight=cost_weight,
        concurrency_limit=concurrency,
        providers=provider_names.split(","),
    )
    runner = BenchmarkRunner(config)

    for name in config.providers:
        name = name.strip()
        base_name = name.split(":")[0]

        # YAML registry handles both "provider" and "provider:model" formats
        provider = get_provider_by_name(name)
        if provider:
            runner.register(provider)
            continue

        # Fallback: AssemblyAI (Python-coded, needs polling)
        if base_name == "assemblyai":
            try:
                from voice_benchmarking_platform.providers.assemblyai import AssemblyAIProvider
            except ImportError:
                console.print("[red]AssemblyAI provider not available. Run: poetry install --extras bonus[/red]")
                sys.exit(1)
            key = os.environ.get("ASSEMBLYAI_API_KEY", "")
            if not key:
                console.print("[red]ASSEMBLYAI_API_KEY not set[/red]")
                sys.exit(1)
            runner.register(AssemblyAIProvider(api_key=key))

        else:
            console.print(f"[red]Unknown provider: {name}[/red]")
            sys.exit(1)

    return runner


@click.group()
def cli() -> None:
    """Voice STT Benchmarking Platform — compare providers by accuracy, latency, and cost."""


@cli.command()
@click.option("--audio", required=True, type=click.Path(exists=True, path_type=Path), help="Audio file path")
@click.option("--truth", default=None, help="Ground truth transcript (optional)")
@click.option("--providers", default="openai_whisper,deepgram", show_default=True,
              help="Comma-separated providers. Use provider:model to pin a model, e.g. deepgram:nova-2,openai_whisper:whisper-1")
@click.option("--wer-weight", default=0.5, show_default=True, type=float)
@click.option("--latency-weight", default=0.3, show_default=True, type=float)
@click.option("--cost-weight", default=0.2, show_default=True, type=float)
@click.option("--output", type=click.Choice(["table", "json"]), default="table", show_default=True)
@click.option("--sort-by", type=click.Choice(["composite", "wer", "latency", "cost"]), default="composite", show_default=True)
def run(
    audio: Path,
    truth: str | None,
    providers: str,
    wer_weight: float,
    latency_weight: float,
    cost_weight: float,
    output: str,
    sort_by: str,
) -> None:
    """Run a benchmark on a single audio file."""
    runner = _build_runner(providers, wer_weight, latency_weight, cost_weight, concurrency=5)
    console.print(f"[bold]Benchmarking:[/bold] {audio.name} with providers: {providers}")
    with console.status("[bold green]Calling STT providers in parallel…"):
        result = runner.run_single(audio, ground_truth=truth)

    if output == "json":
        click.echo(json.dumps(result.model_dump(mode="json"), indent=2, default=str))
    else:
        render_benchmark_result(result, sort_by=sort_by)  # type: ignore[arg-type]


@cli.command()
@click.option("--manifest", required=True, type=click.Path(exists=True, path_type=Path), help="CSV file: audio_file,ground_truth")
@click.option("--providers", default="openai_whisper,deepgram", show_default=True)
@click.option("--concurrency", default=5, show_default=True, type=int)
@click.option("--output", type=click.Path(), default="results.json", show_default=True)
@click.option("--wer-weight", default=0.5, type=float)
@click.option("--latency-weight", default=0.3, type=float)
@click.option("--cost-weight", default=0.2, type=float)
def batch(
    manifest: Path,
    providers: str,
    concurrency: int,
    output: str,
    wer_weight: float,
    latency_weight: float,
    cost_weight: float,
) -> None:
    """Run benchmarks for multiple audio files from a CSV manifest."""
    items: list[tuple[Path, str | None]] = []
    with manifest.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            audio_path = Path(row["audio_file"])
            truth = row.get("ground_truth") or None
            items.append((audio_path, truth))

    if not items:
        console.print("[red]No items found in manifest[/red]")
        sys.exit(1)

    runner = _build_runner(providers, wer_weight, latency_weight, cost_weight, concurrency)
    console.print(f"[bold]Batch benchmarking:[/bold] {len(items)} files")

    async def _run():
        with console.status(f"[bold green]Processing {len(items)} files…"):
            return await runner.run_batch_async(items)

    results = asyncio.run(_run())

    out_path = Path(output)
    out_path.write_text(results_to_json(results))
    console.print(f"\n[green]Results saved to:[/green] {out_path}")

    for r in results:
        render_benchmark_result(r)


@cli.command()
@click.option("--input", "input_path", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--sort-by", type=click.Choice(["composite", "wer", "latency", "cost"]), default="composite", show_default=True)
def leaderboard(input_path: Path, sort_by: str) -> None:
    """Render a leaderboard from a saved results JSON file."""
    data = json.loads(input_path.read_text())
    if isinstance(data, list):
        results = [BenchmarkResult.model_validate(r) for r in data]
    else:
        results = [BenchmarkResult.model_validate(data)]

    all_scored = [s for r in results for s in r.scored_results]
    render_leaderboard(all_scored, sort_by=sort_by)  # type: ignore[arg-type]
