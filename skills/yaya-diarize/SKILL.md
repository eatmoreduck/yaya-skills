---
name: yaya-diarize
description: Separates speakers in any audio entirely locally — outputs a who-spoke-when timeline (sherpa-onnx voiceprint clustering, no cloud, no transcript needed). Use when the user asks for "人声分离", "说话人分离", "谁在什么时候说话", "分轨", or wants speaker turns from an audio; also serves as the separation stage called by yaya-asr.
version: 0.1.0
metadata:
  openclaw:
    homepage: https://github.com/eatmoreduck/yaya-skills#yaya-diarize
    requires:
      anyBins:
        - uv
        - ffmpeg
---

# yaya-diarize —— 说话人分离（谁在何时说话）

**音频进 → 说话人时间线出。** 只认声音、不认文字：sherpa-onnx（pyannote 分割 + CAM++ 中文声纹）聚类出"谁在什么时候说话"。纯本地，免费、零登录。

被 [yaya-asr](../yaya-asr/) 作为分离阶段调用（**与 MLX 转写并行跑**：GPU 转写 ∥ CPU 分离，互不争抢）；也可以单独使用。

## 何时使用

- 用户给一段录音，想知道"谁在什么时候说话"（不需要文字稿）
- 用户说"人声分离""说话人分离""分个轨""分一下说话人"
- 想给音频做说话人标注，文字用别的引擎转

**不适用**：要"谁说了什么"（文字+说话人）→ 直接用 `yaya-asr`（它内部自动并行调用本 skill）；要 Space 干货笔记 → `yaya-xspace`。

## 快速开始

```bash
bash {baseDir}/run.sh recording.m4a
bash {baseDir}/run.sh meeting.mp4 --speakers 2 -o ./out
```

依赖说明：分离引擎和模型住在 `yaya-asr` 的共享环境里，**首次使用前先跑一次 yaya-asr**（自动建 venv + 下模型 ~35MB，无需 HF token）。

## 产物

```
<stem>.turns.json   {"num_speakers": N, "turns": [{"start", "end", "speaker"}]}
```

`speaker` 是按声纹聚类的编号（0..N-1），非真实姓名；不标注重叠语音（两人同时说归一人）。

## 参数

| 参数 | 说明 |
|---|---|
| `--speakers N` | **强制聚成 N 类**（引擎语义=确切人数，**不是上限**）。人少的录音务必填真实人数；不给默认 12 类；`-1` 按阈值自动聚类（长音频易过分割） |
| `-o DIR` | 输出目录（默认与输入同目录） |
| `--workdir DIR` | 缓存目录（默认 `.<stem>.diar`；yaya-asr 会传自己的缓存目录来共享） |

缓存带源文件指纹 + 聚类参数：换音频或换 `--speakers` 自动作废重算；坏缓存自愈。
