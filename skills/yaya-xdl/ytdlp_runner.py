"""yt-dlp 启动包装：放宽 Space ID 正则到 13-14 位后再执行原 CLI。

背景：X 会生成 14 位 Space ID，而 yt-dlp 的 TwitterSpacesIE._VALID_URL
硬编码 [0-9a-zA-Z]{13}，14 位 ID 被截断成前 13 位去查询，必报
"Twitter Space not found"（实测 2026-11：六个 14 位 ID 全部此因）。
这里在 import 期把正则放宽为 {13,14} 后交给 yt-dlp 原入口执行。

上游修复（正则改 {13,14} 或更长）发布后，本文件可删，xdl.py 改回直调
`uvx yt-dlp`。
"""
import yt_dlp.extractor.twitter as _tw

_tw.TwitterSpacesIE._VALID_URL = _tw.TwitterSpacesIE._VALID_URL.replace(
    "{13}", "{13,14}")

from yt_dlp import main

if __name__ == "__main__":
    main()
