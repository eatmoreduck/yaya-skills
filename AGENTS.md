# AGENTS.md

Leon (eatmoreduck) 的个人单仓多 skill 仓库：本地优先的 Agent Skills，把录音变成文字、把 X Space 蒸馏成中文干货笔记。面向用户的文档、commit message、对话一律用中文。

## 结构与依赖（改代码前必看）

```
skills/
├── yaya-xdl/      原子能力：Space 链接 → audio.m4a（xdl.py，下载即归档）
├── yaya-asr/      原子能力：任意音频 → 带说话人转写（scripts/asr.py）
├── yaya-diarize/  原子能力：音频 → 说话人时间线 turns.json（diarize.py）
└── yaya-xspace/   编排层：Space 链接 → 调 xdl 下载 → 调 asr 转写 → LLM 蒸馏（distill.py）
```

- **依赖单向**：`yaya-xspace → yaya-xdl + yaya-asr`、`yaya-asr → yaya-diarize`；兄弟 skill 一律经 `run.sh` 子进程调用、靠相邻目录寻址。xdl/asr/diarize 是原子能力，互不依赖、不认识业务概念。不许反向依赖、不许复制实现。
- **数据位置**（Leon 拍板，无例外）：产物/音频归档/缓存一律放 skill 自己的 `out/`（distill.py/xdl.py 各自的 `OUT_ROOT` 常量）——skill 数据跟 skill 走，删 skill 目录=删数据，`git pull` 不动未跟踪的 out/。**没有 YAYA_HOME 之类的搬移开关**——数据不许放 skill 外。`skills/*/out/` 已 .gitignore **整目录忽略**（私人 Space 笔记+音频绝不能进公开仓库）；`demo/` 是手工挑选、随仓库公开的样例产出，别和 out/ 混。不用 /tmp 存要留的东西（重启即清，违背下载即归档）。音频默认保留（下载即归档），`--no-keep-audio` 才删。
- **asr 内部流水线并行**：转写（MLX/GPU）开始时以后台进程拉起 yaya-diarize（CPU 分离），`transcribe` 返回后 `wait()`。实测 GPU/CPU 零争抢；**但两个 MLX 进程绝不能并发**（会崩/拖死）——别把并行改成"再起一个转写进程"。
- **新增 skill 必须登记** `.claude-plugin/marketplace.json` 的 `plugins[0].skills[]`——`source: "./"` 且显式列出时只加载列出的目录，不会自动扫描 `skills/`。步骤见根 README「如何新增一个 skill」。

## 验证命令（无测试套件，按此组合验证）

```bash
skills/yaya-asr/.venv/bin/python -m py_compile skills/yaya-asr/scripts/asr.py skills/yaya-xspace/distill.py skills/yaya-xdl/xdl.py skills/yaya-diarize/diarize.py
bash -n skills/yaya-asr/run.sh && bash -n skills/yaya-xspace/run.sh && bash -n skills/yaya-xdl/run.sh && bash -n skills/yaya-diarize/run.sh
# 端到端：跑一场已有数据的 Space（数据在 skills/yaya-xspace/out/ 下，缓存命中时只花一次 LLM 调用）
bash skills/yaya-xspace/run.sh "https://x.com/i/spaces/1oKMvNAwRdNGQ"
```

Python 环境在 `skills/yaya-asr/.venv`（uv 管理，3.13），别用系统 python3（3.9）跑；模型在 `skills/yaya-asr/models/`（已 gitignore）。

## 硬约束（踩过坑的，别回退）

1. **文件操作必须带后缀过滤**。转写产物与下载音频同 stem（`audio.labeled.json` / `audio.m4a` …），裸 `glob("audio.*")` 曾把产物当音频/误删产物，下载侧和清理侧各咬过一次。`_audio_files()` 现居 `yaya-xdl/xdl.py`；`distill.py` 的清理用同款后缀过滤。下载一律走临时名 + 原子 rename（`audio.dl.*` → `audio.m4a`）。
2. **缓存必须带源文件指纹**（`_fp()`：size+mtime_ns）+ 参数绑定；写入走 `_atomic_write_json`（tmp+replace）；读取容错自愈。旧格式缓存（无指纹）刻意兼容放行——别"顺手"删掉兼容分支，会让存量缓存全部重算（一场 114 分钟 ≈ 50 分钟）。
3. **`--speakers` 语义 = 强制聚成 N 类（确切人数），不是上限**（sherpa `num_clusters>0` 时 threshold 被忽略）。默认 12 是为 X Space 人多场景刻意保留的，别改成 -1（阈值自动聚类在长音频会过分割出几十个说话人）。文档必须如实写"不是上限"。分离缓存归 `yaya-diarize` 所有（文件名 `asr.diarization.json` 与历史版本一致，asr 通过共享 workdir 复用旧缓存）。
4. **幻觉过滤只删整段**（命中模式后剩余 <6 字才删）；`HALLUCINATION_PATTERNS` 里不许出现 `.*` 尾部——真实发言提到"明镜/字幕志愿者"等词时不能连坐删除。
5. **输出路径用字符串拼接**（`_out()`），不用 `with_suffix`（stem 含点时错位）。
6. **蒸馏 LLM 必须显式关思考**（`thinking: {"type":"disabled"}`，glm-5.x 默认开会吃光 token 返回空）；必须检查 `finish_reason=="length"` 并在 distilled.md 顶部打截断警告。Key=`ZAI_CODING_CN_API_KEY`。
7. **多段 Space 陷阱**：主持人断线重连会新开 Space（新 ID），只拿到一段会得出"某内容不存在"的错误结论。转写稿出现重连信号（开场静音、"网络问题""你俩继续""刚才讲到哪"）要主动问用户是否有另一段。

## 已知但刻意不做的

- **性能优化未应用**（Leon 拍板挂起）：分离声纹 `num_threads=4` 可 2× 加速、转写∥分离可并行（GPU/CPU 零争抢，实测 41.5→22 分钟）。别"顺手"加上，等他发话。
- **git 零 commit**：Leon 自己控提交节奏，未经要求不 commit 不 push。

## 文案与措辞

- 用词是**"蒸馏"不是"总结"**：契约是收率——砍寒暄/口头语/重复，但金句原话、关键名词、每人主张、枚举清单一项不许丢。提示词里写"总结"LLM 会往简短优化，这是错的。
- README/文档里的判断句（「下载即归档」「蒸馏不是缩写」）是作者刻意立的，润色可顺字句，不可磨平成营销腔；润色文案用 Leon 本机 `gemini --skip-trust -p "..."`。
- 技术文档里 `--speakers`、产物文件名等事实以 `AGENTS.md` 本节和代码为准，润色不得漂移。

## 敏感区先读

改 `asr.py` 的转写/分离/缓存逻辑前先读 `skills/yaya-asr/SKILL.md`（对外契约：输出文件清单是稳定接口，`<name>.labeled.json` 供下游程序消费，格式不许变）。改 `distill.py` 的提示词前先读 `skills/yaya-xspace/SKILL.md` 与根 README 的设计原则。
