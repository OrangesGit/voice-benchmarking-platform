"""No-ground-truth evaluation strategies.

When ground truth text is unavailable, we provide two strategies:

1. Inter-provider agreement (default): compute pairwise WER between all
   providers and rank by lowest average WER against peers. The most
   "consensus" transcript scores best.

2. LLM judge (optional): send all transcripts to GPT-4o and ask it to
   rank them by likely accuracy. Requires OPENAI_API_KEY.
"""
from __future__ import annotations

import json
import os

from voice_benchmarking_platform.models import ScoredResult, TranscriptionResult
from voice_benchmarking_platform.scoring import compute_wer


def rank_by_inter_provider_agreement(
    results: list[TranscriptionResult],
) -> list[tuple[TranscriptionResult, float]]:
    """Rank providers by average WER against all other providers' transcripts.

    Lower agreement_wer = more consensus = likely more accurate.
    Returns list of (result, agreement_wer) sorted best-first.
    """
    if len(results) < 2:
        return [(r, 0.0) for r in results]

    scores: list[tuple[TranscriptionResult, float]] = []
    for r in results:
        peer_wers = [
            compute_wer(r.transcript, other.transcript)
            for other in results
            if other.provider != r.provider
        ]
        avg_wer = sum(peer_wers) / len(peer_wers) if peer_wers else 0.0
        scores.append((r, avg_wer))

    return sorted(scores, key=lambda x: x[1])


async def rank_by_llm_judge(
    results: list[TranscriptionResult],
    api_key: str | None = None,
) -> list[tuple[TranscriptionResult, int]]:
    """Ask GPT-4o to rank transcripts by likely accuracy.

    Returns list of (result, rank) where rank 1 = best.
    Falls back to inter-provider agreement if API call fails.
    """
    import httpx

    key = api_key or os.environ.get("OPENAI_API_KEY", "")
    if not key:
        agreement = rank_by_inter_provider_agreement(results)
        return [(r, i + 1) for i, (r, _) in enumerate(agreement)]

    numbered = "\n".join(
        f"{i + 1}. [{r.provider}]: \"{r.transcript}\""
        for i, r in enumerate(results)
    )
    prompt = (
        "You are an expert at evaluating speech-to-text transcriptions.\n"
        "Given the following transcripts of the same audio recording, "
        "rank them from most to least accurate. Consider coherence, "
        "natural language flow, and consistency.\n\n"
        f"{numbered}\n\n"
        "Reply with JSON only: {\"ranking\": [<1-based indices best to worst>], "
        "\"reasoning\": \"<one sentence>\"}"
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                    "max_tokens": 200,
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            data = json.loads(content)
            ranking: list[int] = data["ranking"]

        ranked: list[tuple[TranscriptionResult, int]] = []
        for rank_pos, original_idx in enumerate(ranking):
            if 1 <= original_idx <= len(results):
                ranked.append((results[original_idx - 1], rank_pos + 1))
        return ranked

    except Exception:
        agreement = rank_by_inter_provider_agreement(results)
        return [(r, i + 1) for i, (r, _) in enumerate(agreement)]


def apply_no_ground_truth_ranks(scored: list[ScoredResult]) -> None:
    """Mutate ScoredResult list to add llm_rank metadata from agreement scoring."""
    results = [s.result for s in scored]
    ranked = rank_by_inter_provider_agreement(results)
    rank_map = {r.provider: i + 1 for i, (r, _) in enumerate(ranked)}
    agree_map = {r.provider: wer for r, wer in ranked}

    for s in scored:
        s.result.metadata["agreement_rank"] = rank_map.get(s.result.provider)
        s.result.metadata["avg_peer_wer"] = round(agree_map.get(s.result.provider, 0.0), 4)
