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
  **说话人 X（能推断出的身份/行业）**
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
    ap.add_argument("--transcript-only", action="store_true", help="只转写不蒸馏")
    args = ap.parse_args()

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

    # 4) 出图：distilled.md → 分享图 PNG（HTML 是中间产物，只进缓存目录）
    if not args.no_card:
        try:
            import card
            card.render(md, workdir=outdir / f".{audio.stem}.asr")
        except Exception as e:
            log(f"⚠️ 分享图生成失败（不影响笔记）：{e}")

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
