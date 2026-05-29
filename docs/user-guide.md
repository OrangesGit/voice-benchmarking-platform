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

### 1.1 API Keys

平台支持以下三个 STT 服务，使用前需申请对应的 API Key：

| Provider | 申请地址 | 费率 | 备注 |
|----------|---------|------|------|
| OpenAI Whisper | platform.openai.com | $0.006 / 分钟 | 无置信度返回 |
| Deepgram Nova-2 | console.deepgram.com | $0.0043 / 分钟 | 提供词级置信度 |
| AssemblyAI | www.assemblyai.com | $0.0037 / 分钟 | 需额外安装，见第 2 节 |

**推荐先申请 Deepgram（有免费额度）和 OpenAI，即可完成主要对比。**

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

浏览器自动打开 `http://localhost:8501`，出现如下界面：

```
左侧边栏                    主区域
─────────────────────────   ────────────────────────────────
⚙️ Configuration             1. Upload Audio
                             [文件上传] 或 [使用内置样本]
Providers
☑ OpenAI Whisper             2. Ground Truth (optional)
☑ Deepgram Nova-2            [输入预期转录文本]
☐ AssemblyAI

Scoring Weights              [▶ Run Benchmark]
WER (Accuracy)  ████░  0.50
Latency (TTFT)  ███░░  0.30
Cost (auto)            0.20
```

### 3.2 操作步骤

**Step 1 — 选择要对比的 Provider**

在左侧勾选想对比的 STT 服务。默认勾选 OpenAI Whisper 和 Deepgram Nova-2。

**Step 2 — 上传音频**

- **上传文件**：支持 WAV / MP3 / M4A / FLAC，建议时长 5–60 秒
- **使用内置样本**：勾选 "Use built-in sample"，使用项目自带的 8.5 秒 TTS 音频

**Step 3 — 填写 Ground Truth（可选）**

Ground Truth 是**你已知的正确转录文本**。

- **填写后**：平台计算 WER/CER，获得精确的准确率评分
- **不填写**：平台改用「提供商间一致性评分」（Agreement Rank），不需要人工校对

**Step 4 — 调整权重（可选）**

权重决定三个维度的重要程度：

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

**🏆 Leaderboard（排行榜卡片）**

```
🥇                          🥈
deepgram                    openai_whisper
0.4683                      0.4971
composite score             composite score

WER    0.533  CER    1.536   WER    0.644  CER    1.548
TTFT   3.33s  Conf.  0.901   TTFT   2.88s  Conf.  N/A
Cost   $0.000 Total  3.33s   Cost   $0.000 Total  2.88s

"Welcome to the voice bench…"   "Welcome to the voice bench…"
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

> 绿色高亮柱 = 该指标最优的 provider。

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

# 只测一个 provider
poetry run benchmark run \
  --audio my_audio.wav \
  --truth "预期文本" \
  --providers deepgram

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
| `--providers` | `openai_whisper,deepgram` | 逗号分隔的 provider 列表 |
| `--wer-weight` | 0.5 | WER 权重（0–1） |
| `--latency-weight` | 0.3 | 延迟权重（0–1） |
| `--cost-weight` | 0.2 | 成本权重（0–1） |
| `--output` | `table` | 输出格式：`table` 或 `json` |
| `--sort-by` | `composite` | 排序依据：`composite` / `wer` / `latency` / `cost` |

### 4.2 批量测试（多个文件）

**第一步：准备 CSV manifest 文件**

```csv
audio_file,ground_truth
samples/clip1.wav,Hello world this is a test
samples/clip2.wav,The quick brown fox jumps over the lazy dog
samples/clip3.wav,
```

> `ground_truth` 列可留空（表示无 GT 模式）。

**第二步：运行批量测试**

```bash
poetry run benchmark batch \
  --manifest batch.csv \
  --concurrency 5 \
  --output results.json
```

参数说明：

| 参数 | 默认值 | 说明 |
|------|-------|------|
| `--manifest` | 必填 | CSV 文件路径 |
| `--concurrency` | 5 | 同时处理的文件数 |
| `--output` | `results.json` | 结果保存路径 |

**第三步：查看排行榜**

```bash
# 按综合分排序
poetry run benchmark leaderboard --input results.json

# 按 WER 排序
poetry run benchmark leaderboard --input results.json --sort-by wer
```

### 4.3 CLI 输出示例

```
Run ID: f13c21af  Audio: sample.wav
Ground Truth: the weather today is partly cloudy…

                   STT Provider Benchmark Leaderboard
╭────┬────────────────┬───────┬───────┬───────┬────────┬────────┬──────────╮
│ R… │ Provider       │   WER │   CER │  TTFT │  Total │  Conf. │  Cost    │
├────┼────────────────┼───────┼───────┼───────┼────────┼────────┼──────────┤
│ 🥇 │ deepgram       │ 0.533 │ 1.536 │ 3.33s │  3.33s │  0.901 │ $0.00061 │
│ 🥈 │ openai_whisper │ 0.644 │ 1.548 │ 2.88s │  2.88s │    N/A │ $0.00085 │
╰────┴────────────────┴───────┴───────┴───────┴────────┴────────┴──────────╯
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

Provider 对自己转录结果的置信程度（0–1）。置信度低的词可用于后处理高亮"不确定词"提示用户核对。注意：OpenAI Whisper 不返回置信度。

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

### 5.3 无 Ground Truth 时的 Agreement Rank

当你没有正确文本时，平台会计算每个 provider 与其他 provider 的「分歧度」（平均 peer WER）。**分歧度最低的 provider 最接近「所有服务的共识」**，被认为可能最准确。

这是一种代理指标，精度低于真实 WER，但在没有标注数据时仍有参考价值。

### 5.4 读懂噪音测试结果

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

### 6.1 YAML 配置结构

```yaml
providers:
  - name: your_provider_id      # 唯一 ID，CLI 的 --providers 参数中使用
    display_name: "Your Provider Name"
    api_key_env: YOUR_API_KEY   # 对应 .env 中的变量名
    cost_per_minute_usd: 0.005  # 每分钟费率（美元）
    model_version: v1           # 传给 API 的模型版本号

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
      params:                   # 可选：URL 查询参数
        language: en

    response:
      transcript: text          # JSON 响应中转录文本的路径
      duration: duration        # 音频时长（秒），用于计算费用
      language: language        # 检测到的语言（可选）
      confidence: confidence    # 置信度（可选，没有则写 ~）
      words: ~                  # 词级数组（可选，没有则写 ~）
```

### 6.2 auth.type 说明

| 类型 | 生成的 Header |
|------|-------------|
| `bearer` | `Authorization: Bearer {key}` |
| `token` | `Authorization: Token {key}` |
| `api-key` | `api-key: {key}` |

### 6.3 response 路径格式

路径支持点号（`.`）和数组索引（`[0]`）：

```yaml
# 简单字段
transcript: text

# 嵌套字段
transcript: "results.channels[0].alternatives[0].transcript"
```

### 6.4 完整示例

以添加 **Rev AI** 为例，只需在 `providers.yaml` 追加：

```yaml
  - name: revai
    display_name: "Rev AI"
    api_key_env: REVAI_API_KEY
    cost_per_minute_usd: 0.035
    model_version: machine
    request:
      method: POST
      url: "https://api.rev.ai/speechtotext/v1/jobs"
      auth:
        type: bearer
      body:
        type: multipart
        file_field: media
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

重启 Streamlit 或 CLI，Rev AI 会自动出现在 Provider 列表中。

---

## 7. 常见问题

**Q: 运行后提示 "OPENAI_API_KEY not set"**

检查项目根目录的 `.env` 文件是否存在且正确填写了 Key。文件名必须是 `.env`（注意前面的点）。

---

**Q: 上传音频后报错 "Sample audio not found"**

使用内置样本时需要确保 `tests/fixtures/sample.wav` 存在。运行 `ls tests/fixtures/` 确认。若文件缺失，上传一个自己的音频文件即可。

---

**Q: WER 显示 "N/A"**

WER 只有在填写了 Ground Truth 时才会计算。没有填写 Ground Truth 时，界面会显示 Agreement Rank 替代。

---

**Q: Composite Score 中 Cost weight 显示 "⚠️ invalid"**

WER 权重 + Latency 权重之和超过了 1.0。降低其中一个权重，Cost 权重会自动变为正数。

---

**Q: AssemblyAI 不出现在 Provider 列表中**

AssemblyAI 需要额外安装：

```bash
poetry install --extras bonus
```

安装后勾选 "AssemblyAI" 并在 .env 填入 `ASSEMBLYAI_API_KEY`。

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
