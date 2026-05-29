from __future__ import annotations

import time
from pathlib import Path

import httpx

from voice_benchmarking_platform.models import TranscriptionResult
from voice_benchmarking_platform.providers.base import STTProvider

_UPLOAD_URL = "https://api.assemblyai.com/v2/upload"
_TRANSCRIPT_URL = "https://api.assemblyai.com/v2/transcript"
_POLL_INTERVAL = 0.5


class AssemblyAIProvider(STTProvider):
    """AssemblyAI transcription provider (async polling model).

    TTFT is measured as time until the first completed transcript result
    is returned (polling until status == 'completed').
    """

    COST_PER_MINUTE_USD = 0.0037  # Best tier as of 2024

    def __init__(self, api_key: str, model: str = "best") -> None:
        self._api_key = api_key
        self._model = model

    @property
    def provider_name(self) -> str:
        return "assemblyai"

    @property
    def cost_per_minute_usd(self) -> float:
        return self.COST_PER_MINUTE_USD

    async def transcribe_async(self, audio_path: Path) -> TranscriptionResult:
        headers = {"authorization": self._api_key}
        t_start = time.perf_counter()
        ttft: float | None = None

        async with httpx.AsyncClient(timeout=120.0) as client:
            # Step 1: Upload audio
            upload_resp = await client.post(
                _UPLOAD_URL,
                headers=headers,
                content=audio_path.read_bytes(),
            )
            upload_resp.raise_for_status()
            audio_url: str = upload_resp.json()["upload_url"]

            # Step 2: Submit transcription job
            submit_resp = await client.post(
                _TRANSCRIPT_URL,
                headers=headers,
                json={
                    "audio_url": audio_url,
                    "speech_model": self._model,
                    "punctuate": True,
                    "format_text": True,
                },
            )
            submit_resp.raise_for_status()
            transcript_id: str = submit_resp.json()["id"]

            # Step 3: Poll until completed — TTFT = time to first completed result
            poll_url = f"{_TRANSCRIPT_URL}/{transcript_id}"
            result_body: dict = {}
            while True:
                poll_resp = await client.get(poll_url, headers=headers)
                poll_resp.raise_for_status()
                result_body = poll_resp.json()
                status = result_body.get("status")

                if status == "completed":
                    if ttft is None:
                        ttft = time.perf_counter() - t_start
                    break
                elif status == "error":
                    raise RuntimeError(f"AssemblyAI error: {result_body.get('error')}")

                import asyncio
                await asyncio.sleep(_POLL_INTERVAL)

        total_seconds = time.perf_counter() - t_start
        duration: float = (result_body.get("audio_duration") or 0)
        words: list[dict] = result_body.get("words") or []
        word_confidences = [w.get("confidence", 0.0) for w in words if "confidence" in w]
        avg_confidence = sum(word_confidences) / len(word_confidences) if word_confidences else None

        return TranscriptionResult(
            provider=self.provider_name,
            audio_file=str(audio_path),
            transcript=(result_body.get("text") or "").strip(),
            ttft_seconds=ttft,
            total_seconds=total_seconds,
            cost_usd=self._calculate_cost(duration),
            model_version=self._model,
            confidence=avg_confidence,
            metadata={
                "duration_seconds": duration,
                "words": words,
                "acoustic_model": result_body.get("acoustic_model"),
            },
        )
