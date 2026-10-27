# yaya-skills 技术说明

> 面向想了解内部实现的人：架构与模块、数据布局、性能实测。
> 产品介绍与快速开始见 [README](README.md)（中）/[README.en](README.en.md)（英）。

---

## 1. 架构

### 1.1 五个 skill 与依赖

```
skills/
├── yaya-xdl/       原子能力：X Space 链接 → audio.m4a（yt-dlp，下载即归档）
├── yaya-asr/       原子能力：音频 → 带说话人文字（转写 + 编排分离并行）
├── yaya-diarize/   原子能力：音频 → 说话人时间线 turns.json
├── yaya-corpus/    原子能力：文字稿 → 可听语料（校验 → 清洗分段 → Kokoro TTS → MP3 + 双语字幕）
└── yaya-xspace/    编排层：调 xdl → 调 asr → 合并 → 蒸馏 → 出图
```

依赖单向：`yaya-xspace → yaya-xdl + yaya-asr`，`yaya-asr → yaya-diarize`。兄弟 skill 之间只通过各自的 `run.sh` 子进程调用、按相邻目录寻址，不共享代码。命名约定、新增 skill 三步骤见根 README。

`yaya-corpus` 是 `yaya-asr` 的**反向镜像**——asr 把声音变成文字，corpus 把文字变成声音。两者**代码零依赖**（各有独立 `.venv` 与模型目录），只是概念上互补；正因为互不认识，一条从 Space 到语料到笔记的链路才能随时拆开单独用。

### 1.2 流水线与并行设计

```
Space 链接
  │ yt-dlp（uvx 零安装）
  ▼
audio.m4a ──────────────────────────────┐
  │ ffmpeg → 16k wav                     │ 转写与分离唯一共享的输入
  ├─► yaya-asr：MLX Whisper 转写（GPU）  │   ——两者无模型级依赖，因此可并行
  │        └► 双参数交叉校验（GPU，接续） │
  └─► yaya-diarize：sherpa-onnx 分离（CPU，后台进程）
  ▼
词级时间戳 × 说话人时间线 → 按时间重叠归属 → 带说话人对话稿
  ▼
智谱 glm 蒸馏 → distilled.md → 渲染 distilled.png（Chrome headless）
```

- **GPU 转写 ∥ CPU 分离**：`asr.py` 转写一开始就 `Popen` 拉起 diarize，`transcribe()` 返回后 `wait()`。实测两边互不拖慢（MLX+ONNX 无资源争抢）。
- **唯一硬约束**：两个 MLX 进程绝不能并发（会崩），所以并行只发生在"MLX 转写 × ONNX 分离"之间。
- 合并逻辑住在 asr：每个词的时间戳落在哪个说话人区间，就归给谁。

### 1.3 各模块实现要点

**yaya-xdl（下载）**
- 先下临时名 `audio.dl.*`，完整后原子改名 `audio.m4a`——路径上永远不存在"半截文件冒充完整音频"。
- 中断残留自动清理；只认音视频扩展名（`_audio_files()`），转写产物/`.part` 永远不会被误当音频。
- 附带 `meta.json`（Space 标题/时长），供下游做笔记头。

**yaya-asr（转写 + 编排）**
- 转写引擎 `mlx-whisper` + `whisper-large-v3-turbo`（Apple MLX、GPU、词级时间戳）。
- **双参数交叉校验**（默认开）：`condition_on_previous_text` 开/关各独立跑一遍，`difflib` 逐字 diff，产出 `asr.crosscheck.txt`（"第二遍有、主版本无"=疑似漏段）。防的是 Whisper 已知的静默跳段缺陷。
- **缓存三层**（词级转写 / 第二遍转写 / 分离结果）均绑定**源文件内容指纹**（size+mtime_ns）与生成参数；写入用 tmp+rename 原子落盘；读取容错自愈（坏 JSON 自动删除重算）；旧格式缓存兼容放行。
- 幻觉过滤只删"整段几乎就是幻觉句"的内容，真实发言里提到"明镜/MING PAO"等词不会被连坐删除。

**yaya-diarize（说话人分离）**
- `sherpa-onnx`：pyannote segmentation 3.0（切分）+ 3D-Speaker CAM++ 中文声纹（提取），全程 ONNX、免 HF token。
- 聚类语义：`--speakers N` = **强制聚成 N 类（确切人数）**，不是上限；`-1` 按阈值自动聚类（长音频易过分割）。
- 缓存与 asr 共享（同一文件 `asr.diarization.json`，落在 `.audio.asr/`），拆分 skill 前的存量缓存零重算。

**yaya-xspace（编排 + 蒸馏 + 出图）**
- 蒸馏：智谱 `glm-5.3-flash`，`thinking` 显式 disabled（glm-5.x 默认开思考会吃光 token）；检查 `finish_reason=="length"`，截断时在笔记顶部打警告横幅；超时/空返回自动重试一次。
- 提示词契约："蒸馏≠缩写"——砍寒暄/口头语/重复，但金句原话、关键名词、每人核心主张、枚举清单一项不许省。
- 出图 `card.py`：解析 distilled.md（兼容 `- ` 与 `1. ` 两种列表格式）→ **五种风格 HTML**（`--style` 切换：`swiss` 国际主义【默认】/ `editorial` 杂志风 / `riso` 丝印潮风 / `midnight` 夜读 / `hand` 手绘白板；视觉语言参照 claude-motion-skill 案例预览；swiss 右上角用**红色声波弧**（三道同心弧+源点，纯 CSS radial-gradient）——白底实心红圆会被联想"日之丸"，声波弧既避嫌又正好呼应"把音频变成文字"的主题）→ **Chrome headless 两遍截图**（第一遍 `--dump-dom` 把内容高度写进 `<title>` 量高，第二遍按精确高度 `--screenshot` 出图，避免长图截断/留白）。HTML 中间产物只进 `.audio.asr/`，输出目录只多一张 PNG；找不到 Chrome 时警告跳过，不影响笔记；出图后日志提醒可换风格。
- 出图字体：`skills/yaya-xspace/fonts/` 内置两款开源手写体（站酷庆科黄油体=标题、站酷快乐体=正文，均 OFL 许可随附 `OFL.txt`，**仅 `hand` 风格使用**；其余风格用系统宋体/黑体，可读性更好），渲染时拷到 HTML 同目录相对引用，不依赖系统字体。卡图首行品牌 = `eatmoreduck 多吃鸭 · yaya-skills`。
- **说话人改名**：蒸馏后 `apply_speaker_names()` 从 distilled.md 解析 字母→真名 映射（复用 card.py 的 `_header_name()`，兼容 `A / Punk`、`A（Punk，…）`、`Punk（A）`、纯姓名等 LLM 惯用格式），把**对外文本产物**（dialog.txt / dialog.srt / distilled.md）里的字母标签换成真名——**对外永不出现 A/B/C/D**；映射落盘 `speaker_names.json`，供复查与幂等续跑。`labeled.json` / `turns.json` 是机器接口，**保持原始字母不变**。解析不出名字的字母保留原字母；改名失败只警告，绝不影响主流程。

**yaya-corpus（文字 → 可听语料）**

- **五段链路**：`extract`（docx/PDF/纯文本取文本）→ `decrypt`（PDF 文本层被字体子集混淆时先破密）→ 人工/LLM 校对翻译写 `plan.json` → `synth`（Kokoro 合成 MP3 + LRC/SRT）→ `tags`（USLT/SYLT 歌词 + APIC 封面 + 专辑/歌手写入 ID3v2.3）。
- **`plan.json` 是唯一契约**：`segments[].paragraphs[]` 的每一条就是**一条字幕的时间粒度**（1-2 句、≤150 字符）；带 `zh` 字段时自动产出同名 `.lrc`（英文在上、中文在下、同一时间戳）与 `.srt`。段前停顿可逐条指定，纯字符串默认 0.6s。
- **字幕时间轴按合成结果实测反推**，不按字数估算：合成一段就拿 `len(samples)/SR` 得到真实时长，累加停顿得到下一条起点——所以字幕和音频天然对齐，不会随语速漂移。
- **TTS 模型 Kokoro-82M**（ONNX）：`kokoro-v1.0.onnx`（310MB）+ `voices-v1.0.bin`（27MB），首次运行从 GitHub Release 下载到 `skills/yaya-corpus/models/kokoro/`，**同样先下临时名 `.dl` 再原子改名**（半截文件不会冒充模型）。24kHz 单声道，lameenc 编码，默认 96kbps；每段写盘前做峰值归一化，多段音量一致。
- **PDF 字体子集解密的原理**：这类 PDF 页面显示正常但复制/提取出来是 `!"#$"#%&`——生成器按**首次出现顺序**把第 k 个不同字符映射到 `0x21+k`。因此同一份文件内映射稳定，可以用词形（长度 + 重复模式）比对字典反推字母表。`crib.py` 做已知明文攻击（拿同文件内的干净标题当 crib），`final2.py` 生成多套候选映射、按解码后文本的语言模型分择优，`normalize.py` 逐类修补残留并输出 `*.suspect.txt`——**词典外词必须人工核**（专名属正常，年份/数字最容易错），脚本不替你下结论。只在确实检出密文时才套用修补表，干净文本走原样，避免 `The market,` 被误改成 `The marketo`。

### 1.4 数据布局

数据跟着 skill 走（删 skill 目录=删数据；`git pull` 不动未跟踪的 `out/`）：

```
skills/yaya-xspace/out/<space-id>/
├── audio.m4a              原始音频归档（默认保留——下载即归档）
├── meta.json              标题/时长
├── audio.labeled.json     结构化转写 {speaker, start, end, text}（程序接口，说话人=字母）
├── audio.dialog.txt       带说话人对话稿（真名：…）
├── audio.dialog.srt       带说话人字幕（[真名]，可对回音频）
├── audio.txt / audio.srt  纯文本稿 / 无说话人字幕
├── audio.turns.json       说话人时间线（机器接口，说话人=字母）
├── distilled.md           蒸馏笔记（文本母本，说话人=真名）
├── distilled.png          分享图（可直接发布）
├── speaker_names.json     字母→真名 映射（对外文本已替换；机器接口文件不动）
└── .audio.asr/            缓存（不进 git）：
    ├── asr.words.json       词级转写原文（最原始层）
    ├── asr.alt.json         第二遍独立转写
    ├── asr.diarization.json 分离原始结果
    ├── asr.crosscheck.txt   双转写差异报告
    └── distilled.card.html  出图 HTML（中间产物）
```

**对外文本 vs 机器接口的分界**（改名后的三条对外文本用真名）：`dialog.txt` / `dialog.srt` / `distilled.md` 中的说话人一律真名——由 `apply_speaker_names()` 从 distilled.md 解析映射后统一替换，映射存 `speaker_names.json`；`labeled.json` / `turns.json` 是程序消费的机器接口，**保持原始字母**（下游按字母索引，不许改）。解析不出真名的字母（LLM 没写名字）保留原字母，宁缺毋改。

**原始对话稿永不删除**（重跑只跳过不重算；只有 `--no-keep-audio` 删音频本身）。以上任何一层都可用于后续分析：词级 JSON 做精细对齐，labeled.json 做程序统计，dialog 文本做人读分析。

### 1.5 模型

| 模型 | 用途 | 体积 | 位置 | 来源 |
|---|---|---|---|---|
| whisper-large-v3-turbo（MLX 版） | 语音转写 | ~1.5GB | `~/.cache/huggingface/`（全局共享） | HuggingFace |
| sherpa-onnx-pyannote-segmentation-3-0 | 说话人切分 | 5.7MB | `skills/yaya-asr/models/` | GitHub Releases |
| 3D-Speaker CAM++ 中文声纹 | 声纹提取 | 27MB | 同上 | GitHub Releases |
| Kokoro-82M（`kokoro-v1.0.onnx` + `voices-v1.0.bin`） | 文字转语音（yaya-corpus） | 337MB | `skills/yaya-corpus/models/kokoro/` | GitHub Releases |

全部**免 HF token**，首次运行自动下载。国内网络可 `export HF_ENDPOINT=https://hf-mirror.com`。Kokoro 与其余模型分属两个 venv，互不影响。

---

## 2. 性能实测

**环境**：Apple M1 Pro（10 核）/ macOS。**样本**：真实中文 Space，119 分钟 / 84.9MB / 10 位说话人 / 对话稿 29,930 字。

### 2.1 每阶段耗时（完整首跑）

| 阶段 | 耗时 | 吞吐 | 说明 |
|---|---|---|---|
| 元数据探测 | 6s | — | `yt-dlp --simulate` |
| 下载 | 6:15 | ~227KB/s | 单连接，X CDN 限速 |
| ffmpeg 转码 16k | 6s | — | |
| 转写（主版本） | 9:58 | 11.9× 实时 | GPU（MLX），3856 段词级时间戳 |
| 交叉校验 | 5:10 | 23.0× 实时 | GPU，接在转写后；与分离并行执行 |
| 说话人分离 | **21:39** | 5.5× 实时 | CPU（ONNX）——**并行段的关键路径** |
| 合并对话稿 | 3s | — | GPU 路径合计 15:08 < 分离，完全被掩盖 |
| LLM 蒸馏 | 60s | — | glm-5.3-flash |
| 分享图 | 5~6s | — | Chrome headless 两遍截图 |
| **总计** | **≈29.3 分钟** | **0.25× 音频时长** | |

### 2.2 并行收益与瓶颈

- 并行段墙钟 = `max(转写+交叉校验 15:08, 分离 21:39)` = 21:39；同规模**串行**约 41 分钟（0.36×），并行省约 12 分钟。
- 当前唯一瓶颈是**说话人分离**（占全程 ~74%）。已知可再提速：声纹提取 `num_threads=4`（2 分钟样本实测 2.0× 且输出一致，8 线程反而退化）——按需启用，预计总时长降到约 19 分钟（0.16×）。
- 下载 ~6 分钟是次要项（单连接限速），换多连接下载器可省 3-4 分钟。

### 2.3 缓存热路径

- 全缓存命中重跑（只重新蒸馏+出图）：**≈1.5 分钟**。
- 换蒸馏模型/加名单重跑：同上，不触碰转写与分离。

### 2.4 复现

```bash
bash skills/yaya-xspace/run.sh "https://x.com/i/spaces/<13位ID>"
# 各阶段耗时直接读运行日志的 [HH:MM:SS] 前缀
```

---

## 3. 已知边界（技术侧）

- 说话人分离不标注重叠语音（两人同说归一人）；说话人编号按出场顺序，非真实姓名。
- 中文 ASR 有同音字错误（"弦外之音"→"悬外之音"），蒸馏层做上下文纠正，但精确搜索建议配合拼音/模糊匹配。
- 非 Apple Silicon：转写引擎需换 `sherpa-onnx` ASR 或 `faster-whisper`（分离部分本身已全平台）。
