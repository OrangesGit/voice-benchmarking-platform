from __future__ import annotations

import re
import string

from jiwer import cer as jiwer_cer
from jiwer import wer as jiwer_wer

from voice_benchmarking_platform.models import BenchmarkConfig, ScoredResult, TranscriptionResult


def _normalize(text: str) -> str:
    text = text.lower()
    text = text.translate(str.maketrans("", "", string.punctuation))
    text = re.sub(r"\s+", " ", text).strip()
    return text


def compute_wer(hypothesis: str, reference: str) -> float:
    """Word Error Rate. Returns value in [0, inf); >1.0 means more errors than words."""
    ref = _normalize(reference)
    hyp = _normalize(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    return jiwer_wer(ref, hyp)


def compute_cer(hypothesis: str, reference: str) -> float:
    """Character Error Rate. Finer-grained than WER for short utterances."""
    ref = _normalize(reference)
    hyp = _normalize(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    return jiwer_cer(ref, hyp)


def compute_punctuation_accuracy(hypothesis: str, reference: str) -> float:
    """Fraction of reference punctuation marks correctly present in hypothesis."""
    ref_puncts = [c for c in reference if c in string.punctuation]
    hyp_puncts = [c for c in hypothesis if c in string.punctuation]
    if not ref_puncts:
        return 1.0
    matches = sum(1 for c in ref_puncts if c in hyp_puncts)
    return matches / len(ref_puncts)


def compute_capitalization_accuracy(hypothesis: str, reference: str) -> float:
    """Fraction of reference words with correct capitalization."""
    ref_words = reference.split()
    hyp_words = hypothesis.split()
    if not ref_words:
        return 1.0
    matches = sum(1 for r, h in zip(ref_words, hyp_words) if r == h)
    return matches / len(ref_words)


def compute_composite(
    result: TranscriptionResult,
    ground_truth: str | None,
    config: BenchmarkConfig,
) -> tuple[float | None, float | None, float]:
    """Compute WER, CER, and composite score.

    Returns (wer, cer, composite_score). composite_score is in [0, 1] (lower = better).
    When ground_truth is None, WER/CER are None and wer_weight is redistributed.
    """
    wer: float | None = None
    cer: float | None = None

    if ground_truth is not None:
        wer = compute_wer(result.transcript, ground_truth)
        cer = compute_cer(result.transcript, ground_truth)

    latency = result.ttft_seconds if result.ttft_seconds is not None else result.total_seconds
    norm_latency = min(latency / config.latency_baseline_seconds, 1.0)
    norm_cost = min(result.cost_usd / config.cost_baseline_usd, 1.0)

    if wer is not None:
        norm_wer = min(wer, 1.0)
        score = (
            config.wer_weight * norm_wer
            + config.latency_weight * norm_latency
            + config.cost_weight * norm_cost
        )
    else:
        total_other = config.latency_weight + config.cost_weight
        lat_w = config.latency_weight / total_other
        cost_w = config.cost_weight / total_other
        score = lat_w * norm_latency + cost_w * norm_cost

    return wer, cer, score


def score_result(
    result: TranscriptionResult,
    ground_truth: str | None,
    config: BenchmarkConfig,
) -> ScoredResult:
    wer, cer, composite = compute_composite(result, ground_truth, config)
    return ScoredResult(
        result=result,
        ground_truth=ground_truth,
        wer=wer,
        cer=cer,
        composite_score=composite,
    )
