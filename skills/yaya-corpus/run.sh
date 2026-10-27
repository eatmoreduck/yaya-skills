#!/usr/bin/env bash
# yaya-corpus —— 文字稿 → 可听语料（校对清洗 → 离线 TTS → 双语字幕 → 标签内嵌）
# 用法:
#   ./run.sh extract <稿件.docx|.pdf|.txt> [-o 输出.txt] [--headings]
#   ./run.sh decrypt <a.pdf | 目录> [-o 输出目录]
#   ./run.sh synth   <plan.json> [--voice af_heart] [--speed 1.0] [--bit-rate 96]
#   ./run.sh tags    <输出目录> [--cover 封面.jpg] [--album 专辑名] [--artist 歌手]
set -euo pipefail
cd "$(dirname "$0")"

usage() {
  cat >&2 <<'EOF'
用法: ./run.sh <子命令> [参数...]

子命令:
  extract  <docx|pdf|txt> [-o 输出.txt] [--headings]   抽纯文本（默认带英文清洗）
  decrypt  <pdf | 目录>   [-o 输出目录]                破解 PDF 字体子集混淆
  synth    <plan.json>    [--voice V] [--speed S]      合成 MP3 + LRC/SRT
  tags     <目录>         [--album A] [--artist AR]    写入歌词/封面/ID3 标签

示例:
  ./run.sh extract 讲解稿.docx -o draft.txt
  ./run.sh decrypt 加密导游词.pdf -o out/decrypted/
  ./run.sh synth   out/plan.json
  ./run.sh tags    out/mp3/ --album "上海导游" --artist eatmoreduck
EOF
}

if [ $# -lt 1 ]; then
  usage
  exit 1
fi

CMD="$1"; shift

case "$CMD" in
  -h|--help|help) usage; exit 0 ;;
  extract|decrypt|synth|tags) ;;
  *) echo "❌ 未知子命令: $CMD" >&2; usage; exit 1 ;;
esac

if [ $# -lt 1 ]; then
  echo "❌ 子命令 $CMD 缺少参数" >&2
  usage
  exit 1
fi

# 首次运行：建独立环境（TTS 模型由脚本按需自动下载）
if [ ! -x .venv/bin/python ]; then
  echo "首次运行：创建独立环境（uv）…" >&2
  if ! command -v uv >/dev/null; then
    echo "❌ 需要 uv：brew install uv" >&2
    exit 1
  fi
  uv venv .venv --python 3.13
  uv pip install --python .venv/bin/python kokoro-onnx lameenc numpy mutagen pymupdf
  echo "✅ 环境就绪：.venv/" >&2
fi

case "$CMD" in
  extract) exec .venv/bin/python scripts/extract.py "$@" ;;
  decrypt) exec .venv/bin/python scripts/decrypt.py "$@" ;;
  synth)
    # 允许 run.sh synth plan.json 或 run.sh synth --plan plan.json 两种写法
    case "$1" in
      -*) exec .venv/bin/python scripts/synth_kokoro.py "$@" ;;
      *)  PLAN="$1"; shift
          exec .venv/bin/python scripts/synth_kokoro.py --plan "$PLAN" "$@" ;;
    esac ;;
  tags)    exec .venv/bin/python scripts/embed_tags.py "$@" ;;
esac
