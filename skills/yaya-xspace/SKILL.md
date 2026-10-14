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

## 人名识别：字母 → 真名的两层局限

蒸馏后 `apply_speaker_names()` 把对外产物的字母标签换成真名（映射从蒸馏稿署名解析）。但别指望全自动：

1. **ASR 同音误听会污染整个映射**（真实案例）：主播 ID「魂蓝」被整场听写成「黄蓝」，转写稿里出现 133 次「黄蓝姐」——稿内证据再多也是错的，两个 LLM 独立蒸馏给出了相反的名字。**唯一可靠解法是名单**：跑之前去 Space 页面抄一眼主讲/嘉宾账号名，跑时传入：
   ```bash
   bash run.sh "<space-url>" --roster "主持人：Punk；主讲嘉宾：魂蓝姐"
   ```
2. **LLM 署名格式会漂移**（观测过的四种：`B / 魂蓝姐`、`B：魂蓝姐`、`说话人 B / 魂蓝姐`、`说话人 G·小A`）。SYSTEM_PROMPT 已锁定 `**X / 名字（…）**` 格式，distill.py 落盘前还有 `_normalize_speaker_headers()` 归一兜底；仍解析不出的字母保留原字母（宁可留字母，不改坏标题）。

## 蒸馏兜底（1301 内容审核）

智谱对转写稿做内容安全审核（错误码 1301，情趣/医疗等题材易触发），且**同输入随机拦放**——重试经常能过。拦截时 `distill.py` 会报错并给出选项，**不要自动换通道**，提示用户三选一：

- **原样重跑**：缓存命中，只花一次 LLM 调用（首推，多半就过了）
- **`--llm-model` 换智谱其他模型**：同审核体系，不保证过
- **改用本机其他 LLM CLI**（用户拍板用哪个，按该 CLI 的调用格式来）。转写产物完好，重蒸馏要点：
  1. prompt 组装照抄 `distill.py`：`SYSTEM_PROMPT` + 标题 + roster + `render(segs, with_time=True)` 的转写稿
  2. 清洗输出：LLM 可能输出多份/代码围栏/板块重复——取**最后一份**完整蒸馏（以「一句话总结」起、「可行动项」终）
  3. 署名归一（复用 `distill._normalize_speaker_headers`）后落盘 `distilled.md`（header 格式照抄 `main()`），再调 `apply_speaker_names(outdir, md)` + `card.render(md, workdir=…, style=…)` 收尾
  4. 对话稿若已被旧映射改过名（行首不再是字母），先从 `labeled.json` 重渲染字母版（格式照抄 `asr.py` 的 dialog.txt/srt）再套新映射

## 必读边界

1. **只能下开了录音、未过留存期的 Space**。主持人没开 "Record Space" → 无音频；超过 30 天 → 被删。
2. **私密/受限 Space 需要 cookie**：下载由 yaya-xdl 负责，目前需手动给它的 yt-dlp 加 `--cookies-from-browser chrome`。
3. **X 没有 Space 归档/搜索**——回放 30 天即删且搜不到。**下载即归档**，否则那段语音永久消失。

## 环境要求

依赖 `uv` + `ffmpeg` + 智谱 key（`ZAI_CODING_CN_API_KEY`）。转写环境由 `yaya-asr` 自动准备，下载环境由 `yaya-xdl` 负责（`uvx yt-dlp` 零安装）。
