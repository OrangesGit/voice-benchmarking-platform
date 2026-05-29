from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class TranscriptionResult(BaseModel):
    provider: str
    audio_file: str
    transcript: str
    ttft_seconds: float | None = None  # time to first HTTP response byte
    total_seconds: float
    cost_usd: float
    model_version: str
    confidence: float | None = None  # provider-reported avg confidence [0,1]
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ScoredResult(BaseModel):
    result: TranscriptionResult
    ground_truth: str | None
    wer: float | None = None   # Word Error Rate; None when no ground truth
    cer: float | None = None   # Character Error Rate
    composite_score: float     # lower = better
    rank: int | None = None


class BenchmarkConfig(BaseModel):
    wer_weight: float = 0.5
    latency_weight: float = 0.3
    cost_weight: float = 0.2
    concurrency_limit: int = 5
    providers: list[str] = Field(default_factory=lambda: ["openai_whisper", "deepgram"])
    latency_baseline_seconds: float = 5.0
    cost_baseline_usd: float = 0.10


class BenchmarkResult(BaseModel):
    run_id: str = Field(default_factory=lambda: uuid4().hex[:8])
    audio_file: str
    ground_truth: str | None
    scored_results: list[ScoredResult]
    config: BenchmarkConfig
    created_at: datetime = Field(default_factory=datetime.utcnow)
