# yaya-skills

[English](README.en.md) | 简体中文

![yaya-skills](assets/banner.png)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/eatmoreduck/yaya-skills?style=social)](https://github.com/eatmoreduck/yaya-skills)
[![Works with](https://img.shields.io/badge/Works%20with-Claude%20Code%20%7C%20Codex%20%7C%20Cursor%20%7C%20Windsurf%20%7C%20ZCode-blueviolet)](#安装)
![Platform](https://img.shields.io/badge/macOS-Apple%20Silicon-black?logo=apple)
![Local](https://img.shields.io/badge/%E9%9F%B3%E9%A2%91-%E4%B8%8D%E5%87%BA%E6%9C%AC%E6%9C%BA-success)

> **首期主打：X Space 录音转文字。** 给没时间听、或忘了听的人——一条链接，一场两小时的 Space 变成按说话人分组、金句原话全保留的中文干货笔记。

**yaya-skills 的核心逻辑是一条创作流流水线**：素材进来，作品出去。第一波的素材入口是 X Space（[yaya-xspace](skills/yaya-xspace/)），背后由下载 / 转写 / 分离三个原子 skill 支撑；后续会增加写作、发布等更多 skill，逐步补完整条创作链。音频全程不出本机。

## 快速开始（主打场景）

```bash
bash skills/yaya-xspace/run.sh "https://x.com/i/spaces/<13位ID>"
# → ~/Documents/yaya/spaces/<id>/distilled.md
```

首次运行自动下载模型；两小时的场约 30 分钟出稿（GPU 转写与说话人分离并行跑）。

## 定位

![yaya-skills 流水线](assets/architecture.png)

**分层原则：上层依赖下层，依赖单向。**

- **原子能力互不依赖**：`yaya-xdl` 只管下载——Space 链接进，audio.m4a 出（下载即归档）；`yaya-asr` 只管转写——音频进，带说话人的文字出；`yaya-diarize` 只管分离——音频进，"谁在何时说话"的时间线出。都不带业务概念。
- **`yaya-asr` 内部是流水线**：转写（MLX/GPU）一开始就后台拉起分离（yaya-diarize，CPU），两者**并行执行**，互不争抢。
- **`yaya-xspace` 是场景编排**：把 xdl 和 asr 串起来，再加自己的蒸馏，产出干货笔记。每个环节只通过兄弟 skill 的 `run.sh` 调用，不重复实现。

这样拆的好处很直接：只想存音频的用 `yaya-xdl`；只想分说话人的用 `yaya-diarize`；要文字稿的用 `yaya-asr`；只有 X Space 一条龙才需要 `yaya-xspace`。

## 为什么做这个

**好内容先得存住，才谈得上加工。** X 不提供 Space 归档或搜索，回放 30 天即删——**下载即归档**，否则那段语音永久消失。

本地跑还有个好处：免费、零登录、不需要任何云端账号。

## 已收录

**主打（场景 skill）**

| Skill | 说明 |
|---|---|
| [yaya-xspace](skills/yaya-xspace/) | X Space 链接 → 中文干货笔记（金句原话 / 关键名词 / 枚举清单全保留） |

**支撑（原子 skill，组成上面的流水线，也可单独用）**

| Skill | 说明 |
|---|---|
| [yaya-xdl](skills/yaya-xdl/) | X Space 链接 → audio.m4a（下载即归档） |
| [yaya-asr](skills/yaya-asr/) | 任意音频/视频 → 带说话人的文字（转写∥分离自动并行） |
| [yaya-diarize](skills/yaya-diarize/) | 音频 → 说话人时间线 turns.json（谁在何时说话） |

## Roadmap

- ✅ **第一波**：X Space → 干货笔记（上面这条流水线）
- 🔜 **后续**：写作、发布等更多创作流 skill——素材进来，作品出去

## 模型（首次运行自动下载，无需手动准备）

| 模型 | 用途 | 体积 | 存放位置 | 下载源 |
|---|---|---|---|---|
| whisper-large-v3-turbo（MLX 版） | 语音转写 | **~1.5GB** | `~/.cache/huggingface/`（全局共享） | HuggingFace |
| pyannote 分割 + CAM++ 中文声纹 | 说话人分离 | ~33MB | `skills/yaya-asr/models/`（已 gitignore） | GitHub Releases |

- 两个模型都**免 HF token**，首次跑对应 skill 时自动下载，之后重跑不重复下载。
- 下载 Whisper 需要能访问 HuggingFace；网络不稳可提前设镜像：`export HF_ENDPOINT=https://hf-mirror.com`。
- 磁盘敏感的话注意：大头是那 1.5GB 的转写模型，分离模型只有 33MB。

## 数据放哪（产物与归档）

**数据跟着 skill 走**：产物、音频归档、缓存全部落在 skill 自己的 `out/` 里，删 skill 目录 = 删数据，`git pull` 更新也不影响（out/ 已 gitignore）。

```
skills/yaya-xspace/out/<space-id>/   ← 一场 Space 一个目录，一切都在里面
├── audio.m4a                        音频归档（默认保留——下载即归档）
├── distilled.md                     ★ 干货笔记
├── audio.labeled.json / audio.dialog.txt / …   转写产物
└── .audio.asr/                      中间缓存（删掉只损失重算时间）
```

- 想搬到别处（如插件市场安装到版本化缓存目录）：`export YAYA_HOME=/some/where`，数据就落 `$YAYA_HOME/spaces/`。
- 删一场 = 删一个目录；不想要音频加 `--no-keep-audio`。
- ⚠️ `out/` 是你的私人数据（笔记+音频），已在 `.gitignore` 里——永远不会被 git 提交上去。

## 安装

skill 是通用的 Markdown+脚本格式（Agent Skills 规范），**不绑定任何一家 Agent**——Claude Code、Codex、Cursor、Windsurf、ZCode 等所有支持该规范的 Agent 都能装能用。

```bash
# 方式一：插件市场（可增量更新）
/plugin marketplace add eatmoreduck/yaya-skills
/plugin install yaya-skills@yaya-skills

# 方式二：skills CLI
npx skills add eatmoreduck/yaya-skills

# 方式三：手动（项目级）
# 把需要的 skills/<name>/ 目录复制或软链到 <项目>/.agents/skills/
# ⚠️ yaya-xspace 依赖 yaya-xdl 和 yaya-asr；yaya-asr 依赖 yaya-diarize——单独复制会失效
```

## 设计原则

1. **本地优先**：能本地跑的绝不上云。音频不出机器（转写全在本地，只有提取后的文本发给 LLM）。
2. **砍废话，不砍信息**：提炼是“去冗余”，不是“缩写”。金句、关键名词、枚举清单必须完整保留。
3. **原子能力与业务解耦**：`yaya-asr` 不知道 Space 是什么；场景 skill 只管补齐自己独有的那一段。
4. **诚实标注边界**：每个 skill 明确写出它做不到什么，不假装能处理所有情况。

## 目录约定

```
yaya-skills/
├── .claude-plugin/
│   └── marketplace.json     ★ 声明本仓库包含哪些 skill
├── skills/
│   ├── yaya-asr/            原子能力（无依赖）
│   │   ├── SKILL.md
│   │   ├── README.md
│   │   ├── run.sh
│   │   ├── scripts/asr.py
│   │   └── models/          分离模型（gitignore，首次运行自动下）
│   ├── yaya-xdl/            原子能力（无依赖）
│   │   └── SKILL.md / README.md / run.sh / xdl.py
│   ├── yaya-diarize/        原子能力（无依赖）
│   │   └── SKILL.md / README.md / run.sh / diarize.py
│   └── yaya-xspace/         场景编排（依赖 yaya-xdl + yaya-asr）
│       ├── SKILL.md
│       ├── README.md
│       ├── run.sh
│       ├── distill.py
│       └── out/             产物与音频归档（gitignore，数据跟着 skill 走）
└── README.md
```

## 如何新增一个 skill

本仓库是**单仓多 skill** 结构，新增只需三步：

1. **建目录**：创建 `skills/yaya-<名字>/`，写 `SKILL.md`（frontmatter 必须包含 `name`/`description`——description 决定 Agent 什么时候想到用它）。
2. **登记**：在 `.claude-plugin/marketplace.json` 的 `plugins[0].skills[]` 里加一行 `"./skills/yaya-<名字>"`。**这步不能省**：当 `source: "./"` 且显式列出 skills 时，插件只加载列出的目录，不会自动扫描 `skills/`。
3. **声明依赖**：若依赖仓库内其他 skill（如 yaya-asr），在 SKILL.md 里写明依赖方向、寻址路径（目前统一约定为相邻目录 `../yaya-asr`），并说明缺了它会发生什么。

命名统一保持 `yaya-` 前缀。本地技能清单（如 `~/.zcode/skills/`）与仓库是两回事：仓库是源，装机靠 marketplace 安装或手动软链。

## 命名约定

所有 skill 统一使用 `yaya-` 前缀。

## License

MIT
