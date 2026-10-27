#!/usr/bin/env python3
"""
yaya-asr —— 本地语音转文字（带说话人）

把任意音频/视频变成带说话人标注的文字稿。纯本地、免费、零登录。
Apple Silicon 用 MLX 加速；输出标准格式，可被其它工具/流水线复用。

转写（MLX/GPU）与说话人分离（兄弟 skill yaya-diarize，CPU）**并行执行**：
转写一开始就以后台进程拉起分离，两者互不争抢。

用法:
    python3 asr.py <音频或视频文件>
    python3 asr.py meeting.m4a --speakers 2
    python3 asr.py talk.mp4 --speakers 12 -o ./out
    python3 asr.py audio.wav --no-diarize          # 只转写不分离
    python3 asr.py audio.wav --no-crosscheck       # 省一半时间

输出（默认与输入同目录，可用 -o 指定）:
    <name>.txt          纯文本
    <name>.srt          字幕（不带说话人）
    <name>.dialog.txt   ★ 带说话人的对话稿  [A] 文本
    <name>.dialog.srt   ★ 带说话人的字幕
    <name>.labeled.json ★ 结构化结果（供程序调用）

设计原则：本模块**不认识任何业务**（不知道什么是 Space、会议、播客）。
它只做一件事：音频 → 带说话人的文字。上层工具负责下载、蒸馏、发布。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent      # skills/yaya-asr/
DIARIZE_RUN = SKILL_DIR.parent / "yaya-diarize" / "run.sh"   # 分离已拆到兄弟 skill

WHISPER_REPO = "mlx-community/whisper-large-v3-turbo"

# Whisper 对静音/片头片尾的典型中文幻觉短语。只写短语本身、不带 .* 尾部：
# 是否删除整段由 _clean 按"命中后剩余文本长度"决定，避免吞掉真实发言。
HALLUCINATION_PATTERNS = [
    r"请不吝点赞\s*订阅\s*转发\s*打赏支持\s*明镜与点点栏目",
    r"字幕由\s*Amara\.org\s*社区提供",
    r"字幕志愿者",
    r"MING\s*PAO",
    r"明镜与点点栏目",
]

_PUNCT_END = set("。！？.!?；;，,、")


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ══════════════════════════════════════════════════════════════
# 通用小工具：缓存指纹 / 原子写 / 输出路径
# ══════════════════════════════════════════════════════════════
def _fp(path: Path) -> str:
    """源文件内容指纹（大小+mtime）。文件名相同但内容变了也能识别出来。"""
    st = path.stat()
    return f"{st.st_size}:{st.st_mtime_ns}"


def _atomic_write_json(path: Path, data) -> None:
    """先写临时文件再原子改名：写一半崩溃/磁盘满都不会留下恰好通过
    存在性检查的半截 JSON。"""
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _load_json_cache(path: Path):
    """读缓存；文件残缺（历史遗留的非原子写）就删掉重来，不抛异常。"""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        log(f"⚠️ 缓存损坏（{path.name}），删除后重算")
        path.unlink(missing_ok=True)
        return None


def _out(base: Path, ext: str) -> Path:
    """输出路径用字符串拼接，不用 with_suffix——stem 含点时
    （meeting.v2.m4a）with_suffix 会把 .v2 当扩展名替换掉。"""
    return base.parent / (base.name + ext)


# ══════════════════════════════════════════════════════════════
# 音频准备
# ══════════════════════════════════════════════════════════════
VIDEO_EXT = {".mp4", ".mkv", ".mov", ".avi", ".flv", ".webm", ".ts", ".m4v"}
AUDIO_EXT = {".m4a", ".mp3", ".wav", ".aac", ".flac", ".ogg", ".opus", ".wma"}


def to_16k_wav(src: Path, dest: Path, src_fp: str = "") -> Path:
    """任何音频/视频 → 16kHz 单声道 WAV（ASR 引擎要求的输入）。
    源文件内容变了会自动重转码，不认旧 wav。"""
    fpfile = Path(str(dest) + ".fp")
    if dest.exists() and dest.stat().st_size > 0:
        if not src_fp or (fpfile.exists() and fpfile.read_text().strip() == src_fp):
            return dest
        log("源文件已变化，重新转码…")
    log(f"ffmpeg 转码 → 16kHz 单声道（{src.suffix or '?'}）…")
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
         "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dest)],
        check=True)
    if src_fp:
        fpfile.write_text(src_fp)
    return dest


# ══════════════════════════════════════════════════════════════
# 转写
# ══════════════════════════════════════════════════════════════
def _run_whisper(wav: Path, word_ts: bool, cond_prev: bool):
    import mlx_whisper
    return mlx_whisper.transcribe(
        str(wav), path_or_hf_repo=WHISPER_REPO, language="zh",
        word_timestamps=word_ts, condition_on_previous_text=cond_prev,
        verbose=False)


def transcribe(wav: Path, workdir: Path, cross_check: bool = True,
               src_fp: str = "") -> dict:
    """本地转写（主版本，带词级时间戳）。cross_check 会再跑一遍做差异比对。

    缓存带源文件指纹：文件名相同但内容变了会自动作废重算；
    旧格式缓存（无指纹）兼容放行，避免存量缓存全部重算。
    """
    cache = workdir / "asr.words.json"
    data = None
    if cache.exists() and cache.stat().st_size > 0:
        disk = _load_json_cache(cache)
        if isinstance(disk, dict) and "data" in disk:
            if disk.get("fp") == src_fp:
                data = disk["data"]
                log("转写缓存已存在，跳过")
            else:
                log("源文件已变化，转写缓存作废重算")
        elif isinstance(disk, dict):
            data = disk  # 旧格式缓存，兼容放行
            log("转写缓存已存在（旧格式），跳过")
    if data is None:
        log("本地转写中（主版本，词级时间戳）…")
        t = time.time()
        r = _run_whisper(wav, word_ts=True, cond_prev=True)
        log(f"转写完成 {time.time()-t:.0f}s, {len(r['segments'])} 段")
        data = {"text": r["text"],
                "segments": [{"start": s["start"], "end": s["end"], "text": s["text"],
                              "words": [{"w": w.get("word", ""), "s": w["start"], "e": w["end"]}
                                        for w in s.get("words", [])]}
                             for s in r["segments"]]}
        _atomic_write_json(cache, {"fp": src_fp, "data": data})

    if cross_check:
        _cross_check(wav, workdir, data, src_fp)
    return data


def _cross_check(wav: Path, workdir: Path, primary: dict, src_fp: str = "") -> None:
    """双参数交叉校验：换参数再转一遍，逐字 diff，标出可疑区段。

    Whisper 开 condition_on_previous_text 时可能静默跳段（人听到了但转写没有）。
    差异写入 asr.crosscheck.txt 供人工核对。
    """
    cc = workdir / "asr.alt.json"
    alt = None
    if cc.exists() and cc.stat().st_size > 0:
        disk = _load_json_cache(cc)
        if isinstance(disk, dict) and "segments" in disk:
            if disk.get("fp") == src_fp:
                alt = disk["segments"]
                log("交叉校验转写已存在，跳过")
            else:
                log("源文件已变化，交叉校验缓存作废重算")
        elif isinstance(disk, list):
            alt = disk  # 旧格式缓存，兼容放行
            log("交叉校验转写已存在（旧格式），跳过")
    if alt is None:
        log("交叉校验：换参数重转一遍（约再花同样时间）…")
        t = time.time()
        r = _run_whisper(wav, word_ts=False, cond_prev=False)
        alt = [{"start": s["start"], "end": s["end"], "text": s["text"]} for s in r["segments"]]
        _atomic_write_json(cc, {"fp": src_fp, "segments": alt})
        log(f"交叉校验转写完成 {time.time()-t:.0f}s, {len(alt)} 段")

    import difflib
    ta = "".join(s.get("text", "") for s in primary["segments"])
    tb = "".join(s.get("text", "") for s in alt)
    sm = difflib.SequenceMatcher(None, ta, tb, autojunk=False)
    only_alt, only_pri = [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "insert" and (j2 - j1) >= 6:
            only_alt.append(tb[j1:j2])
        elif tag == "delete" and (i2 - i1) >= 6:
            only_pri.append(ta[i1:i2])

    lines = ["# 交叉校验报告",
             f"\n主版本字数: {len(ta)}  第二遍字数: {len(tb)}",
             f"差异率: {(1 - sm.ratio()) * 100:.2f}%\n"]
    if only_alt:
        lines.append(f"## 第二遍有、主版本无（疑似漏段，{len(only_alt)} 处，务必核对）")
        lines += [f"  - {x}" for x in only_alt]
        lines.append("")
    if only_pri:
        lines.append(f"## 主版本有、第二遍无（疑似幻觉，{len(only_pri)} 处）")
        lines += [f"  - {x}" for x in only_pri]
        lines.append("")
    if not only_alt and not only_pri:
        lines.append("两份转写未发现长度≥6字的差异片段，一致性良好。")
    (workdir / "asr.crosscheck.txt").write_text("\n".join(lines), encoding="utf-8")
    log(f"交叉校验完成：疑似漏段 {len(only_alt)} 处，疑似幻觉 {len(only_pri)} 处")


# ══════════════════════════════════════════════════════════════
# 合并：词 → 说话人 → 带标点的对话稿
# ══════════════════════════════════════════════════════════════
def _clean(text: str) -> str:
    """过滤幻觉句，但绝不误删真实发言。

    只在「命中幻觉模式后剩余文本极短」时认定整段是幻觉（Whisper 的幻觉
    典型形态就是整段只有那句话）；真实发言里偶然提到这些词时整段保留——
    局部删除会把「我们请到了明镜与点点栏目的主持人」这类真话削残。"""
    stripped = text.strip()
    for pat in HALLUCINATION_PATTERNS:
        if re.search(pat, stripped):
            remainder = re.sub(pat, "", stripped).strip("。，、！？,.!?；; ")
            if len(remainder) < 6:
                return ""
    return stripped


def _speaker_at(t0: float, t1: float, turns: list[dict]) -> int:
    """取与 [t0,t1] 重叠最多的说话人；无重叠时退化为时间上最近的。"""
    best, best_ov = None, 0.0
    for r in turns:
        ov = min(t1, r["end"]) - max(t0, r["start"])
        if ov > best_ov:
            best_ov, best = ov, r["speaker"]
    if best is not None:
        return best
    mid = (t0 + t1) / 2
    nearest, dist = None, float("inf")
    for r in turns:
        d = 0.0 if r["start"] <= mid <= r["end"] else min(abs(mid - r["start"]), abs(mid - r["end"]))
        if d < dist:
            dist, nearest = d, r["speaker"]
    return nearest if nearest is not None else -1


def _absorb_fragments(blocks: list, min_chars: int = 6, max_gap: float = 1.5) -> list:
    """把极短的碎块并入相邻同说话人块，减少碎片化。"""
    if not blocks:
        return blocks
    for _ in range(2):
        out = [blocks[0]]
        for sp, ws in blocks[1:]:
            text = "".join(w[0] for w in ws)
            prev_sp, prev_ws = out[-1]
            gap = ws[0][1] - prev_ws[-1][2] if prev_ws else 999
            if len(text) < min_chars and gap <= max_gap and sp == prev_sp:
                out[-1] = (prev_sp, prev_ws + ws)
            else:
                out.append((sp, ws))
        blocks = out
    return blocks


def build_labeled(tx: dict, turns: list[dict],
                  sent_gap: float = 0.8, comma_gap: float = 0.35) -> tuple[list[dict], dict]:
    """把词级转写按说话人分组，用停顿恢复标点。返回 (merged, stats)。"""
    # 纯幻觉段必须在取词之前剔除：段级 _clean 能整段删掉它，但一旦进入 words
    # 就会和相邻真实发言合并成一大块，_clean 看到剩余 ≥6 字就整段放行——
    # dialog.txt/srt 因此长期漏出「请不吝点赞…明镜与点点栏目」（真实踩过的坑）。
    clean_segs = [s for s in tx["segments"] if _clean(s.get("text", "")).strip()]
    words = []
    for seg in clean_segs:
        for w in seg.get("words") or []:
            if w["w"].strip():
                words.append(w)
    if not words:  # 回退到段级（同样过滤空文本，空段会在标点恢复处触发 IndexError）
        words = [{"w": s["text"], "s": s["start"], "e": s["end"]}
                 for s in clean_segs if s.get("text", "").strip()]
    for w in words:
        w["sp"] = _speaker_at(w["s"], w["e"], turns)

    blocks, cur, cur_sp = [], [], None
    for w in words:
        if w["sp"] != cur_sp and cur:
            blocks.append((cur_sp, [(x["w"], x["s"], x["e"]) for x in cur]))
            cur = []
        cur_sp = w["sp"]
        cur.append(w)
    if cur:
        blocks.append((cur_sp, [(x["w"], x["s"], x["e"]) for x in cur]))

    blocks = _absorb_fragments(blocks)
    merged_blocks = []
    for sp, ws in blocks:
        if merged_blocks and merged_blocks[-1][0] == sp:
            merged_blocks[-1][1].extend(ws)
        else:
            merged_blocks.append((sp, list(ws)))
    blocks = merged_blocks

    order = {}
    for sp, _ in blocks:
        if sp not in order and sp >= 0:
            order[sp] = len(order) + 1

    merged = []
    for sp, ws in blocks:
        label = order.get(sp, "?")
        buf, prev_end = [], None
        for tok, ws0, we0 in ws:
            if prev_end is not None:
                gap = ws0 - prev_end
                if buf and buf[-1] and buf[-1][-1] not in _PUNCT_END:
                    if gap >= sent_gap:
                        buf.append("。")
                    elif gap >= comma_gap:
                        buf.append("，")
            buf.append(tok)
            prev_end = we0
        text = _clean("".join(buf))
        if text and text not in ("。", "，", "、"):
            merged.append({"speaker": label, "start": ws[0][1], "end": ws[-1][2], "text": text})

    per: dict = {}
    for m in merged:
        per[m["speaker"]] = per.get(m["speaker"], 0) + len(m["text"])
    stats = {"num_speakers": len(order), "blocks": len(blocks),
             "chars": sum(per.values()), "per_speaker": per}
    return merged, stats


def speaker_letters(merged: list[dict]) -> dict:
    """数字 speaker → A/B/C… 字母标签（对话稿更易读）。"""
    order = []
    for m in merged:
        if m["speaker"] not in order:
            order.append(m["speaker"])
    return {s: chr(ord("A") + i) for i, s in enumerate(order)}


# ══════════════════════════════════════════════════════════════
# 输出（标准格式，供下游复用）
# ══════════════════════════════════════════════════════════════
def _ts_srt(s: float) -> str:
    total_ms = max(0, int(round(s * 1000)))
    h, rem = divmod(total_ms, 3_600_000)
    mi, rem = divmod(rem, 60_000)
    sec, ms = divmod(rem, 1000)
    return f"{h:02d}:{mi:02d}:{sec:02d},{ms:03d}"


def write_outputs(base: Path, tx: dict, merged: list[dict], stats: dict) -> dict:
    """写出 txt / srt / dialog.txt / dialog.srt / labeled.json。返回路径表。"""
    letters = speaker_letters(merged) if merged and merged[0]["speaker"] != "?" else {}
    paths = {}

    # 纯文本
    txt = "\n".join(_clean(s.get("text", "")).strip() for s in tx["segments"]
                    if _clean(s.get("text", "")).strip())
    p = _out(base, ".txt"); p.write_text(txt + "\n", encoding="utf-8")
    paths["txt"] = p

    # 字幕（不带说话人）
    blocks = [f"{i}\n{_ts_srt(s['start'])} --> {_ts_srt(s['end'])}\n{_clean(s.get('text','')).strip()}\n"
              for i, s in enumerate(tx["segments"], 1) if _clean(s.get("text", "")).strip()]
    p = _out(base, ".srt"); p.write_text("\n".join(blocks), encoding="utf-8")
    paths["srt"] = p

    if merged:
        # 对话稿：A：文本
        lines = []
        for m in merged:
            lab = letters.get(m["speaker"], str(m["speaker"]))
            lines.append(f"{lab}：{m['text']}")
        p = _out(base, ".dialog.txt")
        p.write_text("\n\n".join(lines) + "\n", encoding="utf-8")
        paths["dialog_txt"] = p

        # 带说话人的字幕（用真实词级结束时间）
        dblocks = []
        for i, m in enumerate(merged, 1):
            lab = letters.get(m["speaker"], str(m["speaker"]))
            end = m.get("end", m["start"] + 1.0)
            dblocks.append(f"{i}\n{_ts_srt(m['start'])} --> {_ts_srt(end)}\n[{lab}] {m['text']}\n")
        p = _out(base, ".dialog.srt")
        p.write_text("\n".join(dblocks), encoding="utf-8")
        paths["dialog_srt"] = p

        # 结构化结果（供程序调用）
        payload = {"num_speakers": stats.get("num_speakers"),
                   "speakers": {letters.get(k, str(k)): v
                                for k, v in stats.get("per_speaker", {}).items()},
                   "segments": [{"speaker": letters.get(m["speaker"], str(m["speaker"])),
                                 "start": round(m["start"], 2),
                                 "end": round(m.get("end", m["start"]), 2),
                                 "text": m["text"]}
                                for m in merged]}
        p = _out(base, ".labeled.json")
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        paths["labeled_json"] = p

    return paths


# ══════════════════════════════════════════════════════════════
def main() -> int:
    ap = argparse.ArgumentParser(
        description="yaya-asr：本地语音转文字（带说话人分离）",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="音频或视频文件路径")
    ap.add_argument("-o", "--outdir", type=Path, default=None,
                    help="输出目录（默认与输入同目录）")
    ap.add_argument("--speakers", type=int, default=12,
                    help="强制聚类的说话人类数——sherpa 语义是「确切人数」而非上限："
                         "人多的话上填实际活跃人数；人少的录音务必填真实人数；"
                         "-1=按阈值自动聚类（长音频易过分割）。默认 12")
    ap.add_argument("--threshold", type=float, default=0.8,
                    help="自动聚类阈值（仅 --speakers -1 时生效），越大说话人越少")
    ap.add_argument("--no-diarize", action="store_true", help="只转写，不做说话人分离")
    ap.add_argument("--no-crosscheck", action="store_true",
                    help="跳过双参数交叉校验（省一半转写时间）")
    ap.add_argument("--keep-wav", action="store_true", help="保留中间 16k wav")
    args = ap.parse_args()

    src = Path(args.input).expanduser().resolve()  # 绝对路径：diarize 的 run.sh 会 cd，相对路径会断
    if not src.exists():
        sys.exit(f"❌ 找不到文件：{src}")
    if src.suffix.lower() not in VIDEO_EXT | AUDIO_EXT:
        log(f"⚠️  扩展名 {src.suffix} 不在已知列表，仍尝试用 ffmpeg 读取")

    outdir = (args.outdir or src.parent).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    workdir = outdir / f".{src.stem}.asr"
    workdir.mkdir(exist_ok=True)
    base = outdir / src.stem

    log(f"输入: {src.name} ({src.stat().st_size/1e6:.1f}MB)")
    src_fp = _fp(src)
    wav = to_16k_wav(src, workdir / "audio16k.wav", src_fp)

    # 分离以后台进程与转写并行（CPU 分离 ∥ GPU 转写，互不争抢）；
    # 缓存目录传自己的 .asr，diarize 的缓存与历史版本同位置同格式，可直接复用
    diar = None
    if not args.no_diarize:
        if not DIARIZE_RUN.exists():
            sys.exit(f"❌ 找不到 yaya-diarize（说话人分离已拆分到该 skill）\n"
                     f"   期望路径: {DIARIZE_RUN}\n"
                     f"   请确认 yaya-diarize 与 yaya-asr 在同一仓库的 skills/ 下。")
        log("后台启动说话人分离（与转写并行）…")
        diar = subprocess.Popen(
            [str(DIARIZE_RUN), str(src), "-o", str(outdir),
             "--workdir", str(workdir), "--speakers", str(args.speakers),
             "--threshold", str(args.threshold)])

    tx = transcribe(wav, workdir, cross_check=not args.no_crosscheck, src_fp=src_fp)

    if args.no_diarize:
        merged, stats = [], {"num_speakers": 0}
        log("跳过说话人分离")
    else:
        rc = diar.wait()
        if rc != 0:
            sys.exit(f"❌ yaya-diarize 失败（退出码 {rc}），见上方日志")
        turns_path = outdir / f"{src.stem}.turns.json"
        turns = json.loads(turns_path.read_text(encoding="utf-8"))["turns"]
        merged, stats = build_labeled(tx, turns)
        dist = " | ".join(f"{k}:{v}" for k, v in
                          sorted(stats["per_speaker"].items(),
                                 key=lambda x: -x[1] if isinstance(x[1], int) else 0))
        log(f"对话稿: {stats['chars']} 字, {stats['num_speakers']} 个说话人, "
            f"{stats['blocks']} 个发言块")
        log(f"发言分布: {dist}")

    paths = write_outputs(base, tx, merged, stats)

    if not args.keep_wav:
        (workdir / "audio16k.wav").unlink(missing_ok=True)

    print("\n" + "=" * 60)
    log("完成！输出：")
    for k, v in paths.items():
        print(f"   {k:14s} {v}")
    if merged:
        print("\n" + "=" * 60)
        letters = speaker_letters(merged)
        for m in merged[:8]:
            lab = letters.get(m["speaker"], str(m["speaker"]))
            print(f"{lab}：{m['text'][:100]}")
        if len(merged) > 8:
            print(f"…（共 {len(merged)} 段，完整内容见 {paths.get('dialog_txt')}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
