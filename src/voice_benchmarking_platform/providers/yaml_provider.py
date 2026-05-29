"""Generic HTTP STT provider driven by a YAML configuration block."""
from __future__ import annotations

import json
import re
import time
import wave
from pathlib import Path
from typing import Any

import httpx

from voice_benchmarking_platform.models import TranscriptionResult
from voice_benchmarking_platform.providers.base import STTProvider


def _resolve_templates(value: str, ctx: dict[str, str]) -> str:
    """Replace {{key}} placeholders with values from ctx."""
    for k, v in ctx.items():
        value = value.replace(f"{{{{{k}}}}}", v)
    return value


def _extract(data: Any, path: str | None) -> Any:
    """Extract a value from nested dicts/lists using dot-notation with array indexing.

    Example: "results.channels[0].alternatives[0].transcript"
    """
    if not path:
        return None
    # Split on dots that are NOT inside brackets
    parts = re.split(r"\.(?![^\[]*\])", path)
    for part in parts:
        if data is None:
            return None
        m = re.match(r"^(\w+)\[(\d+)\]$", part)
        if m:
            key, idx = m.group(1), int(m.group(2))
            data = data.get(key, []) if isinstance(data, dict) else data
            data = data[idx] if isinstance(data, list) and len(data) > idx else None
        else:
            data = data.get(part) if isinstance(data, dict) else None
    return data


def _wav_duration(audio_path: Path) -> float:
    """Read duration from a WAV header; returns 0.0 for non-WAV or unreadable files."""
    try:
        with wave.open(str(audio_path), "rb") as w:
            return w.getnframes() / w.getframerate()
    except Exception:
        return 0.0


def _build_auth_header(auth_cfg: dict, api_key: str) -> dict[str, str]:
    auth_type = auth_cfg.get("type", "bearer")
    if auth_type == "bearer":
        return {"Authorization": f"Bearer {api_key}"}
    if auth_type == "token":
        return {"Authorization": f"Token {api_key}"}
    if auth_type == "api-key":
        return {"api-key": api_key}
    return {}


class YAMLProvider(STTProvider):
    """STT provider whose HTTP behaviour is fully described by a YAML config block."""

    def __init__(self, config: dict, api_key: str, model: str | None = None) -> None:
        self._cfg = config
        self._api_key = api_key
        self._model = model or config.get("model_version", "")
        self._tpl_ctx = {
            "model_version": self._model,
            "api_key": api_key,
        }

    @property
    def provider_name(self) -> str:
        return f"{self._cfg['name']}:{self._model}"

    @property
    def display_name(self) -> str:
        base = self._cfg.get("display_name", self._cfg["name"])
        for m in self._cfg.get("available_models", []):
            if m["id"] == self._model:
                return f"{base} ({m.get('display_name', self._model)})"
        return f"{base} ({self._model})"

    @property
    def cost_per_minute_usd(self) -> float:
        for m in self._cfg.get("available_models", []):
            if m["id"] == self._model and "cost_per_minute_usd" in m:
                return float(m["cost_per_minute_usd"])
        return float(self._cfg["cost_per_minute_usd"])

    async def transcribe_async(self, audio_path: Path) -> TranscriptionResult:
        audio_bytes = audio_path.read_bytes()
        req_cfg = self._cfg["request"]
        resp_cfg = self._cfg.get("response", {})

        url = _resolve_templates(req_cfg["url"], self._tpl_ctx)
        auth_header = _build_auth_header(req_cfg.get("auth", {}), self._api_key)

        # Build query params (template-resolved values)
        params = {
            k: _resolve_templates(str(v), self._tpl_ctx)
            for k, v in req_cfg.get("params", {}).items()
        }

        body_cfg = req_cfg.get("body", {})
        body_type = body_cfg.get("type", "raw")

        t_start = time.perf_counter()
        ttft: float | None = None
        chunks: list[bytes] = []

        # Model-level body_fields override takes priority over provider-level fields
        _model_cfg = next(
            (m for m in self._cfg.get("available_models", []) if m["id"] == self._model), {}
        )
        _body_fields = _model_cfg.get("body_fields") or body_cfg.get("fields", {})

        async with httpx.AsyncClient(timeout=120.0) as client:
            if body_type == "multipart":
                file_field = body_cfg.get("file_field", "file")
                extra_fields = {
                    k: _resolve_templates(str(v), self._tpl_ctx)
                    for k, v in _body_fields.items()
                }
                files = {file_field: (audio_path.name, audio_bytes, "audio/wav")}
                async with client.stream(
                    req_cfg.get("method", "POST"),
                    url,
                    headers=auth_header,
                    params=params,
                    files=files,
                    data=extra_fields,
                ) as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_bytes():
                        if chunk and ttft is None:
                            ttft = time.perf_counter() - t_start
                        chunks.append(chunk)
            else:
                content_type = body_cfg.get("content_type", "audio/wav")
                async with client.stream(
                    req_cfg.get("method", "POST"),
                    url,
                    headers={**auth_header, "Content-Type": content_type},
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

        transcript = str(_extract(body, resp_cfg.get("transcript")) or "").strip()
        duration = float(_extract(body, resp_cfg.get("duration")) or 0.0)
        if duration == 0.0:
            duration = _wav_duration(audio_path)
        language = _extract(body, resp_cfg.get("language"))
        confidence = _extract(body, resp_cfg.get("confidence"))
        words = _extract(body, resp_cfg.get("words")) or []

        # Compute avg word confidence when words list is available
        if words and isinstance(words, list):
            word_confs = [w.get("confidence", 0.0) for w in words if isinstance(w, dict) and "confidence" in w]
            if word_confs:
                confidence = sum(word_confs) / len(word_confs)

        return TranscriptionResult(
            provider=self.provider_name,
            audio_file=str(audio_path),
            transcript=transcript,
            ttft_seconds=ttft,
            total_seconds=total_seconds,
            cost_usd=self._calculate_cost(duration),
            model_version=self._model,
            confidence=float(confidence) if confidence is not None else None,
            metadata={
                "duration_seconds": duration,
                "detected_language": language,
                "words": words,
                "source": "yaml_registry",
            },
        )
