from __future__ import annotations

import asyncio
from pathlib import Path

from voice_benchmarking_platform.models import BenchmarkConfig, BenchmarkResult, ScoredResult
from voice_benchmarking_platform.providers.base import STTProvider
from voice_benchmarking_platform.scoring import score_result


class BenchmarkRunner:
    """Orchestrates concurrent STT provider calls and produces ranked results."""

    def __init__(self, config: BenchmarkConfig | None = None) -> None:
        self.config = config or BenchmarkConfig()
        self._providers: dict[str, STTProvider] = {}

    def register(self, provider: STTProvider) -> None:
        self._providers[provider.provider_name] = provider

    async def run_single_async(
        self,
        audio_path: Path,
        ground_truth: str | None = None,
    ) -> BenchmarkResult:
        semaphore = asyncio.Semaphore(self.config.concurrency_limit)

        async def _run_one(provider: STTProvider) -> ScoredResult:
            async with semaphore:
                result = await provider.transcribe_async(audio_path)
            return score_result(result, ground_truth, self.config)

        tasks = [_run_one(p) for p in self._providers.values()]
        scored: list[ScoredResult] = list(await asyncio.gather(*tasks))
        scored.sort(key=lambda s: s.composite_score)
        for i, s in enumerate(scored):
            s.rank = i + 1

        return BenchmarkResult(
            audio_file=str(audio_path),
            ground_truth=ground_truth,
            scored_results=scored,
            config=self.config,
        )

    def run_single(self, audio_path: Path, ground_truth: str | None = None) -> BenchmarkResult:
        return asyncio.run(self.run_single_async(audio_path, ground_truth))

    async def run_batch_async(
        self,
        items: list[tuple[Path, str | None]],
    ) -> list[BenchmarkResult]:
        """Run multiple audio files concurrently (provider-level concurrency per file)."""
        return list(await asyncio.gather(*[
            self.run_single_async(path, gt) for path, gt in items
        ]))
