#!/usr/bin/env python3
"""
yaya-xspace 出图 —— 把 distilled.md 渲染成一张手绘风分享图（PNG）。

风格：自媒体手绘/白板风——米白纸底 + 马克笔黑线 + 陶土橙高亮 +
手写体（站酷庆科黄油体/站酷快乐体）+ 涂鸦与胶带便签。
（视觉语言参照 claude-motion-skill 的白板/手绘案例预览。）

流程：解析 distilled.md（一句话总结/核心结论/金句/可行动项）
   → 生成 HTML → Chrome headless 两遍截图（先量高度再精确出图）
   → 只留 <name>.png，HTML 中间产物进缓存目录（不污染输出）

说话人署名：自动兼容 "A / Punk"、"A（Punk，…）"、"Punk（A）" 等格式，
永远显示真名、绝不显示 ABCD 字母。

用法（distill.py 会自动调用；也可单独重渲染）:
    python3 card.py <distilled.md 路径> [--out PNG] [--workdir HTML存放目录]

依赖：本机 Chrome（或 Chromium）+ fonts/ 下的两款开源字体（OFL）。
找不到 Chrome 时优雅失败，不影响主流程。
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
SKILL_DIR = Path(__file__).resolve().parent
FONTS_DIR = SKILL_DIR / "fonts"
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
def _header_name(header: str) -> tuple[str, str | None]:
    """从说话人标题里提取 (真名, 字母)。兼容多种 LLM 输出格式：
      "A / Punk（前教师…）"、"A（Punk，自媒体…）"、"Punk（A）— 前教师…"、"铁柱哥"
    返回的真名可能为空串（只有字母时）。"""
    h = re.split(r"[—–]", header.strip())[0].strip()
    letter: str | None = None
    m = re.match(r"^([A-Za-z])\s*[/、]\s*(.+)$", h)            # A / Punk
    if m:
        letter, h = m.group(1), m.group(2)
    elif (m := re.match(r"^([A-Za-z])\s*[（(](.+)$", h)):      # A（Punk，…）
        letter, h = m.group(1), m.group(2)
    elif (m := re.match(r"^(.+?)\s*[（(]\s*([A-Za-z])\s*[）)]\s*$", h)):  # Punk（A）
        h, letter = m.group(1), m.group(2)
    elif (m := re.fullmatch(r"([A-Za-z])", h)):                 # 只有一个字母
        letter, h = m.group(1), ""
    name = re.split(r"[，,、（(]", h)[0].strip().rstrip("）) ").strip()
    if re.fullmatch(r"[A-Za-z]?", name):
        name = ""
    return name, letter


def parse_distilled(md_text: str) -> dict:
    lines = md_text.splitlines()

    def section_lines(name: str) -> list[str]:
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
    header = "\n".join(lines[:12])
    m_spk = re.search(r"说话人:\s*(\d+)", header)
    m_seg = re.search(r"段落:\s*(\d+)", header)

    def clean(s: str) -> str:
        s = s.strip()
        s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
        return s.replace("`", "").strip()

    # 一句话总结
    summary = ""
    for ln in section_lines("一句话总结"):
        if ln.strip():
            summary = clean(ln)
            break

    # 核心结论：兼容 "1. xxx" 与 "- xxx"
    conclusions = []
    for ln in section_lines("核心结论"):
        m = re.match(r"(?:\d+\.|[-*])\s*(.+)$", ln.strip())
        if not m:
            continue
        body = clean(m.group(1))
        mm = re.match(r"^(.{2,14}?)[：:](.+)$", body)
        conclusions.append((mm.group(1), mm.group(2)) if mm and "，" not in mm.group(1)
                           else ("", body))

    # 说话人标题两遍：先建 字母→真名 映射，再收集金句署名
    lmap: dict[str, str] = {}
    for ln in lines:
        hm = re.match(r"^\*\*(.+?)\*\*", ln)
        if hm:
            nm, lt = _header_name(hm.group(1))
            if lt and nm:
                lmap[lt] = nm

    def resolve(raw: str) -> str:
        nm, lt = _header_name(raw)
        return nm or (lmap.get(lt or "", "") if lt else "") or ""

    quotes_raw: list[tuple[str, str]] = []
    speaker_raw = ""
    seen = set()
    for ln in lines:
        hm = re.match(r"^\*\*(.+?)\*\*", ln)
        if hm:
            speaker_raw = hm.group(1)
        if "金句" in ln and "「" in ln:
            for q in re.findall(r"「([^」]{4,72})」", ln):
                q = q.strip()
                if "……" in q or q in seen:  # 残缺/自我更正的引文不上图
                    continue
                seen.add(q)
                quotes_raw.append((q, speaker_raw))
    quotes = [(q, resolve(raw)) for q, raw in quotes_raw]

    # 可行动项：同样兼容两种列表格式
    actions = []
    for ln in section_lines("可行动项"):
        m = re.match(r"(?:\d+\.|[-*])\s*(.+)$", ln.strip())
        if m:
            actions.append(clean(m.group(1)))

    return {
        "title": title,
        "n_spk": m_spk.group(1) if m_spk else "",
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
        by_spk.setdefault(spk or "？", []).append(q)
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
# HTML 模板（自媒体手绘/白板风）
# ══════════════════════════════════════════════════════════════
def esc(s: str) -> str:
    return _html.escape(s, quote=True)


# 手绘涂鸦（内联 SVG，墨线圆头）
_DOODLE = {
    "bulb": "<svg class='doodle' viewBox='0 0 64 64'><circle cx='30' cy='26' r='15'/>"
            "<path d='M24 41h12M26 47h8'/><path d='M30 4v5M48 10l-4 4M52 30h5M8 12l5 4M6 32h5'/>"
            "<path d='M24 20q6-6 12 0'/></svg>",
    "duck": "<svg class='doodle' viewBox='0 0 76 62'><circle cx='48' cy='17' r='9'/>"
            "<path d='M56 15l12 4-12 5'/><path d='M12 46c0-8 10-13 22-12 8 1 14 5 14 11 0 7-10 11-22 11S12 52 12 46z'/>"
            "<path d='M24 45q8-4 16 0'/><circle cx='50' cy='15' r='1.6' fill='currentColor' stroke='none'/></svg>",
    "check": "<svg class='check' viewBox='0 0 40 40'><path d='M8 12q12-3 24-1 1 10 0 20-12 2-24 1-1-10 0-20z'/>"
             "<path d='M12 22l7 7 10-13'/></svg>",
    "underline": "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='150' height='12'><path d='M3 7 Q 22 2 40 7 T 76 7 T 112 7 T 147 6' stroke='%23D96F32' stroke-width='5' fill='none' stroke-linecap='round'/></svg>\")",
    "wave": "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='120' height='10'><path d='M2 5 Q 17 1 32 5 T 62 5 T 92 5 T 122 5' stroke='%23B9AFA0' stroke-width='3.5' fill='none' stroke-linecap='round'/></svg>\")",
}

_GHOSTS = """
<svg class="ghost" style="top:120px;right:-30px;width:150px" viewBox="0 0 120 120">
  <circle cx="60" cy="60" r="42"/><path d="M40 58q20 14 40 0"/></svg>
<svg class="ghost" style="top:920px;left:-40px;width:130px" viewBox="0 0 100 100">
  <path d="M10 70 q20 -50 40 -20 q20 30 40 -20"/></svg>
<svg class="ghost" style="bottom:340px;right:-20px;width:120px" viewBox="0 0 100 100">
  <path d="M50 8v20M50 72v20M8 50h20M72 50h20M20 20l14 14M66 66l14 14M80 20L66 34M34 66L20 80"/></svg>
<svg class="ghost" style="top:2100px;left:-24px;width:110px" viewBox="0 0 90 90">
  <path d="M8 30 q18 -22 36 -6 q18 -22 36 6" /><path d="M20 60 h50"/></svg>
"""

_GRAIN = ("url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='240' height='240'>"
          "<filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='2' stitchTiles='stitch'/>"
          "<feColorMatrix type='saturate' values='0'/></filter>"
          "<rect width='240' height='240' filter='url(%23n)' opacity='0.55'/></svg>\")")


def build_html(d: dict, chars: str = "") -> str:
    stats = []
    if d["n_spk"]:
        stats.append(f'{d["n_spk"]} 位说话人')
    if d["n_seg"]:
        stats.append(f'{d["n_seg"]} 段发言')
    if chars:
        stats.append(f"{chars}对话稿")
    stats_html = "".join(f'<span class="tag w{i%3+1}">{esc(s)}</span>'
                         for i, s in enumerate(stats))

    # 标题里的引号内容做荧光笔高亮
    title_html = esc(d["title"])
    title_html = re.sub(r"([「“])([^」”]{1,14})([」”])",
                        r"\1<span class='hl'>\2</span>\3", title_html)

    concl_html = ""
    for i, (head, body) in enumerate(d["conclusions"], 1):
        head_html = f'<b>{esc(head)}</b>：' if head else ""
        concl_html += (f'<div class="row"><span class="num w{i%3+1}">{i:02d}</span>'
                       f'<p class="rowtext">{head_html}{esc(body)}</p></div>')

    quotes = pick_quotes(d["quotes"])
    NOTE_TINTS = ["#FBF2C4", "#E9F2E3", "#FBE5DB", "#E8EFF7"]
    quote_html = ""
    for i, (q, spk) in enumerate(quotes):
        tint = NOTE_TINTS[i % len(NOTE_TINTS)]
        rot = [-0.7, 0.5, -0.4, 0.6][i % 4]
        by = f'<span class="by">—— {esc(spk)}</span>' if spk and spk != "？" else ""
        quote_html += (f'<div class="quote" style="background:{tint};transform:rotate({rot}deg)">'
                       f'<p>「{esc(q)}」</p>{by}</div>')

    act_html = "".join(f'<div class="act">{_DOODLE["check"]}<p>{esc(a)}</p></div>'
                       for a in d["actions"])

    quotes_block = (f'<div class="sec"><h2>金句</h2>{quote_html}</div>'
                    if quote_html else "")
    act_block = (f'<div class="sec"><h2>可行动项</h2>{act_html}</div>'
                 if act_html else "")

    return f"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8"><style>
  @font-face {{ font-family:'QK'; src:url('ZCOOLQingKeHuangYou-Regular.ttf'); }}
  @font-face {{ font-family:'KL'; src:url('ZCOOLKuaiLe-Regular.ttf'); }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html {{ background:#F5F1E8; }}
  body {{
    width:{WIDTH}px; color:#2B2622; position:relative; overflow:hidden;
    font-family:'KL','PingFang SC',sans-serif;
    background:#F5F1E8;
  }}
  body::after {{ content:""; position:absolute; inset:0; pointer-events:none;
    background:{_GRAIN} repeat; opacity:.5; mix-blend-mode:multiply; }}
  .ghost {{ position:absolute; fill:none; stroke:#2B2622; stroke-width:3.5;
    stroke-linecap:round; opacity:.06; }}
  .wrap {{ position:relative; padding:58px 64px 52px; }}
  .top {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:40px; }}
  .brand {{ display:flex; align-items:center; gap:14px;
    font-family:'QK','PingFang SC',sans-serif; font-size:34px; letter-spacing:1px; }}
  .brand .doodle {{ width:56px; height:46px; color:#2B2622; }}
  .pill {{ font-size:23px; padding:9px 22px; background:#FFFDF6;
    border:3px solid #2B2622; border-radius:205px 20px 220px 18px / 18px 210px 20px 215px; }}
  h1 {{ font-family:'QK','PingFang SC',sans-serif; font-size:54px; line-height:1.42;
    font-weight:400; letter-spacing:1px; }}
  .hl {{ background:linear-gradient(transparent 55%, rgba(240,168,92,.65) 55%); padding:0 2px; }}
  .stats {{ margin:28px 0 6px; }}
  .tag {{ display:inline-block; font-size:23px; margin-right:14px;
    padding:8px 20px; background:#FFFDF6; border:3px solid #2B2622; }}
  .w1 {{ border-radius:225px 18px 205px 20px / 20px 205px 18px 225px; }}
  .w2 {{ border-radius:18px 220px 20px 200px / 210px 18px 225px 18px; }}
  .w3 {{ border-radius:205px 20px 220px 18px / 18px 210px 20px 215px; }}
  .divider {{ height:10px; margin:36px 0 44px; background:{_DOODLE["wave"]} repeat-x left center; }}
  .sec {{ margin-bottom:50px; }}
  h2 {{ display:inline-block; font-family:'QK','PingFang SC',sans-serif; font-size:36px;
    font-weight:400; letter-spacing:3px; padding-bottom:14px; margin-bottom:28px;
    background:{_DOODLE["underline"]} no-repeat left bottom / 150px 12px; }}
  .bubble {{ display:flex; gap:22px; align-items:flex-start; background:#FFFDF6;
    border:4px solid #2B2622; border-radius:225px 22px 210px 24px / 24px 205px 22px 225px;
    padding:30px 34px; }}
  .bubble .doodle {{ width:56px; height:56px; flex:none; color:#D96F32; margin-top:4px; }}
  .bubble p {{ font-size:33px; line-height:1.7; font-weight:600; }}
  .row {{ display:flex; margin-bottom:24px; align-items:flex-start; }}
  .num {{ flex:none; width:64px; height:64px; margin-right:20px; line-height:58px;
    text-align:center; font-family:'QK','PingFang SC',sans-serif; font-size:32px;
    color:#2B2622; background:#F0A85C; border:4px solid #2B2622; }}
  .rowtext {{ font-size:29px; line-height:1.72; padding-top:6px; }}
  .quote {{ position:relative; border:4px solid #2B2622;
    border-radius:220px 24px 210px 26px / 26px 210px 24px 220px;
    padding:30px 36px 24px; margin:0 10px 26px; }}
  .quote::before {{ content:""; position:absolute; top:-16px; left:50%; width:130px; height:32px;
    transform:translateX(-50%) rotate(-3deg);
    background:linear-gradient(rgba(226,196,110,.6), rgba(226,196,110,.45));
    border-left:2px dashed rgba(150,120,50,.35); border-right:2px dashed rgba(150,120,50,.35); }}
  .quote p {{ font-size:33px; line-height:1.62; font-weight:600; }}
  .by {{ display:block; text-align:right; font-size:23px; color:#7A7168; margin-top:12px; }}
  .act {{ display:flex; align-items:flex-start; margin-bottom:20px; }}
  .check {{ flex:none; width:44px; height:44px; margin-right:16px; margin-top:4px;
    fill:none; stroke:#D96F32; stroke-width:4; stroke-linecap:round; stroke-linejoin:round; }}
  .act p {{ font-size:28px; line-height:1.72; }}
  .foot {{ padding-top:30px; background:{_DOODLE["wave"]} repeat-x left top / 120px 10px;
    display:flex; justify-content:space-between; align-items:center; }}
  .foot .l {{ display:flex; align-items:center; gap:12px;
    font-family:'QK','PingFang SC',sans-serif; font-size:26px; letter-spacing:.5px; }}
  .foot .l .doodle {{ width:46px; height:38px; color:#2B2622; }}
  .foot .r {{ font-size:22px; color:#7A7168; }}
  .doodle {{ fill:none; stroke:currentColor; stroke-width:4; stroke-linecap:round; stroke-linejoin:round; }}
</style></head><body>
{_GHOSTS}
<div class="wrap">
  <div class="top">
    <span class="brand">{_DOODLE["duck"]}yaya-skills</span>
    <span class="pill">X Space → 干货笔记</span>
  </div>
  <h1>{title_html}</h1>
  <div class="stats">{stats_html}</div>
  <div class="divider"></div>
  <div class="sec"><h2>一句话总结</h2><div class="bubble">{_DOODLE["bulb"]}<p>{esc(d['summary'])}</p></div></div>
  <div class="sec"><h2>核心结论</h2>{concl_html}</div>
  {quotes_block}
  {act_block}
  <div class="foot">
    <span class="l">{_DOODLE["duck"]}github.com/eatmoreduck/yaya-skills</span>
    <span class="r">X 回放会过期，文字留档</span>
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
            "--default-background-color=F5F1E8FF", "--no-first-run"]

    # 第一遍：跑 JS 量内容高度（写进 <title>）
    p1 = subprocess.run(
        base + ["--virtual-time-budget=5000", "--window-size=%d,900" % WIDTH,
                "--dump-dom", html_path.as_uri()],
        capture_output=True, text=True, timeout=120)
    m = re.search(r"<title>H(\d+)</title>", p1.stdout)
    height = int(m.group(1)) if m else 2600
    if not m:
        log(f"⚠️ 高度测量失败，回退 {height}px")

    # 第二遍：按精确高度截图
    p2 = subprocess.run(
        base + ["--virtual-time-budget=5000", f"--window-size={WIDTH},{height}",
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
    # 字体拷到 HTML 同目录（相对引用，headless 可直接加载）
    if FONTS_DIR.exists():
        for f in FONTS_DIR.glob("*.ttf"):
            shutil.copy2(f, workdir / f.name)
    html_path = workdir / (distilled_md.stem + ".card.html")
    html_path.write_text(h, encoding="utf-8")
    out_png = (out_png or distilled_md.with_suffix(".png")).resolve()
    t = time.time()
    capture(html_path, out_png)
    log(f"分享图已生成 {out_png.name} ({out_png.stat().st_size/1e6:.1f}MB, {time.time()-t:.0f}s)")
    return out_png


def main() -> int:
    ap = argparse.ArgumentParser(description="yaya-xspace：distilled.md → 手绘风分享图 PNG")
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
