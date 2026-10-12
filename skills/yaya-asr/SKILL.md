---
name: yaya-asr
description: Transcribes any audio or video file into speaker-labeled text entirely on the local machine — no cloud, no login, no API key. Outputs plain text, SRT subtitles, an A/B dialogue transcript, and structured JSON. Use when the user shares a recording (meeting, interview, podcast, lecture, voice memo) and wants a transcript, subtitles, or "谁说了什么"; or says "转写", "语音转文字", "会议纪要", "录音转文字", "做字幕", "who said what". Apple Silicon required for the fast MLX path.
version: 0.1.0
metadata:
  openclaw:
    homepage: https://github.com/eatmoreduck/yaya-skills#yaya-asr
    requires:
      anyBins:
        - uv
        - ffmpeg
---

# yaya-asr —— 本地语音转文字

**任意音频/视频 → 带说话人的文字稿。** 纯本地跑，音频不出你的机器；免费、零登录、不需要任何云端账号。

这是整个 yaya 系列的**原子能力**。它不认识任何业务概念（不知道什么是 Space、会议、播客）——只做一件事：音频进，文字出。

内部是**流水线**：转写（MLX/GPU）一开始就以后台进程拉起说话人分离（[yaya-diarize](../yaya-diarize/)，CPU），两者并行执行、互不争抢——分离已拆分为兄弟 skill，本 skill 只负责调用与合并。

## 何时使用

- 用户给你一个**录音/录像文件**（会议、访谈、播客、课程、语音备忘、手机录音）
- 用户要**字幕**（.srt）
- 用户问"**谁说了什么**"（需要说话人区分）
- 用户说"转写""录音转文字""会议纪要""做字幕"

**不适用**：想从 X Space 链接直接拿干货笔记 → 用 `yaya-xspace`（它会调用本 skill）；实时录音转写（本工具处理已录好的文件）。

## 快速开始

```bash
bash {baseDir}/run.sh "/path/to/recording.m4a"
bash {baseDir}/run.sh "/path/to/meeting.mp4" --speakers 2
bash {baseDir}/run.sh "/path/to/talk.wav" -o ./output
```

首次运行自动建独立 venv、下两个模型（都免 HF token）：转写模型 whisper-large-v3-turbo（**~1.5GB**，存 `~/.cache/huggingface/` 全局共享）+ 分离模型（~33MB，存本 skill `models/`）。国内拉 HF 慢可先 `export HF_ENDPOINT=https://hf-mirror.com`。

## 参数

| 参数 | 说明 |
|---|---|
| `--speakers N` | **强制聚成 N 类**（引擎语义=确切人数，**不是上限**）。素材人多就填实际活跃说话人数；人少的录音务必填真实人数；不给默认 12 类；`-1` 按阈值自动聚类（长音频易过分割） |
| `-o DIR` | 输出目录（默认与输入同目录） |
| `--no-diarize` | 只转写不分离（快，但没有 A/B 标签） |
| `--no-crosscheck` | 跳过双参数交叉校验（省一半时间） |
| `--keep-wav` | 保留中间 16k wav |

## 输出（标准格式，可被其它工具消费）

| 文件 | 内容 |
|---|---|
| `<name>.txt` | 纯文本 |
| `<name>.srt` | 字幕（不带说话人） |
| **`<name>.dialog.txt`** | ★ 带说话人的对话稿：`A：文本` |
| **`<name>.dialog.srt`** | ★ 带说话人的字幕 |
| **`<name>.labeled.json`** | ★ 结构化结果（`{speaker, start, text}`），供程序调用 |

> 下游工具请读 **`.labeled.json`**——这是稳定的机器接口，格式不会变。

## 环境要求

| 组件 | 用途 | 来源 |
|---|---|---|
| `uv` | 建 venv、下 Python | 需预装 |
| `ffmpeg` | 音频/视频转码 | 需预装（系统不自带） |
| `mlx-whisper` | 本地转写（**Apple Silicon 专用**） | 脚本自动装 |
| `sherpa-onnx` | 说话人分离 | 脚本自动装 |

> **非 Apple Silicon**：转写引擎需换成 `sherpa-onnx` 自带 ASR 或 `faster-whisper`（两者都有 Win/Linux 轮子）。分离部分（sherpa-onnx）本身已全平台。

## 上游与下游

- **被谁调用**：`yaya-xspace`（编排：下载 → 调本 skill → 蒸馏）
- **依赖**：`yaya-diarize`（说话人分离，转写时以后台进程并行调用，共享 venv 与模型）
- **不依赖任何下载/业务 skill**（单向依赖：上层依赖下层）

## 已知边界

1. **说话人编号是临时的**（A/B/C 按出场顺序），非真实姓名。
2. **不标注重叠语音**（两人同时说时归给一人）。
3. **不含下载功能**——只处理你已有的文件。
4. Whisper 有**同音字错误**（"弦外之音"可能被转成"悬外之音"）。搜索关键词时请配合模糊/拼音搜索，别只做精确匹配。
