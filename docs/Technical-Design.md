# Technical Design — Voice Benchmarking Platform

> This document answers seven core design questions using the actual implementation as ground truth.
> Code references use the format `file:line`.

---

## 1. Unified Wrapper Interface

**How is a single uniform interface built so that switching providers requires no changes to benchmarking logic?**

### STTProvider Abstract Base Class

All providers implement the same three-contract interface defined in `providers/base.py`:

```python
class STTProvider(ABC):
    @property @abstractmethod
    def provider_name(self) -> str: ...       # unique key, e.g. "deepgram:nova-2"

    @property @abstractmethod
    def cost_per_minute_usd(self) -> float: ...

    @abstractmethod
    async def transcribe_async(self, audio_path: Path) -> TranscriptionResult: ...

    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        return asyncio.run(self.transcribe_async(audio_path))   # sync convenience

    def _calculate_cost(self, duration_seconds: float) -> float:
        return (duration_seconds / 60.0) * self.cost_per_minute_usd
```

`BenchmarkRunner` only ever calls `transcribe_async` — it has zero knowledge of HTTP, auth, or response format. Adding a new provider never touches the runner or scoring logic.

### Two Implementation Paths

| Path | When to use | Example |
|------|-------------|---------|
| **YAMLProvider** (`providers/yaml_provider.py`) | REST API with static request/response shape | OpenAI Whisper, Deepgram |
| **Python subclass** | Polling, WebSocket, or SDK with async lifecycle | AssemblyAI |

**YAMLProvider** reads a declarative config block from `providers.yaml` and handles:
- Auth styles: `bearer` (`Authorization: Bearer key`), `token` (`Authorization: Token key`), `api-key` (header)
- Body styles: `multipart` (form upload, e.g. Whisper) and `raw` (binary stream, e.g. Deepgram)
- Template variables: `{{model_version}}`, `{{api_key}}` interpolated at request time
- Model-level `body_fields` override: a model entry can replace the parent `body.fields` entirely (used for `gpt-4o-transcribe` which rejects `verbose_json`)
- Response extraction: dot-notation with array indices, e.g. `results.channels[0].alternatives[0].transcript`

### Provider Registry

`providers/registry.py` loads `providers.yaml` at runtime and returns `STTProvider` instances:

```python
# Parse "deepgram:nova-2" → base_name="deepgram", model="nova-2"
provider = get_provider_by_name("deepgram:nova-2")

# List all providers and their available models (used by Streamlit UI)
infos = list_available_providers()
```

The `provider_name` property always returns `{base}:{model}` (e.g. `deepgram:nova-2`), ensuring uniqueness when multiple models of the same provider run in a single benchmark.

### Adding a New Provider (Zero Python)

Append a YAML block to `providers.yaml`. The CLI and UI discover it automatically on next run:

```yaml
- name: assemblyai_universal
  display_name: "AssemblyAI Universal"
  api_key_env: ASSEMBLYAI_API_KEY
  cost_per_minute_usd: 0.0062
  model_version: universal
  request:
    method: POST
    url: "https://api.assemblyai.com/v2/upload"
    auth:
      type: api-key
    body:
      type: raw
      content_type: audio/wav
  response:
    transcript: text
```

---

## 2. Accuracy Analysis (WER / CER)

**How is a scoring mechanism implemented to measure transcription accuracy?**

### Text Normalization

Before any metric is computed, both hypothesis and reference pass through `_normalize()` (`scoring.py:12`):

1. Lowercase
2. Remove all punctuation (`string.punctuation`)
3. Collapse whitespace

This prevents spurious errors from case differences or punctuation style mismatches.

### Word Error Rate (WER)

```python
def compute_wer(hypothesis: str, reference: str) -> float:
    ref = _normalize(reference)
    hyp = _normalize(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    return jiwer_wer(ref, hyp)
```

Uses the `jiwer` library (Levenshtein alignment at word level). WER ∈ [0, ∞); values > 1.0 mean the hypothesis has more errors than the reference has words. In the composite score it is clamped to 1.0.

### Character Error Rate (CER)

```python
def compute_cer(hypothesis: str, reference: str) -> float:
    return jiwer_cer(_normalize(reference), _normalize(hypothesis))
```

CER uses character-level Levenshtein. It is more sensitive than WER for:
- Short utterances (single-word errors dominate WER)
- Languages with no word boundaries
- Detecting partial recognition errors within long words

Both WER and CER are stored in `ScoredResult` and displayed in the leaderboard.

### Composite Score

The single ranking metric is a weighted sum of three normalized dimensions (`scoring.py:57`):

```
norm_wer     = min(WER, 1.0)
norm_latency = min(TTFT / 5.0, 1.0)      # baseline: 5 seconds
norm_cost    = min(cost_usd / 0.10, 1.0)  # baseline: $0.10

composite = wer_weight * norm_wer
          + latency_weight * norm_latency
          + cost_weight * norm_cost
```

Default weights: `wer=0.5, latency=0.3, cost=0.2`. Lower composite = better overall. All three inputs are normalized to [0, 1] against fixed baselines before weighting, making the dimensions comparable regardless of unit.

When no ground truth is provided, the WER term is dropped and the remaining two weights are renormalized proportionally:

```python
total_other = latency_weight + cost_weight
lat_w  = latency_weight / total_other
cost_w = cost_weight / total_other
score  = lat_w * norm_latency + cost_w * norm_cost
```

---

## 3. Performance Tracking (TTFT + Total Time)

**How are key latency metrics — especially Time to First Token (TTFT) — measured and recorded?**

### TTFT Measurement via HTTP Streaming

Both `YAMLProvider` and the Python provider implementations use `httpx.AsyncClient.stream()` with `aiter_bytes()`. This enables capturing the exact moment the server begins transmitting the response body:

```python
t_start = time.perf_counter()
ttft: float | None = None
chunks: list[bytes] = []

async with client.stream("POST", url, ...) as response:
    response.raise_for_status()
    async for chunk in response.aiter_bytes():
        if chunk and ttft is None:
            ttft = time.perf_counter() - t_start   # first non-empty byte
        chunks.append(chunk)

total_seconds = time.perf_counter() - t_start
```

This works for **non-streaming APIs** too (e.g., Whisper, Deepgram) — the "first byte" still marks the server's processing completion and start of network transfer, which correlates with user-perceived wait time.

### What Gets Recorded

| Field | Type | Meaning |
|-------|------|---------|
| `ttft_seconds` | `float \| None` | Time from request send to first response byte |
| `total_seconds` | `float` | Full wall-clock time including response download |
| Both stored in | `TranscriptionResult` | Persisted in every `BenchmarkResult` |

`ttft_seconds` can be `None` if the network delivers the entire response in a single packet with no observable delay (rare in practice; handled by falling back to `total_seconds` in composite scoring).

### Latency in Composite Score

The composite formula uses TTFT as the latency signal, falling back to `total_seconds` when TTFT is unavailable (`scoring.py:74`). This means the score rewards providers that start responding quickly, not just those that finish quickly — which matters for real-time transcription UX.

---

## 4. Comparative Report (Leaderboard)

**How is a concise leaderboard output generated for comparing providers?**

### CLI Leaderboard — Rich Table

`leaderboard.py` renders a terminal-formatted Rich table via `benchmark run` or `benchmark leaderboard`:

```
Rank │ Provider              │ WER    │ CER    │ TTFT(s) │ Total(s) │ Cost(USD) │ Score  │ Transcript
─────┼───────────────────────┼────────┼────────┼─────────┼──────────┼───────────┼────────┼────────────────────────────
  1  │ deepgram:nova-2       │ 0.0400 │ 0.0200 │ 0.312   │ 0.891    │ $0.00014  │ 0.1240 │ Hello world this is a test
  2  │ openai_whisper:whis…  │ 0.0800 │ 0.0450 │ 0.841   │ 1.203    │ $0.00021  │ 0.2180 │ Hello world, this is a test
```

Columns: Rank, Provider (base + model), WER, CER, TTFT, Total, Cost, Composite Score, Transcript (truncated to 80 chars).

### Streamlit UI — Sortable Cards

`app.py` renders a card-per-provider layout with five sort dimensions:

| Sort Key | Field | Order |
|----------|-------|-------|
| Composite Score | `composite_score` | ascending (lower = better) |
| WER | `wer` | ascending |
| Latency (TTFT) | `ttft_seconds` | ascending |
| Cost | `cost_usd` | ascending |
| Confidence | `confidence` | descending (higher = better) |

Sort state is controlled by `st.radio()` and the result is stored in `st.session_state["benchmark_result"]` so the sort re-renders without re-running the benchmark. Internally, `_sort_scored()` deepcopies the scored list, sorts, and reassigns ranks — the original result is never mutated.

Provider names in the UI are formatted as `base<br><small>model</small>` to distinguish multiple models of the same provider at a glance.

### Saving and Loading Results

```bash
# Save to JSON
benchmark run --audio clip.wav --truth "text" --output json > results.json

# Re-render from saved JSON
benchmark leaderboard --input results.json --sort-by composite
```

---

## 5. High QPS Batch Architecture

**How does the system handle high-concurrency scenarios with many simultaneous requests?**

### Current Design: asyncio.gather + Semaphore

Within a single benchmark run, all providers are called concurrently under a shared `asyncio.Semaphore`:

```python
semaphore = asyncio.Semaphore(self.config.concurrency_limit)  # default: 5

async def _run_one(provider):
    async with semaphore:
        result = await provider.transcribe_async(audio_path)
    return score_result(result, ground_truth, self.config)

scored = list(await asyncio.gather(*[_run_one(p) for p in providers]))
```

For batch processing (`run_batch_async`), multiple audio files are dispatched simultaneously:

```python
async def run_batch_async(self, items: list[tuple[Path, str | None]]) -> list[BenchmarkResult]:
    return list(await asyncio.gather(*[
        self.run_single_async(path, gt) for path, gt in items
    ]))
```

This means with N audio files and M providers, up to `N × M` concurrent HTTP calls can be in flight simultaneously (bounded by the semaphore per file).

### Scaling Beyond a Single Process

For production-grade high QPS, the following architecture is recommended:

```
                        ┌─────────────────────┐
  Audio Uploads ──────► │   Task Queue        │  (Redis / SQS)
                        │   (job_id, path, gt) │
                        └──────────┬──────────┘
                                   │  pop
              ┌────────────────────▼────────────────────┐
              │         Worker Pool (N workers)          │
              │  ┌───────────┐  ┌───────────┐           │
              │  │ Worker 1  │  │ Worker 2  │  ...      │
              │  │asyncio    │  │asyncio    │           │
              │  │event loop │  │event loop │           │
              │  └───────────┘  └───────────┘           │
              └────────────────────┬────────────────────┘
                                   │  write
                        ┌──────────▼──────────┐
                        │   Results Store     │  (PostgreSQL / DynamoDB)
                        └─────────────────────┘
```

Key scaling decisions:

| Concern | Recommendation |
|---------|----------------|
| **CPU/IO isolation** | Multiple worker processes (not threads) via `multiprocessing` or Celery workers, each running its own `asyncio` event loop |
| **Per-provider rate limits** | Move the semaphore to a shared distributed counter (Redis `INCR/DECR`) so all workers respect the same provider rate ceiling |
| **Backpressure** | Queue depth monitoring; shed load by returning 429 when queue exceeds threshold |
| **Timeout handling** | `httpx.AsyncClient(timeout=120.0)` per request; workers retry with exponential backoff up to 3 times before marking job failed |
| **Cost control** | Track monthly spend per provider in the results store; hard-stop when approaching budget ceiling |
| **Audio preprocessing** | Normalize sample rate and format (16 kHz mono WAV) before enqueuing to avoid per-provider conversion overhead inside the hot path |

The `BenchmarkRunner` interface is already queue-friendly: `run_single_async(audio_path, ground_truth)` takes a file path and returns a `BenchmarkResult` that serializes cleanly to JSON.

---

## 6. No Ground Truth Evaluation

**How are providers compared when no reference transcript is available?**

When `ground_truth=None`, two complementary strategies are available (implemented in `evaluator.py`).

### Strategy 1: Inter-Provider Agreement (Default)

Compute pairwise WER between every pair of providers. The provider whose transcript is most similar to all other providers — the "consensus" transcript — is ranked highest.

```python
def rank_by_inter_provider_agreement(results):
    for r in results:
        peer_wers = [
            compute_wer(r.transcript, other.transcript)
            for other in results
            if other.provider != r.provider
        ]
        avg_wer = sum(peer_wers) / len(peer_wers)
    return sorted(scores, key=lambda x: x[1])  # lower avg_wer = better
```

The agreement WER and rank are attached to each `TranscriptionResult.metadata` as `avg_peer_wer` and `agreement_rank`. This runs automatically inside `BenchmarkRunner.run_single_async` when `ground_truth is None and len(providers) > 1`.

**Rationale**: If four providers broadly agree on a transcript and one outlier diverges significantly, the outlier is more likely to have made an error. This is a form of majority vote without requiring a human reference.

**Limitation**: If all providers share a systematic bias (e.g., all mis-hear a domain-specific term the same way), agreement will be high but all transcripts will be wrong. Agreement is a proxy, not a ground truth substitute.

### Strategy 2: LLM Judge (Optional)

When inter-provider agreement is insufficient (e.g., only two providers, or significantly divergent transcripts), an LLM can act as a zero-shot quality evaluator:

```python
async def rank_by_llm_judge(results, api_key=None):
    prompt = (
        "Given the following transcripts of the same audio recording, "
        "rank them from most to least accurate. Consider coherence, "
        "natural language flow, and consistency.\n\n"
        + numbered_transcripts
        + "\n\nReply with JSON only: {\"ranking\": [...], \"reasoning\": \"...\"}"
    )
    # POST to gpt-4o-mini with response_format=json_object
```

The LLM evaluates linguistic coherence, natural phrasing, and internal consistency. It degrades gracefully — if the API call fails for any reason, it falls back to inter-provider agreement automatically.

**Cost**: ~$0.0002 per evaluation call using `gpt-4o-mini`. Negligible relative to the STT costs being evaluated.

### When Each Strategy Applies

| Situation | Strategy |
|-----------|----------|
| ≥3 providers | Inter-provider agreement (free, always available) |
| 2 providers with divergent output | LLM judge |
| Single provider | Composite score (latency + cost only) |
| High-stakes evaluation | Both strategies, compare agreement rank vs LLM rank |

---

## 7. Multi-Dimensional Evaluation Metrics

**What additional metrics beyond WER can further differentiate provider quality?**

The platform currently computes or collects the following metrics. Bolded items are fully implemented; others are designed and partially implemented.

### Accuracy Metrics

| Metric | Implementation | Description |
|--------|----------------|-------------|
| **WER** | `scoring.compute_wer` | Word-level edit distance / reference word count |
| **CER** | `scoring.compute_cer` | Character-level edit distance; better for short clips |
| **Punctuation Accuracy** | `scoring.compute_punctuation_accuracy` | Fraction of reference punctuation marks present in hypothesis |
| **Capitalization Accuracy** | `scoring.compute_capitalization_accuracy` | Fraction of reference words with correct capitalization |
| Agreement WER | `evaluator.rank_by_inter_provider_agreement` | Average WER vs all peer providers (no-GT proxy) |

**Punctuation Accuracy** measures whether the provider correctly inserts commas, periods, and question marks — critical for downstream NLP pipelines (sentence segmentation, NER) but invisible to WER after normalization.

**Capitalization Accuracy** captures proper noun recognition (names, brands, acronyms) which WER misses due to lowercasing in normalization.

### Latency Metrics

| Metric | Field | Description |
|--------|-------|-------------|
| **TTFT** | `TranscriptionResult.ttft_seconds` | Time from request send to first response byte |
| **Total Time** | `TranscriptionResult.total_seconds` | Full wall-clock including download |
| Transfer Time | `total - ttft` | Network download duration; indicates response payload size |

### Confidence Metrics

| Metric | Source | Description |
|--------|--------|-------------|
| **API Confidence** | `TranscriptionResult.confidence` | Provider-reported average confidence (Deepgram: avg word confidence; OpenAI: N/A) |
| **Per-Word Confidence** | `metadata.words` | Word-level confidence array; useful for identifying uncertain segments |

When a provider returns per-word confidence (Deepgram's `results.channels[0].alternatives[0].words`), the platform computes a weighted average and stores it as the overall confidence score (`yaml_provider.py:171`).

### Cost Metrics

| Metric | Calculation | Description |
|--------|-------------|-------------|
| **Cost per call** | `(duration_sec / 60) × cost_per_min` | Actual cost for the audio file |
| **Cost per word** | `cost_usd / word_count` | Normalized efficiency metric |
| Cost per WER point | `cost_usd / (1 - WER)` | Value-for-money: lower = more accuracy per dollar |

### Advanced Metrics (Design-Level)

| Metric | Description | Implementation Path |
|--------|-------------|---------------------|
| **Hallucination Score** | Words in hypothesis not derivable from actual speech; detect by comparing transcript length vs audio duration ratio, or flagging known filler repetitions | Heuristic: `len(words) / duration > threshold`; or LLM binary classifier |
| **Language Detection Match** | Whether provider-detected language matches expected (`metadata.detected_language`) | Compare against `--language` CLI flag |
| **Consistency (Stddev WER)** | Run same audio 3× and measure WER variance — low consistency is a reliability risk | `benchmark run --repeat 3`; compute `stddev(wer_across_runs)` |
| **Domain-Specific WER** | Compute WER only on domain vocabulary (medical terms, product names) extracted from a glossary | Filter reference/hypothesis to domain tokens before WER |
| **Noise Robustness** | WER delta between clean and noisy versions of same audio | Run benchmark twice: once on clean, once on ffmpeg-mixed noisy audio |
| **Disfluency Handling** | Whether the provider correctly filters or transcribes fillers ("um", "uh", "like") | Compare output with and without filler-removal preprocessing |
| **Speaker Diarization Accuracy** | For multi-speaker audio: `DER` (Diarization Error Rate) | Requires word-level timestamps + reference speaker segments |

### Metric Selection Guide

For **real-time dictation** (highest perceived quality):
- Primary: TTFT, WER
- Secondary: Punctuation Accuracy, Capitalization Accuracy
- Ignore: Hallucination (rare in dictation), Diarization

For **meeting transcription** (accuracy over speed):
- Primary: WER, CER, Speaker Diarization
- Secondary: Confidence, Consistency
- Ignore: TTFT (batch processing, not real-time)

For **cost-sensitive batch jobs**:
- Primary: Cost per word, WER
- Secondary: Total Time
- Ignore: TTFT, Confidence

---

## Appendix: Data Flow

```
Audio File (WAV)
      │
      ▼
BenchmarkRunner.run_single_async()
      │
      ├── asyncio.Semaphore(5) ─── concurrent HTTP calls ──► STTProvider × N
      │                                                           │
      │                                               TranscriptionResult
      │                                         (transcript, ttft, cost, confidence)
      │
      ▼
score_result()  ──► compute_composite(wer, latency, cost)
      │
      ▼
ScoredResult  ──► sorted by composite_score ──► BenchmarkResult
      │
      ├── CLI: leaderboard.py (Rich table)
      └── UI:  app.py (Streamlit cards + sort radio)
```
