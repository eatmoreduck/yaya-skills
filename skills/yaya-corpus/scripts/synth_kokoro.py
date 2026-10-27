#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kokoro-82M 离线神经语音合成：按 plan.json 生成分段 MP3 + 双语字幕（LRC/SRT）。

用法：
  python3 synth_kokoro.py --plan plan.json
plan.json:
  {"outdir": "/abs/out", "voice": "af_heart", "speed": 1.0, "bit_rate": 96,
   "segments": [{"name": "01-xxx",
                 "paragraphs": [{"text": "...", "zh": "中文翻译", "pause": 0.6}, "..."]}]}
paragraphs 里的纯字符串默认用 default_pause（0.6s）作为段前停顿。
- "paragraphs" 就是字幕句粒度：一条 = 一条字幕（1-2 句英文，≤150 字符）
- 带 "zh" 时自动输出同名 .lrc（英文在上、中文在下，同一条时间戳）和 .srt
- 模型文件缺失时会自动从 GitHub Release 下载
"""
import argparse, json, os, time
import numpy as np

# 模型跟 skill 走：skills/yaya-corpus/models/kokoro/（已被 .gitignore 整目录忽略）
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = os.path.join(SKILL_DIR, "models", "kokoro")
FILES = {
    "kokoro-v1.0.onnx": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx",
    "voices-v1.0.bin": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
}
SR = 24000


def ensure_models():
    """缺失时下载；先下临时名再原子改名，网络中断不会留下半截文件冒充模型。"""
    os.makedirs(MODEL_DIR, exist_ok=True)
    import urllib.request
    for name, url in FILES.items():
        p = os.path.join(MODEL_DIR, name)
        if os.path.exists(p):
            continue
        tmp = p + ".dl"
        print(f"downloading {name} ...", flush=True)
        try:
            urllib.request.urlretrieve(url, tmp)
        except Exception:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise
        os.replace(tmp, p)
    return os.path.join(MODEL_DIR, "kokoro-v1.0.onnx"), os.path.join(MODEL_DIR, "voices-v1.0.bin")


def write_mp3(samples, sr, path, bit_rate):
    import lameenc
    peak = float(np.max(np.abs(samples))) or 1.0
    samples = samples / peak * 0.95                      # 峰值归一化，各段音量一致
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()
    enc = lameenc.Encoder()
    enc.set_bit_rate(bit_rate)
    enc.set_in_sample_rate(sr)
    enc.set_channels(1)
    enc.set_quality(2)
    with open(path, "wb") as f:
        f.write(enc.encode(pcm) + enc.flush())


def lrc_ts(t):
    m = int(t // 60)
    return f"[{m:02d}:{t - 60 * m:05.2f}]"


def srt_ts(t):
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(round((s - int(s)) * 1000)):03d}"


def write_subtitles(name, cues, outdir):
    """cues: [(start, end, en, zh)]。LRC 必须英文在上、中文在下（同一条时间戳）。"""
    lines = [f"[ti:{name}]", "[by:Kokoro-82M TTS]"]
    for st, _, en, zh in cues:
        ts = lrc_ts(st)
        lines.append(f"{ts}{en}")
        lines.append(f"{ts}{zh}")
    open(f"{outdir}/{name}.lrc", "w").write("\n".join(lines) + "\n")

    blocks = []
    for i, (st, en, eng, zh) in enumerate(cues, 1):
        end = max(cues[i][0] - 0.05 if i < len(cues) else en, st + 1.0)
        blocks.append(f"{i}\n{srt_ts(st)} --> {srt_ts(end)}\n{eng}\n{zh}\n")
    open(f"{outdir}/{name}.srt", "w").write("\n".join(blocks))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--voice", default=None)
    ap.add_argument("--speed", type=float, default=None)
    ap.add_argument("--bit-rate", type=int, default=None)
    ap.add_argument("--default-pause", type=float, default=0.6,
                    help="plan 里段落未指定 pause 时的默认停顿（秒）")
    args = ap.parse_args()

    plan = json.load(open(args.plan))
    voice = args.voice or plan.get("voice", "af_heart")
    speed = args.speed if args.speed is not None else plan.get("speed", 1.0)
    bit_rate = args.bit_rate or plan.get("bit_rate", 96)
    outdir = plan["outdir"]
    os.makedirs(outdir, exist_ok=True)

    model, voices = ensure_models()
    from kokoro_onnx import Kokoro
    kokoro = Kokoro(model, voices)
    print(f"voice={voice} speed={speed} -> {outdir}", flush=True)

    silent = {}

    def silence(sec):
        n = int(SR * sec)
        if n not in silent:
            silent[n] = np.zeros(n, dtype=np.float32)
        return silent[n]

    t0 = time.time()
    done = []
    for seg in plan["segments"]:
        audio, cues, t, words = [], [], 0.0, 0
        for item in seg["paragraphs"]:
            text = item if isinstance(item, str) else item["text"]
            pause = args.default_pause if isinstance(item, str) else item.get("pause", args.default_pause)
            if not text.strip():
                continue
            if pause and audio:
                audio.append(silence(pause))
                t += pause
            samples, _ = kokoro.create(text, voice=voice, speed=speed, lang="en-us")
            dur = len(samples) / SR
            zh = None if isinstance(item, str) else item.get("zh")
            if zh:
                cues.append((t, t + dur, text, zh))
            audio.append(samples.astype(np.float32))
            t += dur
            words += len(text.split())
        if not audio:
            continue

        audio_np = np.concatenate(audio)
        mp3 = os.path.join(outdir, seg["name"] + ".mp3")
        write_mp3(audio_np, SR, mp3, bit_rate)
        if cues:
            write_subtitles(seg["name"], cues, outdir)
        done.append((seg["name"], words, t, os.path.getsize(mp3)))
        print(f"OK {seg['name']} | {words}w | {t/60:.1f}min | "
              f"{os.path.getsize(mp3)/1048576:.2f}MB | {'+lrc/srt ' if cues else ''}| {time.time()-t0:.0f}s",
              flush=True)

    print(f"\nDONE {len(done)} files | {sum(d[1] for d in done)} words | "
          f"{sum(d[2] for d in done)/60:.1f} min audio | took {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
