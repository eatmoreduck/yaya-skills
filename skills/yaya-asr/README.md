# yaya-asr —— 本地语音转文字（带说话人）

任意音频/视频 → 带说话人的文字稿。**纯本地跑：音频不出机器，免费、零登录、不需要任何云端账号。**

这是 yaya 系列的**原子能力**：不认识任何业务概念（不知道什么是 Space、会议、播客），只做一件事——音频进，带说话人的文字出。要"X Space 链接 → 干货笔记"的完整流水线，用 [yaya-xspace](../yaya-xspace/)（它内部调用本 skill）。

**内部是流水线**：转写（MLX/GPU）一开始就后台拉起说话人分离（[yaya-diarize](../yaya-diarize/)，CPU），两者并行执行——实测互不拖慢，长音频总耗时接近两者中较慢的一个。分离的依赖和模型共享 `yaya-asr` 的环境，无需额外安装。

## 快速开始

```bash
bash skills/yaya-asr/run.sh ~/Downloads/recording.m4a
bash skills/yaya-asr/run.sh meeting.mp4 --speakers 2
bash skills/yaya-asr/run.sh talk.wav -o ./out
```

首次运行自动建独立 venv，并下载两个模型（都免 HF token，之后重跑不重复下载）：

| 模型 | 用途 | 体积 | 位置 |
|---|---|---|---|
| whisper-large-v3-turbo（MLX 版） | 转写 | **~1.5GB** | `~/.cache/huggingface/`（全局共享，其他 MLX 工具也能复用） |
| pyannote 分割 + CAM++ 中文声纹 | 说话人分离 | ~33MB | 本 skill `models/`（已 gitignore） |

> 国内网络拉 HuggingFace 慢的话，先 `export HF_ENDPOINT=https://hf-mirror.com` 再跑。

要求 `uv` + `ffmpeg` 预装，Apple Silicon（转写走 MLX；其他平台需换引擎，见 SKILL.md）。

## 输出（标准格式，可被其它工具消费）

| 文件 | 内容 |
|---|---|
| `<name>.txt` / `<name>.srt` | 纯文本稿 / 不带说话人的字幕 |
| `<name>.dialog.txt` | ★ 带说话人的对话稿（`A：文本`） |
| `<name>.dialog.srt` | ★ 带说话人的字幕 |
| `<name>.labeled.json` | ★ 结构化结果 `{speaker, start, end, text}`，稳定机器接口 |

## 用前须知

- `--speakers N` 的**真实语义是"强制聚成 N 类"，不是上限**：素材人多就填实际活跃说话人数；人少的录音（2~4 人）务必填真实人数，默认 12 会把两个人拆成七八个标签。详见 [SKILL.md](SKILL.md)。
- 默认开启**双参数交叉校验**（换参数独立转两遍逐字 diff，防 Whisper 静默跳段），转写时间翻倍；赶时间加 `--no-crosscheck`。
- 说话人编号 A/B/C 按出场顺序，非真实姓名；不标注重叠语音。
- 缓存（词级转写、分离结果）带源文件指纹：同名文件换了内容会自动重算，写一半崩溃的坏缓存会自愈，不用手删。
