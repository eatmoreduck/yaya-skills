#!/usr/bin/env bash
# yaya-diarize —— 说话人分离（谁在何时说话）
# 用法: ./run.sh <音频或视频> [--speakers N] [-o 输出目录] [--workdir 缓存目录]
set -euo pipefail
cd "$(dirname "$0")"

if [ $# -lt 1 ]; then
  echo "用法: $0 <音频或视频文件> [--speakers N] [-o 输出目录] [--workdir 缓存目录]" >&2
  exit 1
fi

# 分离的依赖（sherpa-onnx/soundfile/模型）住在 yaya-asr 的共享环境里
PY="../yaya-asr/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "❌ 找不到 yaya-asr 的共享环境（$PY）" >&2
  echo "   先跑一次 yaya-asr（bash ../yaya-asr/run.sh <任意音频>），" >&2
  echo "   它会自动建 venv 并下载分离模型（~35MB）。" >&2
  exit 1
fi

exec "$PY" diarize.py "$@"
