# 贡献指南

> [English](CONTRIBUTING.en.md)

谢谢你想为 yaya-skills 出力。这个仓库的规矩都写在 [AGENTS.md](AGENTS.md) 里——**动手前先通读它**，尤其是「硬约束（踩过坑的，别回退）」一节。下面只讲最要紧的几条。

## 开工之前

1. **读 AGENTS.md**。里面的硬约束每一条都对应一次真实事故（文件误删、缓存失效、说话人字母泄漏…）。改动若与硬约束冲突，默认是你错了。
2. **改契约前先读契约**：
   - 改 `yaya-asr` 的转写/分离/缓存 → 先读 `skills/yaya-asr/SKILL.md`（输出文件清单是稳定接口，`<name>.labeled.json` 供下游程序消费，格式不许变）
   - 改 `yaya-xspace` 的蒸馏提示词 → 先读 `skills/yaya-xspace/SKILL.md` 与根 README 的设计原则
3. **新增 skill 必须登记** `.claude-plugin/marketplace.json` 的 `plugins[0].skills[]`——显式列出时不会自动扫描 `skills/`。步骤见根 README「如何新增一个 skill」。

## 这个仓库的几条铁律

- **依赖单向**：编排层 → 原子能力，兄弟 skill 一律经 `run.sh` 子进程调用。不许反向依赖、不许复制实现。
- **数据跟 skill 走**：产物/音频/缓存一律放 skill 自己的 `out/`，没有搬移开关。`out/` 已整目录 gitignore——私人 Space 的音频和笔记**绝不能**进公开仓库，`demo/` 是手工挑选的公开样例，别混。
- **「蒸馏」不是「总结」**：契约是收率——砍寒暄口头语，但金句原话、关键名词、每人主张、枚举清单一项不许丢。提示词里写「总结」LLM 会往简短优化，这是错的。
- **对外文本不出现说话人字母标签**：`dialog.txt` / `dialog.srt` / `distilled.md` 用真名；`labeled.json` / `turns.json` 保持字母（机器接口）。

## 提交与验证

无测试套件，验证靠这组命令（见 AGENTS.md）：

```bash
skills/yaya-asr/.venv/bin/python -m py_compile skills/yaya-asr/scripts/asr.py skills/yaya-xspace/distill.py skills/yaya-xdl/xdl.py skills/yaya-diarize/diarize.py
bash -n skills/yaya-asr/run.sh && bash -n skills/yaya-xspace/run.sh && bash -n skills/yaya-xdl/run.sh && bash -n skills/yaya-diarize/run.sh
# 端到端：跑一场已有缓存的 Space，缓存命中时只花一次 LLM 调用
bash skills/yaya-xspace/run.sh "https://x.com/i/spaces/<id>"
```

- commit message 用中文，风格参考 `git log`（`feat:` / `fix:` / `polish:` / `docs:` + 一句话讲清「改了什么、为什么」）。
- PR 描述里说明：改了什么、为什么、验证方式（跑过上面哪条命令）。

## 沟通

中文优先。Issue 请用模板；拿不准是不是 bug 的，先开 Issue 描述现象即可。
