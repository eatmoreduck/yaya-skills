#!/usr/bin/env bash
# yaya-xspace —— X Space → 干货笔记（依赖同仓库的 yaya-asr）
# 用法: ./run.sh "<Space链接或本地音频>" [--speakers 12] [--roster "..."]
set -euo pipefail
cd "$(dirname "$0")"

if [ $# -lt 1 ]; then
  echo "用法: $0 \"<Space 链接 / 13位ID / 本地音频>\" [--speakers N] [--roster \"...\"]" >&2
  exit 1
fi

# 检查依赖的 yaya-asr
ASR_DIR="$(cd .. && pwd)/yaya-asr"
if [ ! -x "$ASR_DIR/run.sh" ]; then
  echo "❌ 找不到 yaya-asr（本 skill 依赖它做转写）" >&2
  echo "   期望路径: $ASR_DIR/run.sh" >&2
  exit 1
fi

# 本 skill 只用标准库，借用 yaya-asr 的 python（否则退回系统 python3）
PY="$ASR_DIR/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "提示：yaya-asr 环境尚未建立，它会在首次转写时自动创建（约 1-2 分钟）" >&2
  PY="$(command -v python3)"
fi

exec "$PY" distill.py "$@"
