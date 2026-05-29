from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

from voice_benchmarking_platform.models import TranscriptionResult
from voice_benchmarking_platform.providers.base import STTProvider

_API_URL = "https://api.deepgram.com/v1/listen"


class DeepgramProvider(STTProvider):
    """Deepgram Nova-2 prerecorded transcription provider.

    TTFT is measured as time to first non-empty HTTP response byte.
    Deepgram returns word-level confidence; we store the utterance-level
    confidence from the top alternative.
    """

    COST_PER_MINUTE_USD = 0.0043  # Nova-2 pay-as-you-go

    def __init__(self, api_key: str, model: str = "nova-2") -> None:
        self._api_key = api_key
        self._model = model

    @property
    def provider_name(self) -> str:
        return "deepgram"

    @property
    def cost_per_minute_usd(self) -> float:
        return self.COST_PER_MINUTE_USD

    async def transcribe_async(self, audio_path: Path) -> TranscriptionResult:
        audio_bytes = audio_path.read_bytes()
        t_start = time.perf_counter()
        ttft: float | None = None
        chunks: list[bytes] = []

        params = {
            "model": self._model,
            "smart_format": "true",
            "punctuate": "true",
            "utterances": "false",
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                _API_URL,
                headers={
                    "Authorization": f"Token {self._api_key}",
                    "Content-Type": "audio/wav",
                },
                params=params,
                content=audio_bytes,
            ) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes():
                    if chunk and ttft is None:
                        ttft = time.perf_counter() - t_start
                    chunks.append(chunk)

        total_seconds = time.perf_counter() - t_start
        body = json.loads(b"".join(chunks))

        metadata = body.get("metadata", {})
        duration: float = metadata.get("duration", 0.0)

        channels = body.get("results", {}).get("channels", [])
        alt = channels[0]["alternatives"][0] if channels else {"transcript": "", "confidence": None, "words": []}

        transcript: str = alt.get("transcript", "").strip()
        confidence: float | None = alt.get("confidence")

        words: list[dict] = alt.get("words", [])
        word_confidences = [w.get("confidence", 0.0) for w in words if "confidence" in w]
        avg_word_confidence = sum(word_confidences) / len(word_confidences) if word_confidences else confidence

        return TranscriptionResult(
            provider=self.provider_name,
            audio_file=str(audio_path),
            transcript=transcript,
            ttft_seconds=ttft,
            total_seconds=total_seconds,
            cost_usd=self._calculate_cost(duration),
            model_version=self._model,
            confidence=avg_word_confidence,
            metadata={
                "duration_seconds": duration,
                "detected_language": metadata.get("detected_language"),
                "words": words,
            },
        )
