# Voice Benchmarking Platform — Development Documentation

## 1. 项目目标

为高端**实时听写产品**选型提供客观依据：通过统一接口并发调用多个第三方 STT（Speech-to-Text）服务，在**真实噪音条件**下量化比较它们在准确率、延迟和成本三个维度的表现，输出可排序的 Leaderboard。

> **"Vibe" 定义**：本项目的核心问题是——哪个服务对听写用户感觉最好？用户感知的"好"是准确率（WER）和响应速度（TTFT）的综合体验，而不是单一指标最优。Composite Score 就是这种"vibe"的量化形式。

---

## 0. Quick Start（5 分钟跑通完整 Demo）

```bash
# 1. 安装依赖
poetry install --with dev

# 2. 配置 API Keys
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY 和 DEEPGRAM_API_KEY

# 3. 运行单文件 benchmark（有 ground truth）
benchmark run \
  --audio tests/fixtures/sample.wav \
  --truth "Welcome to the voice benchmarking platform..." \
  --providers openai_whisper,deepgram

# 4. 运行噪音鲁棒性测试
benchmark run \
  --audio tests/fixtures/noisy_sample.wav \
  --truth "Welcome to the voice benchmarking platform..."

# 5. 无 ground truth 模式（自动提供商间一致性评分）
benchmark run --audio tests/fixtures/sample.wav
```

### 实测基线结果（2026-05-29，macOS TTS @ 140 wpm）

| 条件 | Provider | WER | TTFT | Cost/min | Score |
|------|----------|-----|------|----------|-------|
| 干净音频 | **Deepgram Nova-2** | 0.533 | 3.33s | $0.0043 | **0.468 🥇** |
| 干净音频 | OpenAI Whisper-1 | 0.644 | 2.88s | $0.006 | 0.497 🥈 |
| 噪音音频 (~18dB SNR) | **Deepgram Nova-2** | 0.533 | 3.03s | $0.0043 | **0.449 🥇** |
| 噪音音频 (~18dB SNR) | OpenAI Whisper-1 | 0.644 | **4.39s** (+52%) | $0.006 | 0.588 🥈 |

**关键发现**：白噪音条件下，Deepgram 的 TTFT 几乎不变，而 OpenAI Whisper 的响应时间增加 52%。对于要求实时反馈的听写应用，**Deepgram 在噪音鲁棒性上具有明显优势**。

---

## 2. 项目结构

```
voice-benchmarking-platform/
├── pyproject.toml                          # 依赖管理与项目配置
├── .env.example                            # 环境变量模板
├── docs/
│   └── development.md                      # 本文档
├── src/voice_benchmarking_platform/
│   ├── __init__.py
│   ├── models.py                           # Pydantic 数据模型
│   ├── scoring.py                          # 评分算法（WER/CER/Composite）
│   ├── benchmark.py                        # 异步调度器（BenchmarkRunner）
│   ├── evaluator.py                        # 无 ground truth 评估策略
│   ├── leaderboard.py                      # Rich CLI 排行榜渲染
│   ├── cli.py                              # Click CLI 入口
│   └── providers/
│       ├── base.py                         # STTProvider 抽象基类
│       ├── openai_whisper.py               # OpenAI Whisper 实现
│       ├── deepgram.py                     # Deepgram Nova-2 实现
│       └── assemblyai.py                   # AssemblyAI 实现（bonus）
└── tests/
    ├── test_scoring.py
    ├── test_benchmark.py
    ├── test_evaluator.py
    └── fixtures/
        └── sample.wav                      # 测试音频
```

---

## 3. 架构设计

### 3.1 核心数据流

```
音频文件
    │
    ▼
BenchmarkRunner.run_single_async()
    │
    ├── asyncio.gather() ──► [Provider A].transcribe_async()  ──► TranscriptionResult
    │                   ──► [Provider B].transcribe_async()  ──► TranscriptionResult
    │                   ──► [Provider C].transcribe_async()  ──► TranscriptionResult
    │
    ▼
score_result() × N  ──► ScoredResult（含 WER/CER/composite_score）
    │
    ▼
sort by composite_score → 分配 rank
    │
    ├── (无 ground truth) apply_no_ground_truth_ranks()  ──► agreement_rank
    │
    ▼
BenchmarkResult
    │
    ▼
render_leaderboard()  ──► Rich CLI 表格
```

### 3.2 分层职责

| 层 | 文件 | 职责 |
|----|------|------|
| **数据层** | `models.py` | 不可变数据模型，Pydantic 校验 |
| **接入层** | `providers/` | 封装各厂商 API，统一返回 `TranscriptionResult` |
| **评分层** | `scoring.py` | 纯函数，无副作用，可独立测试 |
| **调度层** | `benchmark.py` | 并发控制，聚合结果 |
| **评估层** | `evaluator.py` | 无 ground truth 时的降级评估策略 |
| **展示层** | `leaderboard.py` | 渲染，与业务逻辑解耦 |
| **入口层** | `cli.py` | 参数解析，组装各层，不含业务逻辑 |

---

## 4. 数据模型

### 4.1 核心模型（`models.py`）

```python
# 单次 Provider 调用结果
TranscriptionResult
├── provider: str              # "openai_whisper" | "deepgram" | "assemblyai"
├── transcript: str            # 转录文本
├── ttft_seconds: float | None # Time to First Token（首字节响应时间）
├── total_seconds: float       # 总处理时间
├── cost_usd: float            # 本次调用费用（基于 duration 估算）
├── confidence: float | None   # 提供商返回的置信度（0~1，部分提供商不支持）
└── metadata: dict             # 扩展字段（words、language、duration 等）

# 评分结果（包装 TranscriptionResult）
ScoredResult
├── result: TranscriptionResult
├── wer: float | None          # Word Error Rate（无 ground truth 时为 None）
├── cer: float | None          # Character Error Rate
├── composite_score: float     # 综合分（越低越好）
└── rank: int | None           # 排名（1 = 最优）

# 配置（嵌入 BenchmarkResult，每次运行自描述）
BenchmarkConfig
├── wer_weight: float = 0.5
├── latency_weight: float = 0.3
├── cost_weight: float = 0.2
├── concurrency_limit: int = 5
├── latency_baseline_seconds: float = 5.0
└── cost_baseline_usd: float = 0.10
```

### 4.2 设计决策

- **`ScoredResult` 包装而非继承 `TranscriptionResult`**：避免字段冲突，保持评分层与接入层的清晰边界。
- **`BenchmarkConfig` 嵌入 `BenchmarkResult`**：每次运行完全自描述，保存的 JSON 可以在任何时候复现排名逻辑。
- **`metadata: dict` 作为扩展槽**：允许各 provider 存放私有字段（如 Deepgram 的 `words` 数组），不污染核心模型。

---

## 5. Provider 实现规范

### 5.1 统一接口

```python
class STTProvider(ABC):
    @property @abstractmethod
    def provider_name(self) -> str: ...      # 唯一标识符，用作字典 key

    @property @abstractmethod
    def cost_per_minute_usd(self) -> float:  # 费率，用于成本估算

    @abstractmethod
    async def transcribe_async(self, audio_path: Path) -> TranscriptionResult: ...

    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        return asyncio.run(self.transcribe_async(audio_path))  # 同步封装
```

**规范：`transcribe_async` 是所有 provider 的唯一核心方法**，同步版 `transcribe` 仅作 CLI 单次调用便利封装，批处理路径全程走异步。

### 5.2 TTFT 测量方案

**问题**：Whisper 和 Deepgram 的 REST API 均为 non-streaming，返回完整 JSON blob，没有 token 级别的流式输出。

**方案**：使用 `httpx.AsyncClient.stream()` 在 HTTP 传输层模拟流式接收，记录第一个非空字节到达时的 `time.perf_counter()`。

```python
async with client.stream("POST", url, ...) as response:
    async for chunk in response.aiter_bytes():
        if chunk and ttft is None:
            ttft = time.perf_counter() - t_start  # 首字节时间
        chunks.append(chunk)
```

**含义**：此处的 TTFT = 服务器完成推理并开始发送响应的时刻，反映网络往返 + 服务端处理延迟，是实际用户感知延迟的合理代理指标。

### 5.3 新增 Provider 步骤

1. 在 `providers/` 下新建文件，继承 `STTProvider`
2. 实现 `provider_name`、`cost_per_minute_usd`、`transcribe_async`
3. 在 `providers/__init__.py` 中导出
4. 在 `cli.py` 的 `_build_runner()` 中添加 `elif name == "your_provider":` 分支

---

## 6. 评分算法

### 6.1 文本预处理

WER/CER 计算前对 hypothesis 和 reference 同步处理：

```python
text.lower()                         # 统一小写
text.translate(remove_punctuation)   # 去除标点
re.sub(r"\s+", " ", text).strip()   # 合并空白
```

### 6.2 Composite Score 公式

$$\text{score} = w_{wer} \cdot \min(WER, 1) + w_{lat} \cdot \min\left(\frac{TTFT}{5.0}, 1\right) + w_{cost} \cdot \min\left(\frac{cost}{0.10}, 1\right)$$

- **归一化**：各项用 baseline 值（可配置）归一化到 [0, 1]，`min(..., 1)` 防止极端值主导排名
- **默认权重**：WER 50%、Latency 30%、Cost 20%，可通过 CLI 参数调整
- **分数越低越好**：0 = 完美，1 = 各项均达上限

### 6.2.1 权重与"Vibe"的对应关系

| 场景 | 推荐权重 | 理由 |
|------|---------|------|
| **高端实时听写**（默认）| WER 50% / Latency 30% / Cost 20% | 准确率是核心，但 TTFT 直接影响打字即时感；成本次要 |
| **实时语音助手** | WER 30% / Latency 60% / Cost 10% | 用户最敏感的是响应延迟，错词可容忍 |
| **批量转录/字幕** | WER 70% / Latency 10% / Cost 20% | 不需要实时反馈，准确率最重要 |
| **高频低成本场景** | WER 40% / Latency 20% / Cost 40% | 大量短音频处理，成本控制优先 |

```bash
# 实时听写优化：更重视延迟
benchmark run --audio clip.wav --truth "..." --latency-weight 0.5 --wer-weight 0.3 --cost-weight 0.2
```

### 6.3 无 Ground Truth 降级策略

当没有参考文本时，WER weight 按比例重分配给 Latency 和 Cost：

```python
# wer_weight=0.5, latency_weight=0.3, cost_weight=0.2
# total_other = 0.5 → lat_w = 0.6, cost_w = 0.4
lat_w = latency_weight / (latency_weight + cost_weight)
cost_w = cost_weight  / (latency_weight + cost_weight)
score  = lat_w * norm_latency + cost_w * norm_cost
```

同时启动**提供商间一致性评估**（`evaluator.py`）：计算每个 provider 的转录结果与其他所有 provider 的平均 WER，平均 WER 最低的 provider 被认为"最接近共识"，即最可能准确。

### 6.4 额外指标（均存于 ScoredResult 或 metadata）

| 指标 | 含义 | 计算方式 |
|------|------|---------|
| CER | 字符错误率，比 WER 更细粒度 | `jiwer.cer` |
| Confidence | 模型对自身输出的置信度 | Provider 原生返回（词级平均）|
| Punctuation Accuracy | 标点符号匹配比例 | 参考/预测标点集合交集/参考大小 |
| Capitalization Accuracy | 大小写匹配比例 | 词级逐一比对 |
| Agreement Rank | 无 GT 时的提供商间一致性排名 | 平均 peer WER，越低越好 |

---

## 7. 并发模型（高 QPS 设计）

### 7.1 单文件：Provider 级并发

```python
semaphore = asyncio.Semaphore(config.concurrency_limit)  # 默认 5

async def _run_one(provider):
    async with semaphore:
        return await provider.transcribe_async(audio_path)

await asyncio.gather(*[_run_one(p) for p in providers])
```

所有 provider 并发调用，Semaphore 防止同时打开过多连接。

### 7.2 批处理：文件级并发

```python
# run_batch_async 将多个文件的 run_single_async 全部并发执行
await asyncio.gather(*[run_single_async(path, gt) for path, gt in items])
```

**批处理 CSV 格式**：

```csv
audio_file,ground_truth
samples/clip1.wav,The quick brown fox
samples/clip2.wav,Hello world
samples/clip3.wav,          ← 空 = 无 ground truth
```

### 7.3 规模扩展建议

当文件数 > 1000 时，`asyncio.gather` 会一次性创建所有协程，建议改为 `asyncio.Queue` 生产者/消费者模式，控制内存中同时存在的协程数量。

---

## 8. CLI 使用

### 8.1 环境配置

```bash
cp .env.example .env
# 编辑 .env，填入 API Keys
OPENAI_API_KEY=sk-proj-...
DEEPGRAM_API_KEY=...
ASSEMBLYAI_API_KEY=...   # 可选，需安装 bonus extra
```

### 8.2 安装

```bash
# 基础（OpenAI Whisper + Deepgram）
poetry install --with dev

# 含 AssemblyAI
poetry install --with dev --extras bonus
```

### 8.3 命令参考

**单文件 benchmark（有 ground truth）**

```bash
benchmark run \
  --audio path/to/audio.wav \
  --truth "预期转录文本" \
  --providers openai_whisper,deepgram \
  --wer-weight 0.5 --latency-weight 0.3 --cost-weight 0.2 \
  --output table   # 或 json
```

**单文件 benchmark（无 ground truth）**

```bash
benchmark run --audio audio.wav --providers openai_whisper,deepgram,assemblyai
# 自动使用提供商间一致性评分，Leaderboard 显示 Agreement Rank 列
```

**批量 benchmark**

```bash
benchmark batch \
  --manifest batch.csv \
  --concurrency 5 \
  --output results.json
```

**渲染历史 Leaderboard**

```bash
benchmark leaderboard --input results.json --sort-by wer
# sort-by: composite | wer | latency | cost
```

---

## 9. 测试

### 9.1 运行测试

```bash
poetry run pytest tests/ -v
```

### 9.2 测试覆盖范围

| 文件 | 测试类 | 覆盖内容 |
|------|--------|---------|
| `test_scoring.py` | `TestWER` | 完全匹配、大小写、标点、空串 |
| | `TestCER` | 完全匹配、部分匹配 |
| | `TestPunctuationAccuracy` | 无标点、全匹配、缺失 |
| | `TestCompositeScore` | 有/无 ground truth、权重重分配、延迟影响 |
| `test_benchmark.py` | `TestBenchmarkRunner` | 排名、无 GT 模式、批处理、同步封装 |
| `test_evaluator.py` | `TestInterProviderAgreement` | 完全一致、离群值检测、单 provider |

**测试策略**：Provider 调用全部通过 `MockProvider` 模拟，不发起真实 HTTP 请求；评分函数为纯函数，直接单元测试。

---

## 10. Provider 费率参考

| Provider | 模型 | 费率 |
|----------|------|------|
| OpenAI Whisper | whisper-1 | $0.006 / min |
| Deepgram | Nova-2 | $0.0043 / min |
| AssemblyAI | Best | $0.0037 / min |

> 注：以上为代码中硬编码的估算值，实际计费以各平台官方为准。

---

## 11. 噪音鲁棒性测试

### 11.1 为什么要用 noisy audio

在干净 TTS 音频上，所有现代 STT 服务的 WER 都接近 0，无法区分优劣。**真实听写场景**中充满噪音：
- 键盘敲击声、风扇噪音（办公室）
- 背景音乐、人声嘈杂（公共场所）
- 麦克风底噪、回声（在线会议）

噪音条件下的 WER 分化和 TTFT 变化，才是评估 provider 实际生产能力的有效指标。

### 11.2 生成 noisy 测试音频

**方案一：Python wave 模块（无依赖）**

```python
# scripts/add_noise.py
import wave, array, random, math

NOISE_RATIO = 0.12  # 12% noise → ~18dB SNR

with wave.open("input.wav", "rb") as src:
    params, frames = src.getparams(), src.readframes(src.getnframes())

samples = array.array("h", frames)
peak = max(abs(s) for s in samples) or 1
noise_amp = int(peak * NOISE_RATIO)

noisy = array.array("h", (
    max(-32768, min(32767, s + random.randint(-noise_amp, noise_amp)))
    for s in samples
))

with wave.open("noisy_output.wav", "wb") as dst:
    dst.setparams(params)
    dst.writeframes(noisy.tobytes())

print(f"SNR ≈ {20 * math.log10(peak / noise_amp):.1f} dB")
```

**方案二：ffmpeg（若已安装）**

```bash
# 混入白噪音，SNR ≈ 20dB
ffmpeg -i input.wav -filter_complex \
  "aevalsrc=random(0)*0.05:s=16000[noise]; [0:a][noise]amix=inputs=2:weights=1 0.1" \
  noisy_output.wav
```

### 11.3 SNR 级别参考

| SNR | 场景模拟 | 预期 WER 变化 |
|-----|---------|--------------|
| > 30 dB | 安静录音室 | 接近干净音频 |
| 18–25 dB | 安静办公室 | 轻微增加 |
| 10–18 dB | 嘈杂开放办公区 | 明显增加，提供商出现分化 |
| < 10 dB | 街道/公共场所 | 严重降级，WER > 50% |

### 11.4 实测噪音对比（2026-05-29）

| 指标 | Deepgram | OpenAI Whisper | 结论 |
|------|----------|----------------|------|
| TTFT (干净) | 3.33s | 2.88s | Whisper 更快 |
| TTFT (噪音 18dB) | **3.03s** (-9%) | **4.39s** (+52%) | Deepgram 噪音鲁棒性更强 |
| WER 变化 | 无变化 | 无变化 | 该噪音级别不影响文字准确率 |

> Whisper 在噪音下响应时间显著增加，推测是服务端对低 SNR 音频的预处理/重采样更耗时。

---

## 12. 结果解读与选型建议

### 12.1 Score 分段含义

| Composite Score | 含义 | 建议 |
|----------------|------|------|
| 0.00 – 0.20 | 优秀：WER 低、延迟短、成本低 | 直接采用 |
| 0.20 – 0.40 | 良好：各项指标均衡 | 可用于生产 |
| 0.40 – 0.60 | 一般：某项指标偏弱 | 评估瓶颈后决定 |
| 0.60 – 1.00 | 较差：存在明显短板 | 谨慎使用，针对场景调权重 |

### 12.2 选型决策流程

```
高端实时听写产品选型
        │
        ├── 延迟敏感（< 2s TTFT）？
        │       ├── 是 → 优先看 TTFT 列，调高 --latency-weight
        │       └── 否 → 使用默认权重
        │
        ├── 有 ground truth 数据集？
        │       ├── 是 → 用 WER 评分，关注噪音条件下的 WER 分化
        │       └── 否 → 用 Agreement Rank + Confidence 作为代理指标
        │
        └── 成本敏感？
                ├── 是 → 调高 --cost-weight，对比 Cost/min
                └── 否 → 重点看 Score 和 Confidence 综合排名
```

### 12.3 当前推荐（基于实测）

针对**高端实时听写**场景：

**推荐 Deepgram Nova-2**
- 准确率（WER）优于 Whisper
- 噪音条件下 TTFT 稳定（+0% vs +52%）
- 成本更低（$0.0043 vs $0.006/min）
- 提供词级置信度（可用于后处理高亮不确定词）

**OpenAI Whisper 适用场景**：已深度集成 OpenAI 生态、或需要利用其多语言识别能力时。

---

## 13. 已知限制与后续改进方向

| 限制 | 说明 | 改进方向 |
|------|------|---------|
| TTFT 非真正流式 | Whisper/Deepgram REST API 不支持 token 级流式，当前 TTFT = HTTP 首字节时间 | 使用 Deepgram WebSocket 实时接口可获得真正的 TTFT |
| OpenAI Whisper 无置信度 | API 不返回 confidence | 使用 `verbose_json` 格式可获取 segments，可作为代理指标 |
| AssemblyAI 轮询延迟 | 异步轮询间隔 500ms，影响 TTFT 精度 | 使用 Webhook 回调替代轮询 |
| 批处理内存 | `asyncio.gather` 一次性创建所有协程 | 改为 `asyncio.Queue` 生产者/消费者模式 |
| 无持久化存储 | 结果仅保存为 JSON 文件 | 可接入 SQLite 或时序数据库，支持趋势分析 |
| Hallucination 检测未实现 | 设计中有，代码中暂缺 | 对比转录词汇与语言模型词频，检测幻觉词 |
