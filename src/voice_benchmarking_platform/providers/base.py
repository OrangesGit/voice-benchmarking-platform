from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from pathlib import Path

from voice_benchmarking_platform.models import TranscriptionResult


class STTProvider(ABC):
    """Unified interface for all Speech-to-Text providers."""

    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @property
    @abstractmethod
    def cost_per_minute_usd(self) -> float: ...

    @abstractmethod
    async def transcribe_async(self, audio_path: Path) -> TranscriptionResult: ...

    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        return asyncio.run(self.transcribe_async(audio_path))

    def _calculate_cost(self, duration_seconds: float) -> float:
        return (duration_seconds / 60.0) * self.cost_per_minute_usd
