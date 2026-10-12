---
name: yaya-xdl
description: Downloads X (Twitter) Space audio to a local m4a file — archive-first downloader. Use when the user shares an x.com/i/spaces link and asks to "下载 Space", "存个 Space", "归档 Space", "把录音存下来", or wants just the audio without transcription; also serves as the download step of yaya-xspace.
version: 0.1.0
metadata:
  openclaw:
    homepage: https://github.com/eatmoreduck/yaya-skills#yaya-xdl
    requires:
      anyBins:
        - uv
---

# yaya-xdl —— X Space 音频下载（下载即归档）

**Space 链接 → 本地 audio.m4a。** 只管下载这一件事；转写找 [yaya-asr](../yaya-asr/)，蒸馏找 [yaya-xspace](../yaya-xspace/)。

X 不提供 Space 归档或搜索，回放 30 天即删——**下载即归档**，否则那段语音永久消失。这个 skill 的存在本身就是这条原则。

## 何时使用

- 用户发来 `x.com/i/spaces/...` 链接，只想把音频存下来（不转写、不蒸馏）
- 用户说"下载这个 Space""把录音存档""先存下来再说"
- 想只归档：一个链接一条命令，音频落在本地就完事

**不适用**：要文字稿或干货笔记 → 直接用 `yaya-xspace`（它会自动调用本 skill 下载）；手里已是音频文件 → 直接用 `yaya-asr`。

## 快速开始

```bash
bash {baseDir}/run.sh "https://x.com/i/spaces/<13位ID>"
bash {baseDir}/run.sh "<url>" -o /path/to/archive    # 指定输出目录（默认 skill 自己的 out/<space-id>/）
```

## 产物

默认归档到 skill 自己的 `out/`，一场一个目录：

```
skills/yaya-xdl/out/<space-id>/
├── audio.m4a   音频（先下临时名、完整后原子改名——绝无半截文件冒充全量）
└── meta.json   标题/时长等元数据（yaya-xspace 会读它做笔记头）
```

## 必读边界

1. **只能下开了录音、未过留存期的 Space**：主持人没开 "Record Space" → 无音频；超过 ~30 天 → 回放被删。
2. **私密 Space 需要 cookie**：目前需手动给脚本内的 yt-dlp 加 `--cookies-from-browser chrome`。
3. 中断残留的 `.part` 会被自动清理，永远不会被误当完整音频。
