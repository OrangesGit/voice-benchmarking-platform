"""Unit tests for no-ground-truth evaluator."""
import pytest

from voice_benchmarking_platform.evaluator import rank_by_inter_provider_agreement
from voice_benchmarking_platform.models import TranscriptionResult


def make_result(provider: str, transcript: str) -> TranscriptionResult:
    return TranscriptionResult(
        provider=provider,
        audio_file="test.wav",
        transcript=transcript,
        total_seconds=1.0,
        cost_usd=0.001,
        model_version="v1",
    )


class TestInterProviderAgreement:
    def test_identical_transcripts_score_equally(self):
        results = [
            make_result("a", "hello world"),
            make_result("b", "hello world"),
        ]
        ranked = rank_by_inter_provider_agreement(results)
        assert ranked[0][1] == pytest.approx(0.0)
        assert ranked[1][1] == pytest.approx(0.0)

    def test_divergent_transcript_ranks_last(self):
        results = [
            make_result("a", "hello world foo bar"),
            make_result("b", "hello world foo bar"),
            make_result("c", "completely different text"),  # outlier
        ]
        ranked = rank_by_inter_provider_agreement(results)
        # The outlier should have highest average peer WER
        outlier_entry = next(entry for entry in ranked if entry[0].provider == "c")
        consensus_entry = next(entry for entry in ranked if entry[0].provider == "a")
        assert outlier_entry[1] > consensus_entry[1]

    def test_single_result(self):
        results = [make_result("a", "hello")]
        ranked = rank_by_inter_provider_agreement(results)
        assert len(ranked) == 1
        assert ranked[0][1] == pytest.approx(0.0)
