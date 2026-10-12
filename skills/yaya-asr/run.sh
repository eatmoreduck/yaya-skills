#!/usr/bin/env bash
# yaya-asr —— 本地语音转文字（带说话人分离）
# 用法: ./run.sh <音频或视频文件> [--speakers 12] [-o 输出目录]
set -euo pipefail
cd "$(dirname "$0")"

if [ $# -lt 1 ]; then
  echo "用法: $0 <音频或视频文件> [--speakers N] [-o 输出目录]" >&2
  echo "示例: $0 ~/Downloads/meeting.m4a --speakers 2" >&2
  exit 1
fi

# 首次运行：建独立环境（复用全局 whisper 模型缓存，不重复下载 1.5G）
if [ ! -x .venv/bin/python ]; then
  echo "首次运行：创建独立环境（复用全局 whisper 模型缓存）…" >&2
  uv venv .venv --python 3.13
  uv pip install --python .venv/bin/python mlx-whisper sherpa-onnx soundfile numpy
fi

# 首次运行：下说话人分离模型（约 35MB，不需 HF token）
# curl 必须 -f：否则 404/代理拦截页会以退出码 0 被存成"模型"永久放行；
# 先下临时名再 mv：网络中断留下的半截文件不会冒充完整模型。
if [ ! -f models/3dspeaker_campplus_zh.onnx ] || \
   [ ! -f models/sherpa-onnx-pyannote-segmentation-3-0/model.onnx ]; then
  echo "下载说话人分离模型（约 35MB）…" >&2
  mkdir -p models && cd models
  if [ ! -f sherpa-onnx-pyannote-segmentation-3-0/model.onnx ]; then
    curl -fsSL --retry 3 -o seg.tar.bz2 "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2" \
      || { rm -f seg.tar.bz2; echo "❌ 分离模型下载失败" >&2; exit 1; }
    tar xjf seg.tar.bz2 && rm seg.tar.bz2
  fi
  if [ ! -f 3dspeaker_campplus_zh.onnx ]; then
    curl -fsSL --retry 3 -o 3dspeaker_campplus_zh.onnx.dl "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_campplus_sv_zh-cn_16k-common.onnx" \
      || { rm -f 3dspeaker_campplus_zh.onnx.dl; echo "❌ 声纹模型下载失败" >&2; exit 1; }
    mv 3dspeaker_campplus_zh.onnx.dl 3dspeaker_campplus_zh.onnx
  fi
  cd ..
fi

exec .venv/bin/python scripts/asr.py "$@"
