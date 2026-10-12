#!/usr/bin/env python3
"""
yaya-xdl —— X Space 音频下载（下载即归档）

把 X Space 链接（或 13 位 ID）变成磁盘上的 audio.m4a。只管下载这一件事：
转写找 yaya-asr，蒸馏找 yaya-xspace。

X 不提供 Space 归档或搜索，回放 30 天即删——所以"下载即归档"不是口号，
是这个 skill 存在的理由。

用法:
    bash run.sh "https://x.com/i/spaces/<13位ID>"
    bash run.sh <13位ID> -o /path/to/archive      # 指定输出目录
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent

VIDEO_EXT = {".mp4", ".mkv", ".mov", ".avi", ".flv", ".webm"}
AUDIO_EXT = {".m4a", ".mp3", ".wav", ".aac", ".flac", ".ogg", ".opus", ".wma"}


OUT_ROOT = SKILL_DIR / "out"    # 归档根目录：就在 skill 自己目录下（数据跟 skill 走）


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def probe_meta(url: str) -> dict:
    try:
        p = subprocess.run(
            ["uvx", "yt-dlp", "--no-warnings", "--simulate",
             "--print", "%(title)s\t%(duration)s\t%(is_live)s", url],
            capture_output=True, text=True, timeout=180)
        parts = (p.stdout.strip().splitlines()[-1] if p.stdout.strip() else "").split("\t")
        return {"title": parts[0] if parts else "",
                "duration": parts[1] if len(parts) > 1 else "",
                "is_live": parts[2] if len(parts) > 2 else ""}
    except Exception:
        return {"title": "", "duration": "", "is_live": ""}


def _audio_files(outdir: Path) -> list[Path]:
    """目录里真正的音频容器。绝不能匹配元数据（meta.json）和 yt-dlp 的
    .part 下载残留——只认音视频扩展名。"""
    return sorted(e for e in outdir.glob("audio.*")
                  if e.suffix in (VIDEO_EXT | AUDIO_EXT))


def download_audio(url: str, outdir: Path) -> Path:
    """下载 Space 音频（yt-dlp）。已存在则跳过；先下临时名，成功后原子改名，
    保证 audio.m4a 一旦出现就是完整文件（中断/并发都不会拿半截当全量）。"""
    got = _audio_files(outdir)
    if got:
        log(f"音频已存在，跳过下载 ({got[0].stat().st_size/1e6:.1f}MB)")
        return got[0]

    log("下载音频中（yt-dlp）…")
    p = subprocess.run(
        ["uvx", "yt-dlp", "--no-warnings", "--newline", "-x",
         "--audio-format", "m4a", "-o", str(outdir / "audio.dl.%(ext)s"), url],
        capture_output=True, text=True)
    done = [e for e in outdir.glob("audio.dl.*")
            if e.suffix in (VIDEO_EXT | AUDIO_EXT)]
    if not done:
        for residue in outdir.glob("audio.dl.*"):
            residue.unlink(missing_ok=True)  # 清掉 .part 残留，避免之后被误当音频
        sys.stderr.write(p.stdout[-2000:] + "\n" + p.stderr[-2000:] + "\n")
        raise RuntimeError("音频下载失败（未开录音 / 已过期 / 需 cookie）")
    audio = outdir / "audio.m4a"
    done[0].replace(audio)
    log(f"下载完成 {audio.stat().st_size/1e6:.1f}MB")
    return audio


def main() -> int:
    ap = argparse.ArgumentParser(
        description="yaya-xdl：X Space 音频下载（下载即归档）")
    ap.add_argument("src", help="Space 链接或 13 位 ID")
    ap.add_argument("-o", "--outdir", default=None,
                    help="输出目录（默认 skill 自己的 out/<space-id>/）")
    args = ap.parse_args()

    url = args.src.strip()
    if re.fullmatch(r"[0-9a-zA-Z]{13}", url):
        url = f"https://x.com/i/spaces/{url}"
    m = re.search(r"spaces/([0-9a-zA-Z]{13})", url)
    if not m:
        sys.exit(f"❌ 无法解析 13 位 Space ID：{args.src}")
    sid = m.group(1)

    outdir = (Path(args.outdir).expanduser().resolve() if args.outdir
              else OUT_ROOT / sid)
    outdir.mkdir(parents=True, exist_ok=True)
    log(f"工作目录: {outdir}")

    meta = probe_meta(url)
    if meta.get("title"):
        log(f"标题: {meta['title']} | 时长: {meta.get('duration')}s")
    meta_path = outdir / "meta.json"
    if not meta_path.exists():
        meta_path.write_text(
            json.dumps({"id": sid, "url": url, **meta}, ensure_ascii=False),
            encoding="utf-8")

    audio = download_audio(url, outdir)
    log(f"音频就位: {audio}")
    print(str(audio))  # 最后一行输出音频绝对路径，供调用方/人消费
    return 0


if __name__ == "__main__":
    sys.exit(main())
