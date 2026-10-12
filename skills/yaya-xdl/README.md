# yaya-xdl —— X Space 音频下载（下载即归档）

一条命令：**X Space 链接 → 本地 audio.m4a**。只管下载，不管转写和蒸馏。

X 不提供 Space 归档或搜索，回放 30 天即删——**下载即归档**，否则那段语音永久消失。

```bash
bash skills/yaya-xdl/run.sh "https://x.com/i/spaces/<13位ID>"
bash skills/yaya-xdl/run.sh "<url>" -o /path/to/archive   # 自定义归档目录
```

产物：`~/Documents/yaya/spaces/<space-id>/audio.m4a`（`YAYA_HOME` 可改根目录；完整下载后才落正式名，中断残留自动清理）+ `meta.json`（标题/时长）。

- 依赖：`uv`（yt-dlp 用 uvx 临时跑，零安装）。纯标准库实现，系统 python3 即可。
- 只能下**开了录音、未过留存期（~30 天）**的 Space；私密 Space 需 cookie。
- 完整流水线（转写+蒸馏）用 [yaya-xspace](../yaya-xspace/)；只转写用 [yaya-asr](../yaya-asr/)。
