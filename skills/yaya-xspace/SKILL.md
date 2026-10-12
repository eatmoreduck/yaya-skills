---
name: yaya-xspace
description: Turns an X (Twitter) Space into a distilled Chinese notes file — orchestrates yaya-xdl (download) and yaya-asr (transcribe with speaker labels), then distills while keeping every quote, keyword and enumeration intact. Use when the user shares an x.com/i/spaces link or Space audio and asks to "转写 Space", "Space 蒸馏", "把这场 Space 总结成干货", or wants who-said-what notes from a Space.
version: 0.1.0
metadata:
  openclaw:
    homepage: https://github.com/eatmoreduck/yaya-skills#yaya-xspace
    requires:
      anyBins:
        - uv
        - ffmpeg
---

# yaya-xspace —— X Space → 干货笔记

**Space 链接（或本地音频）→ 带说话人的对话稿 → 立场化干货笔记。**

本 skill 是**编排层**，依赖两个兄弟 skill：**[yaya-xdl](../yaya-xdl/)**（下载 Space 音频）、
**[yaya-asr](../yaya-asr/)**（转写 + 说话人分离）。它自己只做：把两者串起来 + LLM 蒸馏。

## 何时使用

- 用户发来 `x.com/i/spaces/...` 链接或 13 位 Space ID
- 用户已下好 Space 音频文件，想转写 + 提炼
- 用户说"Space 蒸馏""转写这场""提炼干货""谁说了什么"

**不适用**：普通会议/访谈录音（用 `yaya-asr` 就够，不需要蒸馏）；实时直播中的 Space（只支持已结束的回放）。

## 快速开始

```bash
bash {baseDir}/run.sh "https://x.com/i/spaces/<id>"
bash {baseDir}/run.sh "/path/to/space.m4a" --speakers 12
```

## 参数

| 参数 | 说明 |
|---|---|
| `--speakers N` | 推荐显式给**实际活跃说话人数**（强制聚类类数，不是上限：11 人场给 12；人少的录音务必给真实人数）。`-1` 自动聚类在长音频上易过分割 |
| `--no-keep-audio` | 跑完删除音频。**默认保留**（下载即归档，重跑不用再下） |
| `--no-card` | 跳过分享图（distilled.png）。默认出图，依赖本机 Chrome，失败只警告不影响笔记 |
| `--style S` | 分享图风格：`swiss` 国际风（**默认**，白底黑体红方块） / `editorial` 杂志风 / `riso` 丝印潮风 / `midnight` 夜读 / `hand` 手绘白板。出图后日志会提醒可随时换 |
| `--llm-model M` | 蒸馏模型，默认 `glm-5.3-flash` |
| `--transcript-only` | 只转写，不蒸馏 |
| `--no-crosscheck` | 跳过双参数交叉校验（省一半时间） |

## 产物

产物就落在 skill 自己的 `out/`（数据跟 skill 走），一场一个目录，音频默认保留：

```
skills/yaya-xspace/out/<space-id>/
├── audio.m4a                 音频归档（下载即归档；--no-keep-audio 才删）
├── distilled.md              ★ 最终干货（按说话人分组 + 关键名词总表）
├── distilled.png             ★ 分享图（笔记自动渲染成一张可直接发推的图）
├── <audio>.labeled.json      ★ 结构化转写（机器接口，说话人=字母）
├── <audio>.dialog.txt        ★ 带说话人的对话稿（真名：文本）
├── <audio>.dialog.srt          带说话人的字幕（[真名]）
└── speaker_names.json          字母→真名 映射（对外文本用真名；labeled/turns 保持字母）
```

## ⚠️ 陷阱：一场 Space 可能是多段（真实案例）

**这是本 skill 最容易踩的坑，代价极高——你会拿到"半场"而不自知。**

主持人**断线重连**会新开一个 Space（**新 ID**），两段各自独立、各有各的链接。真实案例：一场 152 分钟的 Space 被拆成两段（91 分钟 + 60 分钟），只拿到第二段会得出"某内容不存在"的**错误结论**。

**识别信号**（录音开头出现这些，说明它是"第二段"）：
- 开头有大段静音（重连空档）
- 有人说"网络有问题""大家都断了""你俩继续""我们刚才讲到哪"
- 有人转述"前面的大佬说了…"但那些人的发言不在录音里

**应对**：发现信号时**主动问用户"这场是不是还有另一段"**，别默认拿到的是全部。

## 必读边界

1. **只能下开了录音、未过留存期的 Space**。主持人没开 "Record Space" → 无音频；超过 30 天 → 被删。
2. **私密/受限 Space 需要 cookie**：下载由 yaya-xdl 负责，目前需手动给它的 yt-dlp 加 `--cookies-from-browser chrome`。
3. **X 没有 Space 归档/搜索**——回放 30 天即删且搜不到。**下载即归档**，否则那段语音永久消失。

## 环境要求

依赖 `uv` + `ffmpeg` + 智谱 key（`ZAI_CODING_CN_API_KEY`）。转写环境由 `yaya-asr` 自动准备，下载环境由 `yaya-xdl` 负责（`uvx yt-dlp` 零安装）。
