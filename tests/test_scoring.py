"""Unit tests for scoring module."""
import pytest
from voice_benchmarking_platform.models import BenchmarkConfig, TranscriptionResult
from voice_benchmarking_platform.scoring import (
    compute_wer,
    compute_cer,
    compute_punctuation_accuracy,
    compute_capitalization_accuracy,
    compute_composite,
    score_result,
)


def make_result(**kwargs) -> TranscriptionResult:
    defaults = dict(
        provider="test",
        audio_file="test.wav",
        transcript="hello world",
        ttft_seconds=1.0,
        total_seconds=2.0,
        cost_usd=0.001,
        model_version="test-v1",
    )
    defaults.update(kwargs)
    return TranscriptionResult(**defaults)


class TestWER:
    def test_perfect_match(self):
        assert compute_wer("hello world", "hello world") == pytest.approx(0.0)

    def test_case_insensitive(self):
        assert compute_wer("Hello World", "hello world") == pytest.approx(0.0)

    def test_punctuation_ignored(self):
        assert compute_wer("hello, world!", "hello world") == pytest.approx(0.0)

    def test_one_word_wrong(self):
        wer = compute_wer("hello earth", "hello world")
        assert wer > 0.0

    def test_empty_reference(self):
        assert compute_wer("", "") == pytest.approx(0.0)
        assert compute_wer("hello", "") == 1.0

    def test_all_wrong(self):
        wer = compute_wer("foo bar", "hello world")
        assert wer == pytest.approx(1.0)


class TestCER:
    def test_perfect_match(self):
        assert compute_cer("hello", "hello") == pytest.approx(0.0)

    def test_partial_match(self):
        cer = compute_cer("helo", "hello")
        assert 0.0 < cer < 1.0


class TestPunctuationAccuracy:
    def test_no_punctuation_in_ref(self):
        assert compute_punctuation_accuracy("hello world", "hello world") == pytest.approx(1.0)

    def test_all_present(self):
        result = compute_punctuation_accuracy("hello, world!", "hello, world!")
        assert result == pytest.approx(1.0)

    def test_missing_punctuation(self):
        result = compute_punctuation_accuracy("hello world", "hello, world!")
        assert result < 1.0


class TestCompositeScore:
    def test_with_ground_truth(self):
        result = make_result(transcript="hello world", ttft_seconds=1.0, total_seconds=2.0, cost_usd=0.001)
        config = BenchmarkConfig()
        wer, cer, score = compute_composite(result, "hello world", config)
        assert wer == pytest.approx(0.0)
        assert score >= 0.0
        assert score <= 1.0

    def test_without_ground_truth(self):
        result = make_result(ttft_seconds=1.0, total_seconds=2.0, cost_usd=0.001)
        config = BenchmarkConfig()
        wer, cer, score = compute_composite(result, None, config)
        assert wer is None
        assert cer is None
        assert 0.0 <= score <= 1.0

    def test_higher_latency_increases_score(self):
        config = BenchmarkConfig()
        fast = make_result(ttft_seconds=0.5, total_seconds=1.0, cost_usd=0.001)
        slow = make_result(ttft_seconds=4.0, total_seconds=5.0, cost_usd=0.001)
        _, _, fast_score = compute_composite(fast, None, config)
        _, _, slow_score = compute_composite(slow, None, config)
        assert fast_score < slow_score

    def test_weight_redistribution_without_ground_truth(self):
        config = BenchmarkConfig(wer_weight=0.5, latency_weight=0.3, cost_weight=0.2)
        result = make_result(ttft_seconds=5.0, total_seconds=5.0, cost_usd=0.1)
        _, _, score = compute_composite(result, None, config)
        # With redistributed weights: lat_w=0.6, cost_w=0.4 → score = 0.6*1 + 0.4*1 = 1.0
        assert score == pytest.approx(1.0, abs=0.01)


class TestScoreResult:
    def test_returns_scored_result(self):
        result = make_result(transcript="hello world")
        config = BenchmarkConfig()
        scored = score_result(result, "hello world", config)
        assert scored.result is result
        assert scored.wer is not None
        assert scored.composite_score >= 0.0
