#!/usr/bin/env python3
"""
yaya-diarize —— 说话人分离（谁在何时说话）

把任意音频变成说话人时间线：sherpa-onnx（pyannote 分割 + CAM++ 中文声纹）
聚类出"谁在什么时候说话"，输出 turns.json。纯本地，不依赖转写——
要不要文字是 yaya-asr 的事，本 skill 只认声音。

被 yaya-asr 作为分离阶段调用（与 MLX 转写并行：GPU 转写 ∥ CPU 分离，
互不争抢）；也可以单独使用。

用法:
    bash run.sh <音频或视频> [-o 输出目录] [--speakers N] [--workdir 缓存目录]

输出:
    <stem>.turns.json   {"num_speakers": N, "turns": [{start, end, speaker}]}
    缓存: <workdir>/asr.diarization.json（源指纹+聚类参数绑定，兼容 yaya-asr 旧缓存）
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
MODELS = SKILL_DIR / "models"          # 兼容独立放置；共享布局用 yaya-asr 的模型
ASR_MODELS = SKILL_DIR.parent / "yaya-asr" / "models"
SEG_MODEL = ASR_MODELS / "sherpa-onnx-pyannote-segmentation-3-0" / "model.onnx"
EMB_MODEL = ASR_MODELS / "3dspeaker_campplus_zh.onnx"
if not SEG_MODEL.exists():
    SEG_MODEL = MODELS / "sherpa-onnx-pyannote-segmentation-3-0" / "model.onnx"
    EMB_MODEL = MODELS / "3dspeaker_campplus_zh.onnx"

VIDEO_EXT = {".mp4", ".mkv", ".mov", ".avi", ".flv", ".webm", ".ts", ".m4v"}
AUDIO_EXT = {".m4a", ".mp3", ".wav", ".aac", ".flac", ".ogg", ".opus", ".wma"}


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _fp(path: Path) -> str:
    """源文件内容指纹（大小+mtime），与 yaya-asr 同款。"""
    st = path.stat()
    return f"{st.st_size}:{st.st_mtime_ns}"


def to_16k_wav(src: Path, dest: Path, src_fp: str = "") -> Path:
    """任何音频/视频 → 16kHz 单声道 WAV；源变了自动重转（fp 边车记录）。"""
    fpfile = Path(str(dest) + ".fp")
    if dest.exists() and dest.stat().st_size > 0:
        if not src_fp or (fpfile.exists() and fpfile.read_text().strip() == src_fp):
            return dest
        log("源文件已变化，重新转码…")
    import subprocess
    log(f"ffmpeg 转码 → 16kHz 单声道（{src.suffix or '?'}）…")
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
         "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dest)],
        check=True)
    if src_fp:
        fpfile.write_text(src_fp)
    return dest


def diarize(wav: Path, workdir: Path, threshold: float, num_speakers: int,
            src_fp: str = "") -> list[dict]:
    """分离。缓存绑定 源文件指纹 + 聚类参数：换音频或换 --speakers 都会
    作废重算。缓存文件名与 yaya-asr 历史版本一致（asr.diarization.json），
    旧缓存直接兼容。"""
    import json as _json
    cache = workdir / "asr.diarization.json"
    if cache.exists() and cache.stat().st_size > 0:
        try:
            disk = _json.loads(cache.read_text(encoding="utf-8"))
        except (_json.JSONDecodeError, UnicodeDecodeError):
            log(f"⚠️ 缓存损坏（{cache.name}），删除后重算")
            cache.unlink(missing_ok=True)
            disk = None
        if isinstance(disk, dict) and "turns" in disk:
            if (disk.get("fp") == src_fp
                    and disk.get("num_speakers") == num_speakers
                    and disk.get("threshold") == threshold):
                log("分离缓存已存在，跳过")
                return disk["turns"]
            log("音频或聚类参数已变化，分离缓存作废重算")
        elif isinstance(disk, list):
            log("分离缓存已存在（旧格式），跳过")
            return disk

    import soundfile as sf
    import sherpa_onnx

    if not SEG_MODEL.exists() or not EMB_MODEL.exists():
        sys.exit(f"缺少分离模型（{SEG_MODEL} / {EMB_MODEL}）。\n"
                 f"先跑一次 yaya-asr（bash ../yaya-asr/run.sh <任意音频>），"
                 f"它会自动下载模型到共享 models/。")

    log("说话人分离中（sherpa-onnx pyannote-seg + CAM++ 中文声纹）…")
    cfg = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                model=str(SEG_MODEL))),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(EMB_MODEL)),
        clustering=sherpa_onnx.FastClusteringConfig(
            num_clusters=num_speakers, threshold=threshold),
        min_duration_on=0.3, min_duration_off=0.5)
    assert cfg.validate(), "sherpa 配置无效"
    sd = sherpa_onnx.OfflineSpeakerDiarization(cfg)

    t = time.time()
    audio, sr = sf.read(str(wav), dtype="float32", always_2d=True)
    assert sr == sd.sample_rate, f"需要 {sd.sample_rate}Hz"
    res = sd.process(audio[:, 0]).sort_by_start_time()
    turns = [{"start": float(r.start), "end": float(r.end), "speaker": int(r.speaker)}
             for r in res]
    log(f"分离完成 {time.time()-t:.0f}s, {len(turns)} 个发言段, "
        f"{len(set(t['speaker'] for t in turns))} 个说话人")

    tmp = Path(str(cache) + ".tmp")
    tmp.write_text(_json.dumps({"fp": src_fp, "num_speakers": num_speakers,
                                "threshold": threshold, "turns": turns},
                               ensure_ascii=False), encoding="utf-8")
    tmp.replace(cache)
    return turns


def main() -> int:
    ap = argparse.ArgumentParser(
        description="yaya-diarize：说话人分离（谁在何时说话）")
    ap.add_argument("input", help="音频或视频文件路径")
    ap.add_argument("-o", "--outdir", type=Path, default=None,
                    help="输出目录（默认与输入同目录）")
    ap.add_argument("--workdir", type=Path, default=None,
                    help="缓存目录（默认 <输出目录>/.<stem>.diar；yaya-asr 会传自己的 .asr 目录来共享缓存）")
    ap.add_argument("--speakers", type=int, default=12,
                    help="强制聚类的说话人类数——确切类数，不是上限："
                         "人少务必填真实人数；-1=按阈值自动聚类。默认 12")
    ap.add_argument("--threshold", type=float, default=0.8,
                    help="自动聚类阈值（仅 --speakers -1 时生效）")
    args = ap.parse_args()

    src = Path(args.input).expanduser().resolve()  # 绝对路径：run.sh 已 cd 到 skill 目录
    if not src.exists():
        sys.exit(f"❌ 找不到文件：{src}")
    if src.suffix.lower() not in VIDEO_EXT | AUDIO_EXT:
        log(f"⚠️  扩展名 {src.suffix} 不在已知列表，仍尝试用 ffmpeg 读取")

    outdir = (args.outdir or src.parent).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    workdir = (args.workdir or outdir / f".{src.stem}.diar").expanduser().resolve()
    workdir.mkdir(parents=True, exist_ok=True)

    log(f"输入: {src.name} ({src.stat().st_size/1e6:.1f}MB)")
    src_fp = _fp(src)
    wav = to_16k_wav(src, workdir / "audio16k.wav", src_fp)
    turns = diarize(wav, workdir, args.threshold, args.speakers, src_fp=src_fp)

    out = outdir / f"{src.stem}.turns.json"
    out.write_text(json.dumps({"num_speakers": len({t["speaker"] for t in turns}),
                               "turns": turns}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    if not (workdir / "audio16k.wav.fp").exists():
        (workdir / "audio16k.wav.fp").write_text(src_fp)
    log(f"完成！{out}")
    print(str(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
