# yaya-xspace —— X Space → 干货笔记

一条命令搞定 **X Space 链接 → 音频下载 → 说话人分离 → 本地转写 → 观点蒸馏**。
音频全程不出本机，保护隐私；仅文字稿交由 LLM，端到端直接交付干货。

```
① 下载            ② 转写              ③ 说话人分离          ④ 蒸馏
yt-dlp      →   MLX Whisper      →   sherpa-onnx      →   智谱 glm
(uvx 临时跑)     (本地/词级时间戳)     (纯 ONNX/中文声纹)     (立场化提示词)
```

> 本 skill 是编排层：**下载复用 [yaya-xdl](../yaya-xdl/)，转写与说话人分离复用 [yaya-asr](../yaya-asr/)**，自身只负责串联与蒸馏。三者必须放在同一仓库的 `skills/` 下（靠相邻目录互相寻址，单独拷贝会失效）。

## 用法

在仓库根目录（或任意位置，`run.sh` 会自动寻址）：

```bash
bash skills/yaya-xspace/run.sh "https://x.com/i/spaces/<13位ID>"

# 指定说话人类数（推荐：X Space 人多，填实际活跃人数效果最好）
bash skills/yaya-xspace/run.sh "<url>" --speakers 12

# 换模型 / 只转写 / 保留音频 / 名单辅助识别
bash skills/yaya-xspace/run.sh "<url>" --llm-model glm-4.6
bash skills/yaya-xspace/run.sh "<url>" --transcript-only
bash skills/yaya-xspace/run.sh "<url>" --no-keep-audio   # 省磁盘：跑完删音频（默认保留）
bash skills/yaya-xspace/run.sh "<url>" --roster "浩哥,Tim,少白"

# 省时间：跳过双参数交叉校验（转写时间减半）
bash skills/yaya-xspace/run.sh "<url>" --no-crosscheck
```

完整参数见 `--help` 或 [SKILL.md](SKILL.md)。中间缓存齐全时重跑同一 Space，只会重新走一遍蒸馏，耗时仅数秒到一分钟。

## 产物

数据根目录 `YAYA_HOME`（默认 `~/Documents/yaya`），一场一个目录：

```
~/Documents/yaya/spaces/<space-id>/
├── audio.m4a               音频归档（默认保留——下载即归档）
├── distilled.md            ★ 最终干货（按说话人分组 + 关键名词总表）
├── audio.labeled.json      ★ 结构化转写 {speaker, start, end, text}
├── audio.dialog.txt        ★ 带说话人的对话稿
├── audio.dialog.srt          带说话人的字幕
├── audio.txt / audio.srt     纯文本稿 / 无说话人字幕
└── .audio.asr/               中间缓存（词级转写、分离结果、差异报告）
```

音频**默认保留**：X 不存归档，30 天后回放永久消失——下载即归档，重跑也不用再下 81MB。确要省磁盘加 `--no-keep-audio`。换机器或重装 skill，这个目录都不受影响。

## 双参数交叉校验（默认开启）

Whisper 有个已知毛病：一旦开启“参考上文”且陷入重复，就可能**静默跳过一段音频**（耳朵明明听得到，转写稿里凭空蒸发）。对策是用两组不同参数独立跑两遍，逐字 diff：

- **主版本**：带词级时间戳、开“参考上文”（供说话人对齐）
- **第二遍**：关“参考上文”、无词级（供基准核对）

差异报告在 `.audio.asr/asr.crosscheck.txt`（若“第二遍有、主版本无”，即为疑似漏段，务必人工核对）。实测一场 60 分钟中文 Space 两遍差异率约 4%，全部是语气词级碎片，无整段丢失。**代价是转写时间翻倍**，赶时间加 `--no-crosscheck`。

## 说话人分离怎么调

分离基于 sherpa-onnx（pyannote 分割 + CAM++ 中文声纹）。注意 `--speakers` 的**真实语义是“强制聚成 N 类”，不是上限**：

| 现象 | 调法 |
|---|---|
| 人多的 Space（论坛式，十来人发言） | `--speakers 12`（默认即可，近似实际活跃人数） |
| 人少的对话/访谈（2~4 人） | **务必显式指定真实人数**（如 `--speakers 2`），否则默认 12 会把两个人硬拆成七八个标签 |
| 拿不准人数 | `--speakers -1` 按阈值自动聚类（阈值默认 0.8，越大分出的人越少；长音频上容易过度分割出几十个说话人） |

说话人编号（A/B/C…）按出场先后顺序编排，并非真实姓名；可配合 `--roster` 名单交由 LLM 辅助对号，或自行对照。分离不标注重叠语音（两人抢话时归为一人）。

## ⚠️ 一场 Space 可能是多段

主持人只要断线重连，X 就会**新开一个 Space（生成新 ID）**，两段录音各自独立。**只拿到第二段，会得出“某内容不存在”的错误结论。**

常见的断段识别信号：
- 音频开头有大段静音，或有人开场就说“网络有问题”“你俩继续”“刚才讲到哪了”；
- 嘉宾口中转述“前面的大佬说了……”，但录音前文根本没有那些人的发言。

详见 [SKILL.md](SKILL.md) 的“陷阱”一节。

## 依赖

| 组件 | 用途 | 来源 |
|---|---|---|
| `yt-dlp` | 下载音频 | `uvx` 临时跑，零安装负担 |
| `ffmpeg` | 转码/16k | 需预装（`brew install ffmpeg`） |
| `mlx-whisper` | 本地转写 | yaya-asr 的 `.venv`（首次运行自动建） |
| `sherpa-onnx` | 说话人分离 | 同上（模型 ~35MB 自动下载，无需 HF token） |
| 智谱 LLM | 蒸馏 | `ZAI_CODING_CN_API_KEY`（环境变量或 `~/.bash_profile`） |

非 Apple Silicon 设备：转写引擎需换成 `sherpa-onnx` ASR 或 `faster-whisper`，见 yaya-asr 的 SKILL.md。

**模型**（首次运行自动下载，免 HF token）：转写模型 whisper-large-v3-turbo **~1.5GB**（存 `~/.cache/huggingface/`）+ 分离模型 ~33MB（存 yaya-asr 的 `models/`）。国内拉 HF 慢可先 `export HF_ENDPOINT=https://hf-mirror.com`。

## 已知边界

- **只能下开了录音、未过留存期的 Space**：主持人没开 "Record Space" → 无音频；超过 ~30 天 → 回放被删。私密 Space 需给 yt-dlp 加 cookie。
- **Whisper 偶有同音字错误**（如“弦外之音”转成“悬外之音”）：蒸馏层会依上下文修正，但精确搜索原文时请配合拼音或模糊搜索。
- **蒸馏默认 `max_tokens=8000`**：超长场若触及上限，`distilled.md` 顶部会出现截断警告——按提示分段重蒸馏，别把残缺笔记当全量。
