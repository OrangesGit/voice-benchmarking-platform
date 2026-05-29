"""Unit tests for BenchmarkRunner."""
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from voice_benchmarking_platform.benchmark import BenchmarkRunner
from voice_benchmarking_platform.models import BenchmarkConfig, TranscriptionResult
from voice_benchmarking_platform.providers.base import STTProvider


class MockProvider(STTProvider):
    def __init__(self, name: str, transcript: str, ttft: float = 1.0, total: float = 2.0, cost: float = 0.001):
        self._name = name
        self._transcript = transcript
        self._ttft = ttft
        self._total = total
        self._cost = cost

    @property
    def provider_name(self) -> str:
        return self._name

    @property
    def cost_per_minute_usd(self) -> float:
        return 0.006

    async def transcribe_async(self, audio_path: Path) -> TranscriptionResult:
        return TranscriptionResult(
            provider=self._name,
            audio_file=str(audio_path),
            transcript=self._transcript,
            ttft_seconds=self._ttft,
            total_seconds=self._total,
            cost_usd=self._cost,
            model_version="mock-v1",
        )


class TestBenchmarkRunner:
    @pytest.fixture
    def audio_path(self, tmp_path: Path) -> Path:
        p = tmp_path / "test.wav"
        p.write_bytes(b"RIFF" + b"\x00" * 40)
        return p

    @pytest.mark.asyncio
    async def test_run_single_returns_ranked_results(self, audio_path: Path):
        runner = BenchmarkRunner()
        runner.register(MockProvider("provider_a", "hello world", ttft=1.0, cost=0.01))
        runner.register(MockProvider("provider_b", "hello world", ttft=2.0, cost=0.02))

        result = await runner.run_single_async(audio_path, ground_truth="hello world")
        assert len(result.scored_results) == 2
        assert result.scored_results[0].rank == 1
        assert result.scored_results[1].rank == 2
        # First-ranked should have lower composite score
        assert result.scored_results[0].composite_score <= result.scored_results[1].composite_score

    @pytest.mark.asyncio
    async def test_run_single_no_ground_truth(self, audio_path: Path):
        runner = BenchmarkRunner()
        runner.register(MockProvider("provider_a", "hello world"))
        runner.register(MockProvider("provider_b", "hello earth"))

        result = await runner.run_single_async(audio_path, ground_truth=None)
        assert all(s.wer is None for s in result.scored_results)
        # Agreement metadata should be populated
        assert "agreement_rank" in result.scored_results[0].result.metadata

    @pytest.mark.asyncio
    async def test_run_batch(self, audio_path: Path):
        runner = BenchmarkRunner()
        runner.register(MockProvider("provider_a", "hello world"))

        items = [(audio_path, "hello world"), (audio_path, None)]
        results = await runner.run_batch_async(items)
        assert len(results) == 2

    def test_run_single_sync(self, audio_path: Path):
        runner = BenchmarkRunner()
        runner.register(MockProvider("provider_a", "hello world"))
        result = runner.run_single(audio_path, ground_truth="hello world")
        assert result.scored_results[0].rank == 1
