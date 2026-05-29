"""Streamlit frontend for Voice Benchmarking Platform."""
from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

from voice_benchmarking_platform.benchmark import BenchmarkRunner
from voice_benchmarking_platform.models import BenchmarkConfig, BenchmarkResult, ScoredResult
from voice_benchmarking_platform.providers.registry import list_available_providers

load_dotenv()

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Voice Benchmarking Platform",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.metric-card {
    background: #1e1e2e;
    border: 1px solid #313244;
    border-radius: 10px;
    padding: 16px 20px;
    text-align: center;
}
.rank-badge {
    font-size: 2rem;
    line-height: 1;
}
.provider-name {
    font-size: 1.1rem;
    font-weight: 600;
    color: #cdd6f4;
    margin: 4px 0;
}
.score-val {
    font-size: 1.6rem;
    font-weight: 700;
    color: #89b4fa;
}
.transcript-box {
    background: #181825;
    border-left: 3px solid #89b4fa;
    border-radius: 4px;
    padding: 10px 14px;
    font-family: monospace;
    font-size: 0.95rem;
    color: #cdd6f4;
    margin-top: 6px;
}
</style>
""", unsafe_allow_html=True)


# ── Load provider registry ─────────────────────────────────────────────────────
_yaml_providers = list_available_providers()
# AssemblyAI is a Python-coded provider not in YAML; append it manually
_all_providers = _yaml_providers + [
    {"name": "assemblyai", "display_name": "AssemblyAI", "api_key_env": "ASSEMBLYAI_API_KEY"},
]

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ Configuration")

    st.subheader("Providers")
    _provider_checks: dict[str, bool] = {}
    for _p in _all_providers:
        _default = _p["name"] in ("openai_whisper", "deepgram")
        _help = "Requires poetry install --extras bonus" if _p["name"] == "assemblyai" else None
        _provider_checks[_p["name"]] = st.checkbox(
            _p["display_name"], value=_default, help=_help
        )

    st.divider()
    st.subheader("Scoring Weights")
    st.caption("Must sum to 1.0")
    wer_w = st.slider("WER (Accuracy)", 0.0, 1.0, 0.5, 0.05)
    lat_w = st.slider("Latency (TTFT)", 0.0, 1.0, 0.3, 0.05)
    cost_w = round(1.0 - wer_w - lat_w, 2)
    st.metric("Cost weight (auto)", f"{cost_w:.2f}",
              delta=None if 0 <= cost_w <= 1 else "⚠️ invalid")

    st.divider()
    st.subheader("API Keys")
    with st.expander("Override .env keys"):
        oa_key = st.text_input("OPENAI_API_KEY", type="password",
                               value=os.environ.get("OPENAI_API_KEY", ""))
        dg_key = st.text_input("DEEPGRAM_API_KEY", type="password",
                               value=os.environ.get("DEEPGRAM_API_KEY", ""))
        ai_key = st.text_input("ASSEMBLYAI_API_KEY", type="password",
                               value=os.environ.get("ASSEMBLYAI_API_KEY", ""))

    st.divider()
    st.caption("v0.1.0 · [GitHub](https://github.com/OrangesGit/voice-benchmarking-platform)")


# ── Helpers ────────────────────────────────────────────────────────────────────
RANK_EMOJI = {1: "🥇", 2: "🥈", 3: "🥉"}

_SIDEBAR_KEY_MAP = {"openai_whisper": lambda: oa_key, "deepgram": lambda: dg_key, "assemblyai": lambda: ai_key}


def _build_runner(providers: list[str], wer_weight: float, lat_weight: float,
                  cost_weight: float) -> BenchmarkRunner:
    from voice_benchmarking_platform.providers.registry import get_provider_by_name

    config = BenchmarkConfig(
        wer_weight=wer_weight,
        latency_weight=lat_weight,
        cost_weight=cost_weight,
        providers=providers,
    )
    runner = BenchmarkRunner(config)
    for name in providers:
        sidebar_key = _SIDEBAR_KEY_MAP.get(name, lambda: "")()

        # YAML registry (supports optional key override)
        provider = get_provider_by_name(name, api_key=sidebar_key or None)
        if provider:
            runner.register(provider)
            continue

        # Fallback: AssemblyAI (Python-coded, needs polling — not expressible in YAML)
        if name == "assemblyai":
            from voice_benchmarking_platform.providers.assemblyai import AssemblyAIProvider
            key = sidebar_key or os.environ.get("ASSEMBLYAI_API_KEY", "")
            runner.register(AssemblyAIProvider(api_key=key))

    return runner


def _run_benchmark(audio_path: Path, ground_truth: str | None,
                   providers: list[str]) -> BenchmarkResult:
    if not 0 <= cost_w <= 1:
        st.error("Weight sliders exceed 1.0 — adjust WER or Latency weight.")
        st.stop()
    runner = _build_runner(providers, wer_w, lat_w, cost_w)
    return asyncio.run(runner.run_single_async(audio_path, ground_truth or None))


def _bar_chart(scored: list[ScoredResult], metric: str, title: str,
               color: str, fmt: str = ".3f") -> go.Figure:
    providers = [s.result.provider for s in scored]
    if metric == "wer":
        values = [s.wer if s.wer is not None else 0.0 for s in scored]
    elif metric == "cer":
        values = [s.cer if s.cer is not None else 0.0 for s in scored]
    elif metric == "ttft":
        values = [s.result.ttft_seconds or s.result.total_seconds for s in scored]
    elif metric == "total":
        values = [s.result.total_seconds for s in scored]
    elif metric == "cost":
        values = [s.result.cost_usd for s in scored]
    elif metric == "score":
        values = [s.composite_score for s in scored]
    elif metric == "confidence":
        values = [s.result.confidence or 0.0 for s in scored]
    else:
        values = []

    colors = [color] * len(providers)
    if values:
        best_idx = values.index(min(values))
        colors[best_idx] = "#a6e3a1"  # highlight winner

    fig = go.Figure(go.Bar(
        x=providers, y=values,
        marker_color=colors,
        text=[f"{v:{fmt}}" for v in values],
        textposition="outside",
    ))
    fig.update_layout(
        title=title,
        plot_bgcolor="#1e1e2e",
        paper_bgcolor="#1e1e2e",
        font_color="#cdd6f4",
        height=260,
        margin=dict(t=40, b=20, l=10, r=10),
        yaxis=dict(gridcolor="#313244"),
        xaxis=dict(gridcolor="#313244"),
        showlegend=False,
    )
    return fig


# ── Main ────────────────────────────────────────────────────────────────────────
st.title("🎙️ Voice Benchmarking Platform")
st.caption("Compare STT providers by accuracy · latency · cost — find your best \"vibe\"")

st.divider()

col_upload, col_truth = st.columns([1, 1])

with col_upload:
    st.subheader("1. Upload Audio")
    audio_file = st.file_uploader("WAV / MP3 / M4A", type=["wav", "mp3", "m4a", "flac"])
    if audio_file:
        st.audio(audio_file)
    else:
        use_sample = st.checkbox("Use built-in sample (8.5s TTS speech)", value=True)

with col_truth:
    st.subheader("2. Ground Truth (optional)")
    ground_truth = st.text_area(
        "Paste the expected transcript",
        height=120,
        placeholder="Leave empty to use no-ground-truth mode (inter-provider agreement scoring)",
    )
    if not ground_truth:
        st.info("No ground truth → scoring by Latency + Cost + Agreement Rank")

st.divider()

# Provider selection summary
selected_providers = [name for name, checked in _provider_checks.items() if checked]

if not selected_providers:
    st.warning("Select at least one provider in the sidebar.")
    st.stop()

run_col, _ = st.columns([1, 3])
with run_col:
    run_btn = st.button("▶ Run Benchmark", type="primary", use_container_width=True,
                        disabled=not selected_providers)

if run_btn:
    # Resolve audio path
    if audio_file:
        suffix = Path(audio_file.name).suffix
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.write(audio_file.read())
        tmp.flush()
        audio_path = Path(tmp.name)
    elif use_sample:
        audio_path = Path(__file__).parent / "tests/fixtures/sample.wav"
        if not audio_path.exists():
            st.error("Sample audio not found. Upload a file instead.")
            st.stop()
    else:
        st.error("Please upload an audio file.")
        st.stop()

    gt = ground_truth.strip() or None

    with st.spinner(f"Calling {len(selected_providers)} provider(s) in parallel…"):
        try:
            result = _run_benchmark(audio_path, gt, selected_providers)
        except Exception as e:
            st.error(f"Benchmark failed: {e}")
            st.stop()

    scored = result.scored_results
    st.success(f"Done — Run ID: `{result.run_id}`")
    st.divider()

    # ── Leaderboard cards ──────────────────────────────────────────────────────
    st.subheader("🏆 Leaderboard")
    card_cols = st.columns(len(scored))
    for col, s in zip(card_cols, scored):
        r = s.result
        wer_str = f"{s.wer:.3f}" if s.wer is not None else "N/A"
        cer_str = f"{s.cer:.3f}" if s.cer is not None else "N/A"
        ttft_str = f"{r.ttft_seconds:.2f}s" if r.ttft_seconds else "N/A"
        conf_str = f"{r.confidence:.3f}" if r.confidence is not None else "N/A"
        agree = r.metadata.get("agreement_rank")

        with col:
            st.markdown(f"""
<div class="metric-card">
  <div class="rank-badge">{RANK_EMOJI.get(s.rank or 0, f"#{s.rank}")}</div>
  <div class="provider-name">{r.provider}</div>
  <div class="score-val">{s.composite_score:.4f}</div>
  <small style="color:#a6adc8">composite score</small>
</div>""", unsafe_allow_html=True)
            st.markdown("")
            mc1, mc2 = st.columns(2)
            mc1.metric("WER", wer_str)
            mc2.metric("CER", cer_str)
            mc1.metric("TTFT", ttft_str)
            mc2.metric("Confidence", conf_str)
            mc1.metric("Cost", f"${r.cost_usd:.5f}")
            mc2.metric("Total", f"{r.total_seconds:.2f}s")
            if agree:
                st.caption(f"Agreement rank: #{agree}  "
                           f"(avg peer WER: {r.metadata.get('avg_peer_wer', 'N/A')})")
            st.markdown(f'<div class="transcript-box">"{r.transcript[:120]}{"…" if len(r.transcript) > 120 else ""}"</div>',
                        unsafe_allow_html=True)

    st.divider()

    # ── Charts ─────────────────────────────────────────────────────────────────
    st.subheader("📊 Metric Comparison")

    row1 = st.columns(3)
    with row1[0]:
        if any(s.wer is not None for s in scored):
            st.plotly_chart(_bar_chart(scored, "wer", "Word Error Rate (lower = better)",
                                       "#f38ba8"), use_container_width=True)
        else:
            st.info("WER not available (no ground truth)")
    with row1[1]:
        st.plotly_chart(_bar_chart(scored, "ttft", "TTFT — Time to First Token (s)",
                                   "#89b4fa"), use_container_width=True)
    with row1[2]:
        st.plotly_chart(_bar_chart(scored, "cost", "Cost per Request (USD)",
                                   "#a6e3a1", fmt=".5f"), use_container_width=True)

    row2 = st.columns(3)
    with row2[0]:
        if any(s.cer is not None for s in scored):
            st.plotly_chart(_bar_chart(scored, "cer", "Char Error Rate (lower = better)",
                                       "#fab387"), use_container_width=True)
    with row2[1]:
        if any(s.result.confidence is not None for s in scored):
            st.plotly_chart(_bar_chart(scored, "confidence", "Avg Word Confidence (higher = better)",
                                       "#cba6f7", fmt=".3f"), use_container_width=True)
    with row2[2]:
        st.plotly_chart(_bar_chart(scored, "score", "Composite Score (lower = better)",
                                   "#89dceb"), use_container_width=True)

    st.divider()

    # ── Raw JSON ───────────────────────────────────────────────────────────────
    with st.expander("📄 Raw JSON result"):
        st.json(result.model_dump(mode="json"))
