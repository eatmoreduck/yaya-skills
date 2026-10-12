#!/usr/bin/env python3
"""
yaya-xspace 出图 —— 把 distilled.md 渲染成一张设计好的分享图（PNG）。

流程：解析 distilled.md（一句话总结/核心结论/金句/可行动项）
   → 生成暗色霓虹风 HTML（与仓库视觉一致）
   → Chrome headless 两遍截图（先量内容高度，再按高度精确出图）
   → 只留 <name>.png，HTML 中间产物进缓存目录（不污染输出）

用法（distill.py 会自动调用；也可单独重渲染）:
    python3 card.py <distilled.md 路径> [--out PNG] [--workdir HTML存放目录]

依赖：本机 Chrome（或 Chromium）。找不到时优雅失败，不影响主流程。
"""

from __future__ import annotations

import argparse
import html as _html
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

WIDTH = 1080
CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "chromium",
    "chromium-browser",
    "google-chrome",
    "google-chrome-stable",
]


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def find_chrome() -> str | None:
    for c in CHROME_CANDIDATES:
        if "/" in c:
            if Path(c).exists():
                return c
        else:
            p = shutil.which(c)
            if p:
                return p
    return None


# ══════════════════════════════════════════════════════════════
# 解析 distilled.md
# ══════════════════════════════════════════════════════════════
def parse_distilled(md_text: str) -> dict:
    lines = md_text.splitlines()

    def section_lines(name: str) -> list[str]:
        """取 `# <name>` 到下一个 `# ` 之间的行。"""
        out, inside = [], False
        for ln in lines:
            if ln.startswith("# "):
                if inside:
                    break
                inside = ln[2:].strip() == name
                continue
            if inside:
                out.append(ln)
        return out

    title = next((ln[2:].strip() for ln in lines if ln.startswith("# ")), "")
    # 去掉 md 里第一个标题后的空行；title 也可能是 Space 标题
    header = "\n".join(lines[:12])
    m_spk = re.search(r"说话人:\s*(\d+)", header)
    m_seg = re.search(r"段落:\s*(\d+)", header)
    n_spk = m_spk.group(1) if m_spk else ""

    def clean(s: str) -> str:
        s = s.strip()
        s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
        s = s.replace("`", "")
        return s.strip()

    # 一句话总结
    summary = ""
    for ln in section_lines("一句话总结"):
        if ln.strip():
            summary = clean(ln)
            break

    # 核心结论：兼容 "1. xxx" 与 "- xxx" 两种列表格式（LLM 输出会变）
    conclusions = []
    for ln in section_lines("核心结论"):
        m = re.match(r"(?:\d+\.|[-*])\s*(.+)$", ln.strip())
        if not m:
            continue
        body = clean(m.group(1))
        mm = re.match(r"^(.{2,14}?)[：:](.+)$", body)
        if mm and "，" not in mm.group(1):
            conclusions.append((mm.group(1), mm.group(2)))
        else:
            conclusions.append(("", body))

    # 金句：按说话人段落收集「」
    quotes: list[tuple[str, str]] = []
    speaker = ""
    seen = set()
    for ln in lines:
        hm = re.match(r"^\*\*(.+?)\*\*", ln)
        if hm:
            name = re.split(r"[（(]", hm.group(1))[0].strip()
            speaker = name
        if "金句" in ln and "「" in ln:
            for q in re.findall(r"「([^」]{4,72})」", ln):
                q = q.strip()
                if "……" in q or q in seen:  # 残缺/自我更正的引文不上图
                    continue
                seen.add(q)
                quotes.append((q, speaker))

    # 可行动项：同样兼容两种列表格式
    actions = []
    for ln in section_lines("可行动项"):
        m = re.match(r"(?:\d+\.|[-*])\s*(.+)$", ln.strip())
        if m:
            actions.append(clean(m.group(1)))

    return {
        "title": title,
        "n_spk": n_spk,
        "n_seg": m_seg.group(1) if m_seg else "",
        "summary": summary,
        "conclusions": conclusions,
        "quotes": quotes,
        "actions": actions,
    }


def pick_quotes(quotes: list[tuple[str, str]], limit: int = 6) -> list[tuple[str, str]]:
    """跨说话人轮流取，避免一人的金句霸榜。"""
    by_spk: dict[str, list[str]] = {}
    for q, spk in quotes:
        by_spk.setdefault(spk or "?", []).append(q)
    out, rounds = [], 0
    while len(out) < limit and rounds < 5:
        progressed = False
        for spk, qs in by_spk.items():
            if rounds < len(qs):
                out.append((qs[rounds], spk))
                progressed = True
                if len(out) >= limit:
                    break
        if not progressed:
            break
        rounds += 1
    return out


# ══════════════════════════════════════════════════════════════
# HTML 模板（暗色霓虹，与 repo 视觉一致）
# ══════════════════════════════════════════════════════════════
def esc(s: str) -> str:
    return _html.escape(s, quote=True)


def build_html(d: dict, chars: str = "") -> str:
    stats = []
    if d["n_spk"]:
        stats.append(f'{d["n_spk"]} 位说话人')
    if d["n_seg"]:
        stats.append(f'{d["n_seg"]} 段发言')
    if chars:
        stats.append(f"{chars}对话稿")
    stats_html = "".join(f'<span class="chip">{esc(s)}</span>' for s in stats)

    concl_html = ""
    for i, (head, body) in enumerate(d["conclusions"], 1):
        head_html = f'<b class="acc">{esc(head)}</b>：' if head else ""
        concl_html += (
            f'<div class="row"><span class="num">{i:02d}</span>'
            f'<p class="rowtext">{head_html}{esc(body)}</p></div>')

    quotes = pick_quotes(d["quotes"])
    quote_html = ""
    for q, spk in quotes:
        if "/" in spk:  # "A / Punk" → "Punk"
            spk = spk.split("/")[-1].strip()
        by = f'<span class="by">—— {esc(spk)}</span>' if spk and spk != "?" else ""
        quote_html += f'<div class="quote"><p>「{esc(q)}」</p>{by}</div>'

    act_html = "".join(f'<div class="act"><span class="arrow">→</span><p>{esc(a)}</p></div>'
                       for a in d["actions"])

    quotes_block = (f'<div class="sec"><h2>金句</h2>{quote_html}</div>'
                    if quote_html else "")
    act_block = (f'<div class="sec"><h2>可行动项</h2>{act_html}</div>'
                 if act_html else "")

    return f"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8"><style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html {{ background:#0B1120; }}
  body {{
    width:{WIDTH}px; font-family:'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif;
    color:#E8EEF7; background:
      radial-gradient(900px 500px at 12% -4%, rgba(34,211,238,.16), transparent 60%),
      radial-gradient(800px 600px at 96% 104%, rgba(129,140,248,.14), transparent 60%),
      #0B1120;
  }}
  .wrap {{ padding:64px 72px 56px; }}
  .top {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:44px; }}
  .brand {{ font-size:28px; font-weight:700; letter-spacing:.5px; }}
  .brand i {{ font-style:normal; color:#22D3EE; }}
  .tag {{ font-size:22px; color:#94A3B8; border:1px solid rgba(148,163,184,.35);
          padding:8px 18px; border-radius:999px; }}
  h1 {{ font-size:46px; line-height:1.38; font-weight:800; letter-spacing:.3px;
        background:linear-gradient(92deg,#F8FAFC 30%,#7DD3FC 85%);
        -webkit-background-clip:text; background-clip:text; color:transparent; }}
  .stats {{ margin:26px 0 8px; }}
  .chip {{ display:inline-block; font-size:22px; color:#A5F3FC; margin-right:12px;
           background:rgba(34,211,238,.10); border:1px solid rgba(34,211,238,.28);
           padding:7px 16px; border-radius:999px; }}
  .divider {{ height:1px; margin:34px 0 40px;
              background:linear-gradient(90deg, rgba(34,211,238,.75), rgba(129,140,248,.25), transparent); }}
  .sec {{ margin-bottom:44px; }}
  h2 {{ font-size:26px; color:#22D3EE; font-weight:700; letter-spacing:2px; margin-bottom:24px; }}
  h2::before {{ content:"◆ "; font-size:20px; }}
  .summary {{ font-size:34px; line-height:1.6; font-weight:600;
              background:rgba(45,212,191,.08); border-left:6px solid #2DD4BF;
              border-radius:0 18px 18px 0; padding:28px 32px; }}
  .row {{ display:flex; margin-bottom:22px; }}
  .num {{ color:#22D3EE; font-weight:800; font-size:28px; margin-right:18px; line-height:1.62;
          font-variant-numeric:tabular-nums; }}
  .rowtext {{ font-size:28px; line-height:1.62; color:#DCE6F2; }}
  .acc {{ color:#7DD3FC; }}
  .quote {{ background:rgba(148,163,184,.07); border:1px solid rgba(148,163,184,.16);
            border-radius:18px; padding:24px 30px; margin-bottom:20px; }}
  .quote p {{ font-size:31px; line-height:1.55; font-weight:600; color:#F1F5F9; }}
  .by {{ display:block; text-align:right; font-size:22px; color:#94A3B8; margin-top:10px; }}
  .act {{ display:flex; margin-bottom:18px; }}
  .arrow {{ color:#2DD4BF; font-size:28px; margin-right:14px; line-height:1.6; }}
  .act p {{ font-size:27px; line-height:1.6; color:#DCE6F2; }}
  .foot {{ margin-top:8px; padding-top:30px; border-top:1px solid rgba(148,163,184,.16);
           display:flex; justify-content:space-between; align-items:center; }}
  .foot .l {{ font-size:22px; color:#94A3B8; }}
  .foot .l b {{ color:#E2E8F0; font-weight:600; }}
  .piper {{ font-size:22px; color:#64748B; }}
</style></head><body><div class="wrap">
  <div class="top">
    <span class="brand">yaya<i>-</i>skills</span>
    <span class="tag">X Space → 干货笔记</span>
  </div>
  <h1>{esc(d['title'])}</h1>
  <div class="stats">{stats_html}</div>
  <div class="divider"></div>
  <div class="sec"><h2>一句话总结</h2><p class="summary">{esc(d['summary'])}</p></div>
  <div class="sec"><h2>核心结论</h2>{concl_html}</div>
  {quotes_block}
  {act_block}
  <div class="foot">
    <span class="l"><b>github.com/eatmoreduck/yaya-skills</b></span>
    <span class="piper">X 回放会过期，文字留档</span>
  </div>
</div>
<script>
window.addEventListener('load', function(){{
  document.title = 'H' + document.documentElement.scrollHeight;
}});
</script>
</body></html>"""


# ══════════════════════════════════════════════════════════════
# Chrome 两遍截图
# ══════════════════════════════════════════════════════════════
def capture(html_path: Path, out_png: Path) -> None:
    html_path = html_path.resolve()
    out_png = out_png.resolve()
    chrome = find_chrome()
    if not chrome:
        raise RuntimeError("未找到 Chrome/Chromium，无法出图")

    base = [chrome, "--headless", "--disable-gpu", "--hide-scrollbars",
            "--default-background-color=0B1120FF", "--no-first-run"]

    # 第一遍：跑 JS 量内容高度（写进 <title>）
    p1 = subprocess.run(
        base + ["--virtual-time-budget=4000", "--window-size=%d,900" % WIDTH,
                "--dump-dom", html_path.as_uri()],
        capture_output=True, text=True, timeout=120)
    m = re.search(r"<title>H(\d+)</title>", p1.stdout)
    height = int(m.group(1)) if m else 2600
    if not m:
        log(f"⚠️ 高度测量失败，回退 {height}px")

    # 第二遍：按精确高度截图
    p2 = subprocess.run(
        base + ["--virtual-time-budget=4000", f"--window-size={WIDTH},{height}",
                f"--screenshot={out_png}", html_path.as_uri()],
        capture_output=True, text=True, timeout=120)
    if not out_png.exists() or out_png.stat().st_size == 0:
        raise RuntimeError(f"截图失败: {p2.stderr[-400:]}")


def render(distilled_md: Path, out_png: Path | None = None,
           workdir: Path | None = None) -> Path:
    d = parse_distilled(distilled_md.read_text(encoding="utf-8"))
    chars = ""
    dialog = distilled_md.parent / "audio.dialog.txt"
    if dialog.exists():
        # 去掉 "A：" 说话人前缀后再计字数，与蒸馏统计口径一致
        body = "".join(re.sub(r"^[A-Z]+：", "", ln)
                       for ln in dialog.read_text(encoding="utf-8").splitlines() if ln.strip())
        n = len(body)
        chars = f"{n/10000:.1f} 万字" if n >= 10000 else f"{n} 字"
    h = build_html(d, chars=chars)
    workdir = (workdir or Path(tempfile.mkdtemp(prefix="yaya-card-"))).resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    html_path = workdir / (distilled_md.stem + ".card.html")
    html_path.write_text(h, encoding="utf-8")
    out_png = (out_png or distilled_md.with_suffix(".png")).resolve()
    t = time.time()
    capture(html_path, out_png)
    log(f"分享图已生成 {out_png.name} ({out_png.stat().st_size/1e6:.1f}MB, {time.time()-t:.0f}s)")
    return out_png


def main() -> int:
    ap = argparse.ArgumentParser(description="yaya-xspace：distilled.md → 分享图 PNG")
    ap.add_argument("md", help="distilled.md 路径")
    ap.add_argument("--out", type=Path, default=None, help="输出 PNG（默认同名 .png）")
    ap.add_argument("--workdir", type=Path, default=None, help="HTML 中间产物目录（默认临时目录）")
    args = ap.parse_args()
    md = Path(args.md).expanduser().resolve()
    if not md.exists():
        sys.exit(f"❌ 找不到 {md}")
    render(md, out_png=args.out, workdir=args.workdir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
