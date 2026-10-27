# yaya-corpus —— 文字稿 → 可听语料

**文字稿进 → 可上架的中英双语音频出。** 校对、清洗、分段、离线合成（Kokoro-82M）、双语字幕、标签内嵌，一条流水线走完。稿子不出你的机器。

这是 [yaya-asr](../yaya-asr/) 的**镜像**：yaya-asr 把声音变成文字，本 skill 把文字变成能听的内容。

```bash
bash skills/yaya-corpus/run.sh extract 讲解稿.docx -o draft.txt   # 抽文本（带英文清洗）
bash skills/yaya-corpus/run.sh synth   out/plan.json              # → MP3 + LRC + SRT
bash skills/yaya-corpus/run.sh tags    out/mp3/ --album "专辑名"   # 写歌词/封面/ID3 标签
```

产物落在 `out/`（数据跟着 skill 走）：

```
out/<批次>/
├── 01-区域-关键词.mp3   24kHz 单声道，峰值归一 0.95
├── 01-区域-关键词.lrc   英文在上、中文在下，同一条时间戳
└── 01-区域-关键词.srt   同序
```

- **核心价值在校对**：原稿可以很糙，产出永远干净。合成前逐句修语法、改搭配；中文口播稿先翻成英文、确认后再合成。
- 字幕**英上中下共用时间戳**，是给「每日英语听力」这类工具用的硬要求。
- 内嵌 USLT + SYLT + APIC，本地播放全生效；**网易云「音乐网盘」不读内嵌标签**，云盘里需手动粘贴歌词。
- 依赖：`uv`（首次运行自建 `.venv`）。Kokoro 模型约 350MB，缺时自动下载到 `models/`。
- PDF 文本层被字体子集混淆（提取出来是乱码）时，改用 `run.sh decrypt <pdf>`，输出必定附可疑词清单，年份/专名需人工核。

完整流程见 [SKILL.md](SKILL.md)。反方向（音频 → 文字）用 [yaya-asr](../yaya-asr/)。
