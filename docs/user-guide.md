# Voice Benchmarking Platform — 使用指南

> 面向产品或业务人员：无需了解代码，按步骤操作即可获得 STT 评测报告。

---

## 目录

1. [前置条件](#1-前置条件)
2. [安装与启动](#2-安装与启动)
3. [Streamlit 网页界面](#3-streamlit-网页界面使用指南)
4. [CLI 命令行](#4-cli-命令行使用指南)
5. [如何读懂评测结果](#5-如何读懂评测结果)
6. [添加新的 STT Provider](#6-添加新的-stt-provider)
7. [常见问题](#7-常见问题)

---

## 1. 前置条件

### 1.1 支持的 Provider 与模型

| Provider | 模型 | 费率 / 分钟 | 置信度 | 备注 |
|----------|------|-----------|--------|------|
| **OpenAI** | `whisper-1` | $0.006 | — | 经典模型 |
| | `gpt-4o-transcribe` | $0.006 | — | 更高准确率 |
| | `gpt-4o-mini-transcribe` | $0.003 | — | 最低成本 |
| **Deepgram** | `nova-2` | $0.0043 | ✓ 词级 | 默认，综合最优 |
| | `nova-2-general` | $0.0043 | ✓ 词级 | nova-2 别名 |
| | `enhanced` | $0.0043 | ✓ 词级 | 旧一代 |
| | `base` | $0.0025 | ✓ 词级 | 最低成本 |
| **AssemblyAI** | best | $0.0037 | ✓ | 需额外安装 |

**推荐起步组合**：Deepgram（有免费额度）+ OpenAI，涵盖两家主流服务的多个模型对比。

申请地址：
- OpenAI：platform.openai.com
- Deepgram：console.deepgram.com
- AssemblyAI：www.assemblyai.com

### 1.2 系统环境

- Python 3.13+
- [Poetry](https://python-poetry.org/docs/)（Python 包管理器）
- macOS / Linux（Windows 需 WSL2）

---

## 2. 安装与启动

```bash
# 1. 克隆项目
git clone https://github.com/OrangesGit/voice-benchmarking-platform.git
cd voice-benchmarking-platform

# 2. 安装依赖
poetry install

# 3. 配置 API Keys
cp .env.example .env
```

用文本编辑器打开 `.env`，填入你的 Key：

```
OPENAI_API_KEY=sk-proj-...
DEEPGRAM_API_KEY=xxxxxxxxxxxxxxxx
ASSEMBLYAI_API_KEY=xxxxxxxxxxxxxxxx   # 可选
```

---

## 3. Streamlit 网页界面使用指南

### 3.1 启动

```bash
poetry run streamlit run app.py
```

浏览器自动打开 `http://localhost:8501`：

```
左侧边栏                       主区域
──────────────────────────     ──────────────────────────────────
⚙️ Configuration                1. Upload Audio
                                [文件上传] 或 [使用内置样本]
Providers
☑ OpenAI Whisper               2. Ground Truth (optional)
  ↳ Models [whisper-1 ×]       [输入预期转录文本]
☑ Deepgram
  ↳ Models [nova-2 ×]          [▶ Run Benchmark]
☐ AssemblyAI                   2 configuration(s) will run in parallel

Scoring Weights
WER (Accuracy)  ████░  0.50
Latency (TTFT)  ███░░  0.30
Cost (auto)            0.20
```

### 3.2 操作步骤

**Step 1 — 选择 Provider 和模型**

在左侧勾选 STT 服务，勾选后会出现 `↳ Models` 多选框：
- **单模型**：直接使用默认选中的模型
- **多模型**：点击下拉追加模型，同一供应商的多个模型会同时参与评测
- 可跨供应商同时选多个，例如 Deepgram nova-2 + Deepgram base + OpenAI whisper-1

主区域会实时显示本次将并行运行的配置数量：
> `3 configuration(s) will run in parallel: deepgram:nova-2 · deepgram:base · openai_whisper:whisper-1`

**Step 2 — 上传音频**

- **上传文件**：支持 WAV / MP3 / M4A / FLAC，建议时长 5–60 秒
- **使用内置样本**：勾选 "Use built-in sample"，使用项目自带的 8.5 秒 TTS 音频

**Step 3 — 填写 Ground Truth（可选）**

Ground Truth 是**你已知的正确转录文本**。

- **填写后**：平台计算 WER/CER，获得精确的准确率评分
- **不填写**：平台改用「提供商间一致性评分」（Agreement Rank），不需要人工校对

**Step 4 — 调整权重（可选）**

| 场景 | WER | Latency | Cost |
|------|-----|---------|------|
| 高端实时听写（默认） | 0.50 | 0.30 | 0.20 |
| 语音助手（响应速度优先） | 0.20 | 0.60 | 0.20 |
| 批量转录（准确率优先） | 0.70 | 0.10 | 0.20 |
| 成本敏感场景 | 0.40 | 0.20 | 0.40 |

> Cost 权重自动计算：`1.0 - WER权重 - Latency权重`，无需手动填写。

**Step 5 — 点击 ▶ Run Benchmark**

等待几秒（取决于音频长度和网络），结果页自动出现。

### 3.3 结果页说明

**🏆 Leaderboard（排行榜）**

排行榜上方有排序控件：

```
Sort by  ● Composite Score  ○ WER  ○ Latency (TTFT)  ○ Cost  ○ Confidence
```

点击任意维度，卡片立即重排，🥇🥈🥉 重新分配，卡片中央大数字切换为对应指标值。切换排序不需要重新跑 benchmark（结果缓存在页面中）。

每张卡片包含：

```
🥇
deepgram (nova-2)
0.4683
composite score

WER    0.533   CER    1.536
TTFT   3.33s   Conf.  0.901
Cost  $0.000   Total  3.33s

"Welcome to the voice bench…"
```

**📊 Metric Comparison（六张图表）**

| 图表 | 含义 | 越低越好？ |
|------|------|---------|
| Word Error Rate | 词级别错误率 | ✓ 越低越好 |
| TTFT | 首字节响应时间（秒） | ✓ 越低越好 |
| Cost per Request | 本次调用费用（美元） | ✓ 越低越好 |
| Char Error Rate | 字符级别错误率 | ✓ 越低越好 |
| Avg Word Confidence | 词级置信度（0–1） | ✗ 越高越好 |
| Composite Score | 综合评分 | ✓ 越低越好 |

> 绿色高亮柱 = 该指标最优的配置。

**📄 Raw JSON result**

展开可看到完整的原始数据，包括每个词的置信度、检测语言等。

---

## 4. CLI 命令行使用指南

CLI 适合批量测试、自动化流水线或无 GUI 环境。

### 4.1 单文件测试

```bash
# 基本用法（有 ground truth）
poetry run benchmark run \
  --audio tests/fixtures/sample.wav \
  --truth "the weather today is partly cloudy with a high of seventy two degrees"

# 指定单个 provider（用默认模型）
poetry run benchmark run \
  --audio my_audio.wav \
  --truth "预期文本" \
  --providers deepgram

# 指定 provider:model（固定模型）
poetry run benchmark run \
  --audio my_audio.wav \
  --providers openai_whisper:gpt-4o-mini-transcribe,deepgram:nova-2

# 同一供应商多个模型对比
poetry run benchmark run \
  --audio my_audio.wav \
  --providers deepgram:nova-2,deepgram:base

# 无 ground truth 模式（自动一致性评分）
poetry run benchmark run \
  --audio my_audio.wav

# 输出 JSON 保存结果
poetry run benchmark run \
  --audio my_audio.wav \
  --truth "预期文本" \
  --output json > result.json
```

**完整参数说明：**

| 参数 | 默认值 | 说明 |
|------|-------|------|
| `--audio` | 必填 | 音频文件路径（WAV/MP3/M4A） |
| `--truth` | 空 | 预期转录文本（不填则无 GT 模式） |
| `--providers` | `openai_whisper,deepgram` | 逗号分隔；支持 `provider:model` 格式 |
| `--wer-weight` | 0.5 | WER 权重（0–1） |
| `--latency-weight` | 0.3 | 延迟权重（0–1） |
| `--cost-weight` | 0.2 | 成本权重（0–1） |
| `--output` | `table` | 输出格式：`table` 或 `json` |
| `--sort-by` | `composite` | 排序依据：`composite` / `wer` / `latency` / `cost` |

### 4.2 批量测试（多个文件）

**准备 CSV manifest 文件：**

```csv
audio_file,ground_truth
samples/clip1.wav,Hello world this is a test
samples/clip2.wav,The quick brown fox jumps over the lazy dog
samples/clip3.wav,
```

> `ground_truth` 列可留空（表示无 GT 模式）。

**运行批量测试：**

```bash
poetry run benchmark batch \
  --manifest batch.csv \
  --concurrency 5 \
  --output results.json
```

| 参数 | 默认值 | 说明 |
|------|-------|------|
| `--manifest` | 必填 | CSV 文件路径 |
| `--concurrency` | 5 | 同时处理的文件数 |
| `--output` | `results.json` | 结果保存路径 |

**查看排行榜：**

```bash
# 按综合分排序
poetry run benchmark leaderboard --input results.json

# 按 WER 排序
poetry run benchmark leaderboard --input results.json --sort-by wer
```

### 4.3 CLI 输出示例

```
Benchmarking: sample.wav with providers: deepgram:nova-2,deepgram:base

                   STT Provider Benchmark Leaderboard
╭────┬───────────────┬───────┬───────┬───────┬────────┬────────┬──────────╮
│ R… │ Provider      │   WER │   CER │  TTFT │  Total │  Conf. │  Cost    │
├────┼───────────────┼───────┼───────┼───────┼────────┼────────┼──────────┤
│ 🥇 │ deepgram:base │   N/A │   N/A │ 2.76s │  2.76s │  0.942 │ $0.00036 │
│ 🥈 │ deepgram:nova-2│   N/A │   N/A │ 2.92s │  2.92s │  0.901 │ $0.00061 │
╰────┴───────────────┴───────┴───────┴───────┴────────┴────────┴──────────╯
```

---

## 5. 如何读懂评测结果

### 5.1 核心指标含义

**WER（Word Error Rate）— 词错误率**

```
WER = (替换词数 + 删除词数 + 插入词数) / 参考总词数
```

- `0.0` = 完全正确
- `0.5` = 约一半的词有错误
- `1.0+` = 错误多于正确（可超过 1.0）

> WER 计算前会统一转为小写、去除标点，因此大小写差异不影响分数。

**TTFT（Time to First Token）— 首字节响应时间**

从发送请求到收到第一个响应字节的时间，反映服务器处理延迟。对实时听写而言，TTFT < 3 秒通常能保证流畅体验。

**Confidence — 置信度**

Provider 对自己转录结果的置信程度（0–1）。置信度低的词可用于后处理高亮"不确定词"提示用户核对。注意：OpenAI 系列模型不返回置信度。

**Composite Score — 综合评分**

三个维度加权求和，越低越好：

```
Composite = WER权重 × min(WER, 1)
          + 延迟权重 × min(TTFT/5s, 1)
          + 成本权重 × min(Cost/$0.10, 1)
```

### 5.2 Score 分段参考

| 分数范围 | 水平 | 建议 |
|---------|------|------|
| 0.00 – 0.20 | 优秀 | 可直接用于生产 |
| 0.20 – 0.40 | 良好 | 适合大多数场景 |
| 0.40 – 0.60 | 一般 | 查看哪项指标拖了后腿，调整权重再决定 |
| 0.60 – 1.00 | 较差 | 不建议作为主要方案 |

### 5.3 多维度排序的使用建议

排行榜支持按 5 个维度排序，不同目的下侧重点不同：

| 排序维度 | 适用场景 |
|---------|---------|
| Composite Score | 综合选型，最常用 |
| WER | 有 ground truth，以准确率为首要标准 |
| Latency (TTFT) | 实时听写，延迟敏感 |
| Cost | 大规模部署，成本优先 |
| Confidence | 评估模型自信度，筛选需要人工复核的片段 |

### 5.4 无 Ground Truth 时的 Agreement Rank

当你没有正确文本时，平台会计算每个配置与其他配置的「分歧度」（平均 peer WER）。**分歧度最低的配置最接近「所有服务的共识」**，被认为可能最准确。这是一种代理指标，适合没有标注数据时的初步筛选。

### 5.5 读懂噪音测试结果

对比干净音频和噪音音频的结果时，重点看：

- **WER 变化幅度**：噪音对准确率的影响
- **TTFT 变化幅度**：噪音对服务端处理时间的影响（部分服务会在噪音下变慢）

实测数据（供参考）：

| 条件 | Deepgram TTFT | Whisper TTFT |
|------|--------------|--------------|
| 干净音频 | 3.33s | 2.88s |
| 噪音音频（~18dB SNR） | 3.03s（-9%） | 4.39s（**+52%**） |

Deepgram 在噪音下延迟几乎不变，Whisper 增加了 52%。

---

## 6. 添加新的 STT Provider

**无需写任何 Python 代码**，只需在项目根目录的 `providers.yaml` 文件末尾追加一段配置。

### 6.1 完整 YAML Schema

```yaml
providers:
  - name: your_provider_id      # 唯一 ID，CLI 的 --providers 参数中使用
    display_name: "Your Provider Name"
    api_key_env: YOUR_API_KEY   # 对应 .env 中的变量名
    cost_per_minute_usd: 0.005  # 默认费率（美元/分钟）
    model_version: v1           # 默认模型版本

    available_models:           # 可选：列出所有可选模型，供 UI 下拉选择
      - id: v1
        display_name: "V1 Standard"
        cost_per_minute_usd: 0.005
      - id: v2
        display_name: "V2 Enhanced"
        cost_per_minute_usd: 0.008
        body_fields:            # 可选：该模型需要不同的请求参数时覆盖
          model: "{{model_version}}"
          response_format: json  # 例如 v2 不支持 verbose_json

    request:
      method: POST
      url: "https://api.yourprovider.com/v1/transcribe"
      auth:
        type: bearer            # bearer | token | api-key
      body:
        type: multipart         # multipart（文件上传）| raw（直接发送音频字节）
        file_field: audio       # multipart 时：音频字段名
        fields:
          model: "{{model_version}}"
          response_format: verbose_json
      params:                   # 可选：URL 查询参数
        language: en

    response:
      transcript: text          # JSON 响应中转录文本的路径
      duration: duration        # 音频时长（秒），用于计算费用
      language: language        # 检测到的语言（可选）
      confidence: confidence    # 置信度（可选，没有则写 ~）
      words: ~                  # 词级数组（可选，没有则写 ~）
```

### 6.2 关键字段说明

**`auth.type`**

| 类型 | 生成的 Header |
|------|-------------|
| `bearer` | `Authorization: Bearer {key}` |
| `token` | `Authorization: Token {key}` |
| `api-key` | `api-key: {key}` |

**`body.type`**

| 类型 | 说明 | 适用场景 |
|------|------|---------|
| `multipart` | multipart/form-data，含 `file_field` 和 `fields` | OpenAI 系列 |
| `raw` | 直接发送音频字节，`Content-Type` 由 `content_type` 指定 | Deepgram |

**`response` 路径格式**

支持点号（`.`）和数组索引（`[0]`）：

```yaml
transcript: text                                          # 顶层字段
transcript: "results.channels[0].alternatives[0].transcript"  # 嵌套 + 数组
```

**`body_fields` 覆盖（model 级别）**

当某个模型不支持父级 `body.fields` 中的某个参数时，在该模型的 `available_models` 条目中加 `body_fields`，会完整替换父级 fields：

```yaml
available_models:
  - id: gpt-4o-transcribe
    body_fields:
      model: "{{model_version}}"
      response_format: json   # 覆盖父级的 verbose_json
```

### 6.3 完整示例（Rev AI）

```yaml
  - name: revai
    display_name: "Rev AI"
    api_key_env: REVAI_API_KEY
    cost_per_minute_usd: 0.035
    model_version: machine
    available_models:
      - id: machine
        display_name: "Machine (Standard)"
        cost_per_minute_usd: 0.035
      - id: fusion
        display_name: "Fusion (Enhanced)"
        cost_per_minute_usd: 0.045
    request:
      method: POST
      url: "https://api.rev.ai/speechtotext/v1/jobs"
      auth:
        type: bearer
      body:
        type: multipart
        file_field: media
        fields:
          model: "{{model_version}}"
    response:
      transcript: "monologues[0].elements[0].value"
      duration: duration_seconds
      confidence: ~
      words: ~
```

然后在 `.env` 中加入：

```
REVAI_API_KEY=your_key_here
```

重启 Streamlit，Rev AI 会自动出现在 Provider 列表中，并支持 Machine / Fusion 两个模型的多选对比。

---

## 7. 常见问题

**Q: 运行后提示 "OPENAI_API_KEY not set"**

检查项目根目录的 `.env` 文件是否存在且正确填写了 Key。文件名必须是 `.env`（注意前面的点）。

---

**Q: WER 显示 "N/A"**

WER 只有在填写了 Ground Truth 时才会计算。没有填写 Ground Truth 时，界面显示 Agreement Rank 替代。

---

**Q: 侧边栏提示 "provider_name: no model selected"**

勾选了某个 Provider 但把 `↳ Models` 多选框里所有模型都取消了。重新在多选框里选至少一个模型即可。

---

**Q: Composite Score 中 Cost weight 显示 "⚠️ invalid"**

WER 权重 + Latency 权重之和超过了 1.0。降低其中一个权重，Cost 权重会自动变为正数。

---

**Q: gpt-4o-transcribe 报 400 Bad Request**

这个模型不支持 `verbose_json` 格式。项目已通过 `body_fields` 覆盖自动处理，确保你使用的是最新版本的代码（`git pull`）。

---

**Q: AssemblyAI 不出现在 Provider 列表中**

AssemblyAI 需要额外安装：

```bash
poetry install --extras bonus
```

安装后勾选 "AssemblyAI" 并在 `.env` 填入 `ASSEMBLYAI_API_KEY`。

---

**Q: 想对比更多音频文件，一个一个跑太慢**

使用批量模式：

```bash
poetry run benchmark batch --manifest my_batch.csv --output results.json
```

详见第 4.2 节「批量测试」。

---

**Q: 如何保存网页界面的结果？**

展开页面底部的 "📄 Raw JSON result"，复制 JSON 内容保存为文件，后续可用 `benchmark leaderboard --input saved.json` 重新渲染。

---

*更多技术细节见 [development.md](./development.md)。*
