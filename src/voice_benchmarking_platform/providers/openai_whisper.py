from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

from voice_benchmarking_platform.models import TranscriptionResult
from voice_benchmarking_platform.providers.base import STTProvider

_API_URL = "https://api.openai.com/v1/audio/transcriptions"


class OpenAIWhisperProvider(STTProvider):
    """OpenAI Whisper API provider.

    TTFT is measured as the time until the first non-empty HTTP response byte
    arrives. The Whisper REST API returns a single JSON blob (no token streaming),
    so TTFT captures server processing + network latency to response start.
    """

    COST_PER_MINUTE_USD = 0.006  # $0.006/min as of 2024

    def __init__(self, api_key: str, model: str = "whisper-1") -> None:
        self._api_key = api_key
        self._model = model

    @property
    def provider_name(self) -> str:
        return "openai_whisper"

    @property
    def cost_per_minute_usd(self) -> float:
        return self.COST_PER_MINUTE_USD

    async def transcribe_async(self, audio_path: Path) -> TranscriptionResult:
        audio_bytes = audio_path.read_bytes()
        t_start = time.perf_counter()
        ttft: float | None = None
        chunks: list[bytes] = []

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                _API_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                files={"file": (audio_path.name, audio_bytes, "audio/wav")},
                data={"model": self._model, "response_format": "verbose_json"},
            ) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes():
                    if chunk and ttft is None:
                        ttft = time.perf_counter() - t_start
                    chunks.append(chunk)

        total_seconds = time.perf_counter() - t_start
        body = json.loads(b"".join(chunks))
        duration: float = body.get("duration", 0.0)

        return TranscriptionResult(
            provider=self.provider_name,
            audio_file=str(audio_path),
            transcript=body["text"].strip(),
            ttft_seconds=ttft,
            total_seconds=total_seconds,
            cost_usd=self._calculate_cost(duration),
            model_version=self._model,
            confidence=None,  # Whisper API does not expose confidence
            metadata={
                "language": body.get("language"),
                "duration_seconds": duration,
            },
        )
