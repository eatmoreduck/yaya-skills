#!/usr/bin/env python3
"""
yaya-xspace —— X (Twitter) Space → 干货笔记

把 Space 链接变成"保留全部精华"的中文干货笔记。本 skill 是**编排层**：
下载交给兄弟 skill yaya-xdl，转写与说话人分离交给 yaya-asr，
自己只做两者之间的串联 + LLM 蒸馏。

用法:
    python3 distill.py "https://x.com/i/spaces/<id>"
    python3 distill.py "/path/to/space.m4a"        # 本地音频
    python3 distill.py <url> --speakers 12 --roster "浩哥,Tim,少白"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
REPO_ROOT = SKILL_DIR.parent                        # skills/
ASR_DIR = REPO_ROOT / "yaya-asr"                    # 兄弟 skill：转写
ASR_RUN = ASR_DIR / "run.sh"
XDL_DIR = REPO_ROOT / "yaya-xdl"                    # 兄弟 skill：下载
XDL_RUN = XDL_DIR / "run.sh"


OUT_ROOT = SKILL_DIR / "out"    # 产物根目录：就在 skill 自己目录下。数据跟 skill 走——
                                # 删 skill 目录=删数据，git pull 也不动未跟踪的 out/。

ZAI_URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"
ZAI_KEY_ENV = "ZAI_CODING_CN_API_KEY"
DEFAULT_MODEL = "glm-5.3-flash"

VIDEO_EXT = {".mp4", ".mkv", ".mov", ".avi", ".flv", ".webm"}
AUDIO_EXT = {".m4a", ".mp3", ".wav", ".aac", ".flac", ".ogg", ".opus", ".wma"}


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ══════════════════════════════════════════════════════════════
# 1. 取音频（调 yaya-xdl 下载 or 本地）
# ══════════════════════════════════════════════════════════════
def download_via_xdl(url: str, outdir: Path) -> Path:
    """调 yaya-xdl 下载 Space 音频到 outdir。音频完整后它才落正式名 audio.m4a。"""
    if not XDL_RUN.exists():
        sys.exit(
            f"❌ 找不到 yaya-xdl（本 skill 依赖它下载 Space 音频）\n"
            f"   期望路径: {XDL_RUN}\n"
            f"   请确认 yaya-xdl 与 yaya-xspace 在同一仓库的 skills/ 下。")
    log("调用 yaya-xdl 下载音频…")
    p = subprocess.run([str(XDL_RUN), url, "-o", str(outdir)], text=True)
    if p.returncode != 0:
        raise RuntimeError(f"yaya-xdl 下载失败（退出码 {p.returncode}）")
    audio = outdir / "audio.m4a"
    if not audio.exists():
        raise RuntimeError("yaya-xdl 未产出 audio.m4a")
    return audio


def _load_meta(outdir: Path) -> dict:
    """读 yaya-xdl 写的 meta.json（标题/时长）；没有就占位。"""
    p = outdir / "meta.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"title": "", "duration": "", "is_live": ""}


def ensure_deps_ready() -> None:
    """检查两个兄弟 skill 是否就位。"""
    if not ASR_RUN.exists():
        sys.exit(
            f"❌ 找不到 yaya-asr（本 skill 依赖它做转写）\n"
            f"   期望路径: {ASR_RUN}\n"
            f"   请确认 yaya-asr 与 yaya-xspace 在同一仓库的 skills/ 下。")
    if not XDL_RUN.exists():
        sys.exit(
            f"❌ 找不到 yaya-xdl（本 skill 依赖它下载 Space 音频）\n"
            f"   期望路径: {XDL_RUN}\n"
            f"   请确认 yaya-xdl 与 yaya-xspace 在同一仓库的 skills/ 下。")
    if not (ASR_DIR / ".venv").exists():
        log("yaya-asr 尚未初始化，首次运行会自动建环境（约 1-2 分钟）…")


# ══════════════════════════════════════════════════════════════
# 2. 调用 yaya-asr 转写
# ══════════════════════════════════════════════════════════════
def run_asr(audio: Path, outdir: Path, speakers: int,
            no_crosscheck: bool) -> list[dict]:
    """调 yaya-asr 转写 → 返回 labeled segments [{speaker, start, text}]。"""
    labeled = outdir / f"{audio.stem}.labeled.json"
    if labeled.exists() and labeled.stat().st_size > 0:
        log("yaya-asr 结果已存在，跳过转写")
    else:
        cmd = [str(ASR_RUN), str(audio), "-o", str(outdir),
               "--speakers", str(speakers)]
        if no_crosscheck:
            cmd.append("--no-crosscheck")
        log(f"调用 yaya-asr 转写（speakers={speakers}）…")
        p = subprocess.run(cmd, text=True)
        if p.returncode != 0:
            raise RuntimeError(f"yaya-asr 失败（退出码 {p.returncode}）")

    data = json.loads(labeled.read_text(encoding="utf-8"))
    segs = data["segments"]
    log(f"转写完成: {len(segs)} 段, {data.get('num_speakers')} 个说话人")
    return segs


def render(merged: list[dict], with_time: bool = True) -> str:
    out = []
    for m in merged:
        if with_time:
            t = int(m["start"])
            out.append(f"[{t//60:02d}:{t%60:02d}] {m['speaker']}: {m['text']}")
        else:
            out.append(f"{m['speaker']}: {m['text']}")
    return "\n".join(out)


# ══════════════════════════════════════════════════════════════
# 3. LLM 蒸馏
# ══════════════════════════════════════════════════════════════
SYSTEM_PROMPT = """你是信息提纯器，服务对象是一个用 AI 做软件开发的独立开发者。他时间少、只要干货，但**极其反感"总结式丢失"**——他要的不是缩写版，是**剔掉废话后保留全部精华**的版本。

输入是一份多人对谈的转写稿（已按说话人分段，标为 A/B/C…；有口语重复、跑题、识别错字、说话人标注错误）。

## 唯一原则：砍废话，保精华

**必须删掉的（废话）：**
- 寒暄、问好、道别、设备/网络调试、玩笑、互相谦让、跑题闲聊
- 口头语（"对对对""就是说""然后呢""我意思是我们就是说"）、重复啰嗦、卡顿重说

**必须逐字保留的（精华，绝不允许缩写或省略）：**
- **金句原话**：判断性的、能记住的话，原样保留措辞
- **关键名词/术语**：任何被提到的"能力 / 竞争力 / 护城河要素 / 方法论 / 工具名 / 案例 / 数字"，哪怕只顺口提了一次，也要收录并注明谁提的
- **每个说话人的核心主张**：A 说了什么、B 说了什么，要能分开看清，不能揉成一团
- **枚举清单**：说话人如果列了"我觉得有几点：X、Y、Z"，**X/Y/Z 一个都不能少，顺序也别改**

宁可保留一个只出现一次的名词，也不许为了"简洁"把它删掉。**删的是废话，不是信息。**

## 输出结构（照抄标题，无前言）

# 一句话总结
（≤60 字，要有判断）

# 核心结论
（3-6 条明确判断）

# 各说话人核心发言
按说话人分组，每人一段：
  **X / 名字（能推断出的身份/行业）**
署名格式硬性要求：必须是「字母 / 名字」斜杠式（如 `**B / 魂蓝姐（…）**`）。
禁止冒号式（`B：名字`）、禁止加「说话人」前缀、禁止两个字母并成一行（`G·小A`）——
下游程序靠这个格式解析「字母→真名」映射，格式漂移会导致说话人改名失败。
  - 核心主张：…（用他的原话措辞，不是你的转述）
  - 关键名词/能力项：…（穷尽列出他提到的所有此类名词）
  - 案例/数字/工具：…
  - 金句：「原话」×N

# 关键名词总表（穷尽，去重）
全篇出现过的所有"能力/竞争力/护城河要素/方法论/概念"，一个不落：
  - 名词 —— 谁提的 —— 一句原话上下文

# 争议与分歧
（谁 vs 谁、争什么、各自理由；没有写「无」）

# 提到的人物 / 工具 / 资源
（原名保留，格式：名字 — 角色/观点）

# 可行动项
（2-4 件具体动作）

## 硬性要求
- 只输出以上板块，标题照抄。
- 中文；语言可以精炼，但**内容不许漏**。
- 不编造原文没有的信息。
- 转写错字按上下文修正（如"FD"≈"FDE"、"Cloud"≈"Claude"、"求日欲"≈"求知欲"、"悬外之音"≈"弦外之音"），但不改原意。
- 若转写质量明显过差（大量乱码/无意义），在«一句话总结»后加一行 **[数据完整性]** 说明。"""


def load_api_key() -> str:
    key = os.environ.get(ZAI_KEY_ENV, "").strip()
    if key:
        return key
    # 逐行解析：跳过注释行，只认真正的赋值行（取最后一处，符合 shell 覆盖语义），
    # 避免抓到注释掉的旧 key 或文档示例。
    pat = re.compile(rf'^\s*(?:export\s+)?{ZAI_KEY_ENV}=["\']?([^"\'\s#]+)')
    for p in [Path.home() / ".bash_profile", Path.home() / ".zshrc", Path.home() / ".zprofile"]:
        if not p.exists():
            continue
        hits = [m.group(1) for line in p.read_text(errors="ignore").splitlines()
                if not line.lstrip().startswith("#") and (m := pat.search(line))]
        if hits:
            return hits[-1]
    raise RuntimeError(f"未找到 {ZAI_KEY_ENV}（请设置环境变量，或写进 ~/.bash_profile）")


def llm_distill(labeled: str, model: str, title: str, roster: str) -> tuple[str, bool]:
    """返回 (蒸馏文本, 是否被 max_tokens 截断)。超时/空返回自动重试一次。"""
    key = load_api_key()
    user = f"标题：{title or '（未知）'}\n"
    if roster:
        user += f"参与者名单（供你辅助识别说话人，不要硬套）：{roster}\n"
    user += f"\n以下是转写稿：\n\n{labeled}"
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user", "content": user}],
        "temperature": 0.4,
        "max_tokens": 8000,
        "thinking": {"type": "disabled"},   # glm-5.x 默认开思考，必须显式关
    }
    log(f"调用 LLM 蒸馏中（{model}）…")
    data, content, finish = {}, "", ""
    for attempt in (1, 2):
        p = subprocess.run(
            ["curl", "-sS", "-m", "600", ZAI_URL,
             "-H", "Content-Type: application/json",
             "-H", f"Authorization: Bearer {key}",
             "-d", json.dumps(payload, ensure_ascii=False)],
            capture_output=True, text=True)
        if p.returncode != 0:
            if attempt == 1:
                log(f"LLM 请求失败（{p.stderr[:200]}），重试一次…")
                continue
            raise RuntimeError(f"LLM 请求失败: {p.stderr[:500]}")
        data = json.loads(p.stdout)
        if "error" in data:
            code = str(data["error"].get("code", "")) if isinstance(data["error"], dict) else ""
            if code == "1301":
                raise RuntimeError(
                    "LLM 报错: 智谱内容审核拦截（1301，题材敏感且同输入随机拦放）。"
                    "转写产物完好，可选：①原样重跑（缓存命中，只花一次调用）"
                    "②--llm-model 换智谱其他模型 ③改用本机其他 LLM CLI 重蒸馏"
                    "（操作要点见 SKILL.md「蒸馏兜底」节）")
            raise RuntimeError(f"LLM 报错: {data['error']}")
        choice = data["choices"][0]
        content = (choice.get("message", {}).get("content") or "").strip()
        finish = choice.get("finish_reason", "")
        if content:
            break
        if attempt == 1:
            log("LLM 空返回，重试一次…")
    if not content:
        raise RuntimeError(f"LLM 空返回: {json.dumps(data, ensure_ascii=False)[:400]}")
    truncated = finish == "length"
    if truncated:
        log("⚠️ 输出触及 max_tokens 上限被截断！笔记不完整，会在产物顶部标注")
    return content, truncated


# ══════════════════════════════════════════════════════════════
# 4. 说话人改名：对外文本产物（dialog.txt / dialog.srt / distilled.md）
#    一律用真名，绝不出现 A/B/C 字母标签（见 AGENTS.md 硬约束 9）。
#    机器接口（labeled.json / turns.json）保持原始字母，不动。
# ══════════════════════════════════════════════════════════════
def _renamed_count(text: str) -> int:
    """数一数文本里还剩多少行首字母标签（用于日志/自检）。"""
    return len(re.findall(r"(?m)^[A-Z]：", text))


def _name_of(mapping: dict[str, str], letter: str) -> str:
    """花名可能带备选（文字姐/蚊子姐、Ringo + 旺仔）→ 对外只取第一个名字。"""
    name = (mapping.get(letter) or "").strip()
    return re.split(r"[+/、，,]", name)[0].strip() if name else ""


def _replace_dialog_lines(text: str, mapping: dict[str, str]) -> str:
    """audio.dialog.txt：行首 `^([A-Z])：` → `真名：`（映射缺失的保留原字母）。"""
    out = []
    for line in text.splitlines():
        m = re.match(r"^([A-Z])：", line)
        name = _name_of(mapping, m.group(1)) if m else ""
        out.append(f"{name}：" + line[2:] if name else line)
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def _replace_srt_tags(text: str, mapping: dict[str, str]) -> str:
    """audio.dialog.srt：`[X]` 标签 → `[真名]`（尾随空格保留原样）。"""
    def sub(m: re.Match) -> str:
        name = _name_of(mapping, m.group(1))
        return f"[{name}]" + m.group(2) if name else m.group(0)
    return re.sub(r"\[([A-Z])\]( ?)", sub, text)


def _strip_lead_name(rest: str, mval: str) -> str:
    """`rest` 若以映射值里的名字开头（Punk，自媒体… / Ringo + 旺仔，营销…）→ 去掉
    名字与紧随的分隔符，只留描述；去不掉就原样返回（标题里名字不重复出现）。"""
    rest = rest.strip().strip("（）()").strip()
    if not rest or not mval:
        return rest
    # 同 card._dename 的分片口径：+/、，, 都是名字分隔符（Ringo + 旺仔 两段都要剥）
    parts = [p.strip() for p in re.split(r"[+/、，,]", mval) if p.strip()]
    for p in parts:
        m = re.match(rf"^{re.escape(p)}\s*[+/、，,]?\s*", rest)
        if m:
            rest = rest[m.end():].strip()
    return re.sub(r"^[+/、，,]+\s*", "", rest).strip()


def _normalize_speaker_headers(md: str) -> str:
    """蒸馏文本落盘前，把 LLM 爱漂移的署名格式归一成 `**X / 名字`（观测过的漂移：
      `**说话人 B / 名`、`**说话人 G·小A`、`**说话人 B：名`、`**B：名`）。
    只碰行首 `**` 后紧跟字母的署名行，正文与金句引文不动；已合规的 `**B / 名` 幂等不变。
    与 SYSTEM_PROMPT 的格式硬约束互为双保险（prompt 不听话时代码兜底）。"""
    md = re.sub(r"^\*\*说话人\s*([A-Za-z])\s*[/：:·]\s*", r"**\1 / ", md, flags=re.M)
    md = re.sub(r"^\*\*说话人\s*([A-Za-z])\s*(?=[（(])", r"**\1", md, flags=re.M)
    md = re.sub(r"^\*\*([A-Za-z])\s*[：:]\s*", r"**\1 / ", md, flags=re.M)
    return md


def _md_header_rename(header: str, mapping: dict[str, str]) -> str:
    """distilled.md 小节标题去字母。兼容 LLM 输出过的多种格式：
      `A（Punk，…）`    → `Punk（…）`（名字保留，去掉 `A（`；描述里重复的名字也去掉）
      `A / Punk（…）`   → `Punk（…）`
      `Punk（A）`       → `Punk`
      `A`（孤字母）     → `Punk`
    拿不到真名的字母原样保留（宁可留着字母，也不能改坏标题）。"""
    h = header.strip()
    m = re.match(r"^([A-Za-z])\s*[/、]\s*(.+)$", h)              # A / Punk（…）
    if m and _name_of(mapping, m.group(1)):
        return m.group(2).strip()
    m = re.match(r"^([A-Za-z])\s*[（(]\s*(.+?)\s*[）)]\s*$", h)  # A（Punk，…）
    if m and _name_of(mapping, m.group(1)):
        name = _name_of(mapping, m.group(1))
        rest = _strip_lead_name(m.group(2), mapping.get(m.group(1), ""))
        return f"{name}（{rest}）" if rest else name
    m = re.match(r"^(.+?)\s*[（(]\s*([A-Za-z])\s*[）)]\s*$", h)  # Punk（A）
    if m and m.group(2) in mapping:
        return m.group(1).strip()
    m = re.fullmatch(r"([A-Za-z])", h)                           # 孤字母 A
    if m and _name_of(mapping, m.group(1)):
        return _name_of(mapping, m.group(1))
    # 名字开头、括号里还是全名→去掉括号里重复的开头（幂等收敛：Punk（Punk，x）→ Punk（x））
    m = re.match(r"^(.+?)\s*[（(]\s*(.+?)\s*[）)]\s*$", h)
    if m:
        lead = m.group(1).strip()
        rest = _strip_lead_name(m.group(2), lead)
        if rest and rest != m.group(2).strip():
            return f"{lead}（{rest}）"
    return header


def _replace_bare_letters(text: str, mapping: dict[str, str]) -> str:
    """正文里「不加括号」的说话人字母指代，只认两种高置信结构（其余一律不动）：
      1) 关键名词表单元格：`—— A ——`、`—— A/C/D/F ——`、`—— H、B ——`
      2) 句首归属：句读后紧跟中文的单字母，如 `A主张…`、`H认为…`
    引号内的原话（「边搞 A 又搞 B」）、平台谐音（B 站）、英文词（GPT/KOL/List/I）
    都因不满足上述结构而不受影响——金句原话的意思绝不能动（AGENTS.md 蒸馏契约）。"""
    def sub(m: re.Match) -> str:
        # 组里可能是 A，也可能是 A/C/D/F —— 逐字母替换、分隔符保持原样
        return re.sub(r"[A-Z]", lambda lm: _name_of(mapping, lm.group(0)) or lm.group(0),
                      m.group(1))
    # 1) 表格单元格：字母序列（A、A/C、A/C/D/F）后面跟着 ` ——` 分隔
    text = re.sub(r"(?<![A-Za-z0-9])([A-Z](?:[/、+＋,，][A-Z])*)(?=\s*[—–])", sub, text)
    # 2) 句首归属：句读/行首之后、紧贴中文的单字母（A主张 / H认为 / E也）
    text = re.sub(r"(?<![A-Za-z0-9])([A-Z])(?=[\u4e00-\u9fff])", sub, text)
    return text


def apply_speaker_names(outdir: Path, md_path: Path) -> dict[str, str]:
    """把对外文本产物里的 A/B/C 字母标签换成真名（从 distilled.md 解析映射）。

    产物：audio.dialog.txt、audio.dialog.srt、distilled.md、speaker_names.json。
    幂等：重复运行不破坏（已无字母时静默跳过）；任何异常只警告，绝不中断主流程。
    返回 字母→真名 的映射（拿不到名字的字母不在其中）。"""
    try:
        md_text = md_path.read_text(encoding="utf-8")
    except OSError as e:
        log(f"⚠️ 说话人改名跳过：读不到 {md_path}（{e}）")
        return {}

    try:
        if str(SKILL_DIR) not in sys.path:
            sys.path.insert(0, str(SKILL_DIR))
        import card          # 同目录模块（card.py）
        lmap = card.parse_distilled(md_text).get("lmap") or {}
    except Exception as e:   # card 依赖 Chrome 等，导入失败也不能挡改名
        log(f"⚠️ 说话人改名跳过：解析 distilled.md 失败（{e}）")
        return {}

    # 只留能拿到非空真名的字母；拿不到的保留原字母
    parsed = {k: v.strip() for k, v in lmap.items() if k and (v or "").strip()}
    # 幂等续跑：distilled.md 改完后标题里字母已消失，再解析就空了——
    # 此时沿用上次落盘的 speaker_names.json（否则映射丢失，离群字母永远补不上）
    mapping = parsed
    names_json = outdir / "speaker_names.json"
    if not mapping and names_json.exists():
        try:
            prev = json.loads(names_json.read_text(encoding="utf-8")).get("mapping") or {}
            mapping = {k: v for k, v in prev.items() if k and (v or "").strip()}
        except (OSError, json.JSONDecodeError):
            mapping = {}
    names_json.write_text(json.dumps(
        {"mapping": mapping,
         "note": "由蒸馏稿解析所得；labeled.json/turns.json 保持原始字母（机器接口）"},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if not mapping:
        log("说话人改名：蒸馏稿里解析不出真名（可能还是旧格式或标题已改完），对外文件保持原样")
        return mapping

    # a) dialog.txt（行首 A：→ 真名：）
    for name in ("audio.dialog.txt",):
        p = outdir / name
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        new = _replace_dialog_lines(text, mapping)
        if new != text:
            p.write_text(new, encoding="utf-8")
            log(f"说话人改名: {name}（残留 {_renamed_count(new)} 行字母标签）")

    # b) dialog.srt（[A] → [真名]）
    p = outdir / "audio.dialog.srt"
    if p.exists():
        text = p.read_text(encoding="utf-8")
        new = _replace_srt_tags(text, mapping)
        if new != text:
            p.write_text(new, encoding="utf-8")
            log("说话人改名: audio.dialog.srt")

    # c) distilled.md：①改小节标题（首 12 行是机器生成的头部，不碰）
    #                ②正文括号里的字母指代换真名（card._dename，复用同款）
    #                ③正文裸单字母指代（表格 `—— A ——`、`A/C/D/F`）也换真名
    try:
        lines = md_text.splitlines()
        for i in range(len(lines)):
            if i < 12 or not lines[i].lstrip().startswith("**"):
                continue
            hm = re.match(r"^(\s*\*\*)(.+?)(\*\*.*)$", lines[i])
            if not hm:
                continue
            renamed = _md_header_rename(hm.group(2), mapping)
            if renamed != hm.group(2):
                lines[i] = hm.group(1) + renamed + hm.group(3)
        mdd = "\n".join(lines) + ("\n" if md_text.endswith("\n") else "")
        denamed = _replace_bare_letters(card._dename(mdd, mapping), mapping)
        if denamed != md_text:
            md_path.write_text(denamed, encoding="utf-8")
            log("说话人改名: distilled.md")
    except Exception as e:
        log(f"⚠️ distilled.md 改名失败（不影响其他产物）：{e}")

    named = "、".join(f"{k}→{v}" for k, v in sorted(mapping.items()))
    log(f"说话人映射: {named}；未能命名的字母保留原样")
    return mapping


def slugify(s: str, n: int = 40) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "-", s).strip("-")[:n] or "space"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="yaya-xspace：X Space → 干货笔记（依赖 yaya-asr）")
    ap.add_argument("src", help="Space 链接 / 13 位 ID / 本地音频文件")
    ap.add_argument("--llm-model", default=DEFAULT_MODEL, help=f"蒸馏模型（默认 {DEFAULT_MODEL}）")
    ap.add_argument("--speakers", type=int, default=12,
                    help="强制聚类的说话人类数——注意是确切类数，不是上限："
                         "人多的话上填实际活跃人数（如 11 人场给 12）；"
                         "人少的录音务必填真实人数；-1=按阈值自动聚类。默认 12")
    ap.add_argument("--roster", default="", help="参与者名单，辅助 LLM 识别说话人")
    ap.add_argument("--no-crosscheck", action="store_true", help="跳过双参数交叉校验（省一半时间）")
    ap.add_argument("--keep-audio", action="store_true",
                    help="（已默认保留，此参数仅为兼容）")
    ap.add_argument("--no-keep-audio", action="store_true",
                    help="跑完删除音频。默认保留——下载即归档，重跑不用再下 81MB")
    ap.add_argument("--no-card", action="store_true",
                    help="跳过生成分享图（distilled.png）；默认生成，失败只警告不影响笔记")
    ap.add_argument("--no-page", action="store_true",
                    help="跳过生成收听页（distilled.html，点哪段听哪段）；默认生成")
    ap.add_argument("--style", default="swiss",
                    choices=["swiss", "editorial", "riso", "midnight", "hand"],
                    help="分享图风格（默认 swiss；可选 swiss/editorial/riso/midnight/hand）")
    ap.add_argument("--transcript-only", action="store_true", help="只转写不蒸馏")
    ap.add_argument("--card-only", action="store_true",
                    help="只出分享图：跳过下载/转写/蒸馏，对已有 distilled.md 直接重新出图"
                         "（换 --style、重出高清图用）")
    ap.add_argument("--all-styles", action="store_true",
                    help="配合 --card-only：五种风格一次全出（distilled.<风格>.png × 5），"
                         "改稿/改错名后一键重出全部版本，杜绝图间新旧不一")
    ap.add_argument("--rename", default="",
                    help='错名勘误一条龙："旧名=新名"（多个用英文逗号分隔）。文本三件套'
                         "（distilled.md / dialog.txt / dialog.srt）+ speaker_names.json "
                         "一次改齐，然后五风格全重出图（配 --no-card 只改文本不出图）")
    ap.add_argument("--publish", action="store_true",
                    help="把这一场发布到线上资产库：音频进 R2、收听页+索引页进 Cloudflare Pages。"
                         "仅用于公开场（发布即声明内容可公开）；需 wrangler 登录（npx wrangler login）")
    ap.add_argument("--type", default="auto",
                    choices=["auto", "space", "interview", "youtube", "audio"],
                    help="资产库类型标记（配 --publish）：auto 按 URL 推断，"
                         "其他来源发布时显式指定（如 YouTube 拆解 --type youtube）")
    ap.add_argument("--dry-run", action="store_true",
                    help="配合 --publish：只在本地组装站点不实际上传")
    args = ap.parse_args()
    if args.all_styles and not args.card_only:
        sys.exit("❌ --all-styles 仅配合 --card-only 使用（完整流程一次只出一版，正式产物固定叫 distilled.png）")

    ensure_deps_ready()

    arg = args.src.strip()
    looks_like_path = arg.startswith(("/", "./", "~", "../")) or \
        Path(arg).suffix.lower() in (VIDEO_EXT | AUDIO_EXT)
    local = (not arg.startswith(("http://", "https://"))) and Path(arg).expanduser().is_file()
    if looks_like_path and not local:
        sys.stderr.write(f"错误：看起来是本地文件路径，但文件不存在：{arg}\n")
        return 2

    # 决定工作目录（就在 skill 自己的 out/ 下）
    out_root = OUT_ROOT
    if local:
        src = Path(arg).expanduser().resolve()
        meta = {"title": src.stem, "duration": "", "is_live": ""}
        outdir = out_root / slugify(src.stem)
    else:
        url = arg
        if re.fullmatch(r"[0-9a-zA-Z]{13}", url):
            url = f"https://x.com/i/spaces/{url}"
        sid = (re.search(r"spaces/([0-9a-zA-Z]{13})", url) or [None, slugify(url)])[1]
        meta = {}
        outdir = out_root / sid

    outdir.mkdir(parents=True, exist_ok=True)
    if not local:
        meta = _load_meta(outdir)
    log(f"工作目录: {outdir}")
    if local:
        log(f"输入: 本地音频 {Path(arg).name}")
    elif meta.get("title"):
        log(f"标题: {meta['title']} | 时长: {meta.get('duration')}s")

    # 发布到线上资产库（默认绝不发布——out/ 里有私人场，显式 --publish 才上传）
    if args.publish:
        import publish
        publish.publish(outdir, dry_run=args.dry_run, ctype=args.type)
        return 0

    # 错名勘误一条龙：名字写错了，稿和图必须一起改——只改一半（图没跟上）最坑人。
    # 文本三件套 + speaker_names.json 一处改、全同步，然后五风格全重出（AGENTS.md 硬约束 9 的对外产物口径）。
    if args.rename:
        if args.card_only:
            sys.exit("❌ --rename 已包含全风格重出图，不必再给 --card-only（只想改文本加 --no-card）")
        md = outdir / "distilled.md"
        if not md.exists():
            sys.exit(f"❌ {outdir} 下没有 distilled.md，无可勘误")
        pairs: dict[str, str] = {}
        for part in args.rename.split(","):
            part = part.strip()
            if not part:
                continue
            if "=" not in part:
                sys.exit(f"❌ --rename 格式：旧名=新名，多个用英文逗号分隔（收到：{part}）")
            old, new = (s.strip() for s in part.split("=", 1))
            if len(old) < 2:
                sys.exit(f"❌ 旧名至少 2 个字（收到：{old!r}）——单字母替换会误伤正文与英文词，不支持")
            if not new:
                sys.exit(f"❌ 新名不能为空（{old}=？）")
            if old == new:
                log(f"跳过：{old} 新旧同名")
                continue
            pairs[old] = new
        if not pairs:
            sys.exit("❌ --rename 没解析出任何有效替换")
        for name in ("distilled.md", "audio.dialog.txt", "audio.dialog.srt"):
            p = outdir / name
            if not p.exists():
                log(f"⚠️ 跳过不存在的 {name}")
                continue
            text = p.read_text(encoding="utf-8")
            new_text = text
            for old, new in pairs.items():
                new_text = new_text.replace(old, new)
            if new_text != text:
                p.write_text(new_text, encoding="utf-8")
                log(f"勘误: {name}")
            else:
                log(f"⚠️ 未变: {name}（没出现旧名？确认拼写）")
        # labeled.json：机器接口的字母标签绝不动，但逐字稿文本里的人名错字
        # 随勘误一并订正——否则收听页上蒸馏栏与逐字稿的名字打架
        lj = outdir / "audio.labeled.json"
        if lj.exists():
            try:
                data = json.loads(lj.read_text(encoding="utf-8"))
                touched = False
                for seg in data.get("segments", []):
                    txt = seg.get("text") or ""
                    nt = txt
                    for old, new in pairs.items():
                        nt = nt.replace(old, new)
                    if nt != txt:
                        seg["text"] = nt
                        touched = True
                if touched:
                    lj.write_text(json.dumps(data, ensure_ascii=False) + "\n",
                                  encoding="utf-8")
                    log("勘误: audio.labeled.json（仅 text 字段，speaker 字母不动）")
            except (OSError, json.JSONDecodeError) as e:
                log(f"⚠️ labeled.json 勘误失败（不影响文本产物）：{e}")
        # speaker_names.json 的映射值同步（值可能是复合名：情感求/程序员、Ringo + 旺仔）
        names_json = outdir / "speaker_names.json"
        if names_json.exists():
            try:
                data = json.loads(names_json.read_text(encoding="utf-8"))
                mapping = data.get("mapping") or {}
                touched = False
                for k, v in mapping.items():
                    nv = v
                    for old, new in pairs.items():
                        nv = nv.replace(old, new)
                    if nv != v:
                        mapping[k] = nv
                        touched = True
                if touched:
                    data["mapping"] = mapping
                    names_json.write_text(
                        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
                    log("勘误: speaker_names.json")
            except (OSError, json.JSONDecodeError) as e:
                log(f"⚠️ speaker_names.json 同步失败（不影响文本勘误）：{e}")
        if not args.no_card:
            stems = [f.stem for f in outdir.glob("audio.*")
                     if f.suffix in (VIDEO_EXT | AUDIO_EXT)]
            import card
            for st in card.STYLES:
                card.render(md, out_png=outdir / f"distilled.{st}.png",
                            workdir=outdir / f".{stems[0] if stems else 'audio'}.asr",
                            style=st)
        if not args.no_page:
            import page
            page.build(outdir)
        return 0

    # 只出分享图：蒸馏已完成时免重跑流水线，直接对已有 distilled.md 出图。
    # 输出 distilled.<style>.png——各风格并存、互相不覆盖，也不覆盖正式的 distilled.png
    if args.card_only:
        md = outdir / "distilled.md"
        if not md.exists():
            sys.exit(f"❌ {outdir} 下没有 distilled.md，先完整跑一遍蒸馏再出图")
        # workdir 沿用完整流程的 .<stem>.asr 缓存目录（HTML 副本只进缓存，输出目录只留 PNG）
        stems = [f.stem for f in outdir.glob("audio.*")
                 if f.suffix in (VIDEO_EXT | AUDIO_EXT)]
        import card
        styles = list(card.STYLES) if args.all_styles else [args.style]
        for st in styles:
            card.render(md, out_png=outdir / f"distilled.{st}.png",
                        workdir=outdir / f".{stems[0] if stems else 'audio'}.asr",
                        style=st)
        if not args.no_page:
            import page
            page.build(outdir)
        return 0

    # 1) 取音频
    if local:
        dest = outdir / src.name
        if not dest.exists() or dest.stat().st_size != src.stat().st_size:
            shutil.copy2(src, dest)
        audio = dest
    else:
        audio = download_via_xdl(url, outdir)
        meta = _load_meta(outdir)  # 重新读：meta.json 刚由 xdl 写入（首跑时上面那次读不到）

    # 2) 转写（交给 yaya-asr）
    segs = run_asr(audio, outdir, args.speakers, args.no_crosscheck)

    if args.transcript_only:
        log(f"仅转写模式。对话稿见 {outdir}/{audio.stem}.dialog.txt")
        return 0

    # 3) 蒸馏
    labeled = render(segs, with_time=True)
    distilled, truncated = llm_distill(labeled, args.llm_model,
                                       meta.get("title", ""), args.roster)
    distilled = _normalize_speaker_headers(distilled)

    md = outdir / "distilled.md"
    n_spk = len({s["speaker"] for s in segs})
    banner = ("⚠️ **[截断警告]** 本次蒸馏触及 max_tokens 上限被截断，以下内容不完整，请分段重蒸馏。\n\n"
              if truncated else "")
    header = (f"# {meta.get('title') or outdir.name}\n\n"
              f"> 来源: {arg}\n"
              f"> 说话人: {n_spk} | 段落: {len(segs)} | 蒸馏模型: {args.llm_model}\n"
              f"> 转写由 yaya-asr 提供\n\n{banner}---\n\n")
    md.write_text(header + distilled, encoding="utf-8")
    log("=" * 60)
    log(f"完成！{md}")
    log("=" * 60)

    # 3.5) 说话人改名：对外文本产物（dialog.txt / dialog.srt / distilled.md）
    #      一律真名，绝不留 A/B/C 字母标签（AGENTS.md 硬约束 9）。
    #      失败只警告，绝不中断主流程；--transcript-only 在上面已 return（无蒸馏稿）。
    try:
        apply_speaker_names(outdir, md)
    except Exception as e:
        log(f"⚠️ 说话人改名失败（不影响笔记）：{e}")

    # 4) 出图：distilled.md → 分享图 PNG（HTML 是中间产物，只进缓存目录）
    if not args.no_card:
        try:
            import card
            card.render(md, workdir=outdir / f".{audio.stem}.asr", style=args.style)
            # 生成时提醒可换风格（别让人错过这个开关）
            log(f"分享图风格：{args.style}（想换？--style "
                f"swiss / editorial / riso / midnight / hand）")
        except Exception as e:
            log(f"⚠️ 分享图生成失败（不影响笔记）：{e}")

    # 5) 网页化：蒸馏稿 + 逐字稿 + 原声 → 可交互收听页（点哪段听哪段）
    if not args.no_page:
        try:
            import page
            page.build(outdir)
        except Exception as e:
            log(f"⚠️ 收听页生成失败（不影响笔记）：{e}")

    if args.no_keep_audio and not local:
        # 只删音频容器（后缀过滤，见 AGENTS.md 硬约束）；
        # audio.dialog.txt / audio.labeled.json 等转写产物必须保留
        for f in outdir.glob("audio.*"):
            if f.suffix in (VIDEO_EXT | AUDIO_EXT):
                f.unlink(missing_ok=True)
        log("已删除下载的音频（默认保留，--no-keep-audio 才删）")

    print("\n" + "=" * 60 + "\n" + distilled + "\n" + "=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
