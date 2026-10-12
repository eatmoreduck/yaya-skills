#!/usr/bin/env bash
# yaya-xdl —— X Space 音频下载（下载即归档）
# 用法: ./run.sh "<Space链接或13位ID>" [-o 输出目录]
set -euo pipefail
cd "$(dirname "$0")"

if [ $# -lt 1 ]; then
  echo "用法: $0 \"<Space 链接 / 13位ID>\" [-o 输出目录]" >&2
  exit 1
fi

# 纯标准库实现，系统 python3 即可（3.9+）
exec python3 xdl.py "$@"
