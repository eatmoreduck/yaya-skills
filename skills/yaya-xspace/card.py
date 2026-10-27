#!/usr/bin/env python3
"""
yaya-xspace 出图 —— 把 distilled.md 渲染成一张设计好的分享图（PNG）。

内置多种风格（视觉语言参照 claude-motion-skill 的案例预览）：
  swiss      瑞士国际主义：白底 + 重磅黑体 + 红色点缀 + 细线网格
  editorial  杂志/新闻纸：米白 + 宋体大标题 + 朱红方块 + 双线报头
  riso       双色丝印海报：牛皮纸 + 靛蓝/荧光橙 + 网点 + 套印错位
  midnight   暗色金标题（夜读版）：墨黑底 + 宋体 + 鎏金细线
  hand       手绘白板风：纸底 + 马克笔线 + 便签（早期实验款）

流程：解析 distilled.md（一句话总结/核心结论/金句/可行动项）
   → 生成 HTML → Chrome headless 两遍截图（先量高度再精确出图）
   → 只留 <name>.png，HTML 中间产物进缓存目录（不污染输出）

说话人署名：自动兼容 "A / Punk"、"A（Punk，…）"、"Punk（A）" 等格式，
永远显示真名、绝不显示 ABCD 字母。

用法（distill.py 会自动调用；也可单独重渲染）:
    python3 card.py <distilled.md 路径> [--style editorial] [--out PNG] [--workdir DIR]

依赖：本机 Chrome（或 Chromium）；hand 风格另需 fonts/ 下的开源手写体（OFL）。
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
STYLES = ("swiss", "editorial", "riso", "midnight", "hand")
STYLE_BG = {
    "swiss": "#F1F0EC",
    "editorial": "#F8F4EA",
    "riso": "#F4EDDF",
    "midnight": "#131109",
    "hand": "#F5F1E8",
}
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
        "lmap": lmap,
    }


def _dename(text: str, lmap: dict[str, str]) -> str:
    """把正文括号里的单字母指代（C、E、A 一致主张）换成真名——图上永不出现 ABCD。"""
    def sub_group(m: re.Match) -> str:
        def sub_letter(lm: re.Match) -> str:
            name = lmap.get(lm.group(0), "")
            # 花名可能带备选（文字姐/蚊子姐）→ 图上取第一个
            return re.split(r"[+/、，,]", name)[0].strip() if name else lm.group(0)
        # 前后边界都必须排掉中文：`Domby Seven（东B赛兰/多姆比Seven）` 里的 B 是名字
        # 的一部分（东B赛兰是一个 IP 名），只排英文会把中文相邻的字母也换掉，把
        # 「东B赛兰」改成「东胖姐赛兰」——真实事故。
        # 后置还要排掉画像分类词：`（A类30岁）` 里的 A 指用户画像，换成真名就毁原意。
        return re.sub(r"(?<![A-Za-z一-鿿])[A-Z](?![A-Za-z类组档种])",
                      sub_letter, m.group(0))
    out = re.sub(r"[（(][^）)]{1,60}[）)]", sub_group, text)
    # 替换后可能出现 "Ringo/Ringo" 这类重复，去重
    return re.sub(r"([\u4e00-\u9fffA-Za-z0-9]{2,})/\1", r"\1", out)


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
# 公共小工具
# ══════════════════════════════════════════════════════════════
def esc(s: str) -> str:
    return _html.escape(s, quote=True)


CN_NUM = "一二三四五六七八九十"


def _stats(d: dict, chars: str) -> list[str]:
    s = []
    if d["n_spk"]:
        s.append(f'{d["n_spk"]} 位说话人')
    if d["n_seg"]:
        s.append(f'{d["n_seg"]} 段发言')
    if chars:
        s.append(f"{chars}对话稿")
    return s


def _hl(title: str, cls: str = "hl") -> str:
    """标题里的引号内容做强调。"""
    t = esc(title)
    return re.sub(r"([「“])([^」”]{1,14})([」”])", rf"\1<span class='{cls}'>\2</span>\3", t)


def _concl_rows(d: dict, idx_fn, head_open="<b>", head_close="</b>") -> str:
    out = ""
    for i, (head, body) in enumerate(d["conclusions"], 1):
        h = f"{head_open}{esc(head)}{head_close}：" if head else ""
        out += idx_fn(i, f'{h}{esc(body)}')
    return out


def _quote_blocks(quotes, p_open, p_close, by_html) -> str:
    out = ""
    for q, spk in quotes:
        out += (f'{p_open}'
                f'<span class="qm">「</span>{esc(q)}<span class="qm">」</span>'
                f'{by_html(esc(spk) if spk and spk != "？" else "")}'
                f'{p_close}')
    return out


# ══════════════════════════════════════════════════════════════
# 风格四选一（+手绘旧款）—— 每个模板用 [[TOKEN]] 占位，避免 f-string 转义
# ══════════════════════════════════════════════════════════════
def _fill(tpl: str, **kw) -> str:
    for k, v in kw.items():
        tpl = tpl.replace(f"[[{k}]]", v)
    return tpl


_SWISS = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8"><style>
*{margin:0;padding:0;box-sizing:border-box}
html{background:#F1F0EC}
body{width:1080px;background:#F1F0EC;color:#101010;
 font-family:'Helvetica Neue','Hiragino Sans GB','Heiti SC','PingFang SC',sans-serif;}
.wrap{position:relative;padding:64px 76px 0}
.waves{position:absolute;top:172px;right:76px;width:150px;height:150px;
 background:radial-gradient(circle at 100% 0%,transparent 33px,#E02B20 33px 42px,transparent 42px),
 radial-gradient(circle at 100% 0%,transparent 61px,#E02B20 61px 70px,transparent 70px),
 radial-gradient(circle at 100% 0%,transparent 89px,#E02B20 89px 98px,transparent 98px);}
.waves::after{content:"";position:absolute;top:2px;right:2px;width:15px;height:15px;border-radius:50%;background:#E02B20;}
.top{display:flex;justify-content:space-between;align-items:center;font-size:21px;font-weight:700;letter-spacing:2.5px}
.top .r{opacity:.72}
.hairline{height:1px;background:#101010;margin-top:26px}
h1{font-size:62px;line-height:1.24;font-weight:900;letter-spacing:-.5px;margin:52px 0 26px;max-width:760px}
h1 .hl{color:#E02B20}
.meta{font-size:23px;letter-spacing:1px;font-weight:600;opacity:.62}
.sec{margin-top:54px}
.sechead{display:flex;align-items:baseline;gap:18px;border-bottom:1px solid #101010;padding-bottom:15px;margin-bottom:30px}
.idx{color:#E02B20;font-weight:800;font-size:24px;letter-spacing:1px;font-variant-numeric:tabular-nums}
h2{font-size:30px;font-weight:900;letter-spacing:2px}
.summary{font-size:36px;line-height:1.62;font-weight:500}
.row{display:flex;gap:8px;margin-bottom:24px}
.row .idx{font-size:25px;padding-top:7px;min-width:46px}
.row p{font-size:28px;line-height:1.64;font-weight:500}
.qpx{border-top:1px solid #101010;padding:24px 0 16px}
.qpx p{font-size:32px;font-weight:800;line-height:1.5}
.by{display:block;margin-top:12px;font-size:21px;opacity:.55;font-weight:600;letter-spacing:1px}
.act{display:flex;gap:18px;margin-bottom:20px}
.act .box{flex:none;width:20px;height:20px;border:2.5px solid #101010;margin-top:10px}
.act p{font-size:27px;line-height:1.62;font-weight:500}
.foot{margin-top:66px;border-top:1px solid #101010;padding:22px 0 26px;
 display:flex;justify-content:space-between;font-size:20px;font-weight:600;letter-spacing:1.5px}
.dot{display:inline-block;width:12px;height:12px;border-radius:50%;background:#E02B20;margin-right:10px}
</style></head><body><div class="wrap">
<div class="waves"></div>
<div class="top"><span>eatmoreduck 多吃鸭 · yaya-skills</span><span class="r">X SPACE → 干货笔记</span></div>
<div class="hairline"></div>
<h1>[[TITLE]]</h1>
<p class="meta">[[STATS]]</p>
<div class="sec"><div class="sechead"><span class="idx">01</span><h2>一句话总结</h2></div>
<p class="summary">[[SUMMARY]]</p></div>
<div class="sec"><div class="sechead"><span class="idx">02</span><h2>核心结论</h2></div>
[[CONCL]]</div>
<div class="sec"><div class="sechead"><span class="idx">03</span><h2>金句</h2></div>
[[QUOTES]]</div>
<div class="sec"><div class="sechead"><span class="idx">04</span><h2>可行动项</h2></div>
[[ACTS]]</div>
<div class="foot"><span><span class="dot"></span>github.com/eatmoreduck/yaya-skills</span><span>X 回放会过期 · 文字留档</span></div>
</div><script>
window.addEventListener('load', function(){
  document.title = 'H' + document.documentElement.scrollHeight;
});
</script></body></html>"""


_EDITORIAL = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8"><style>
*{margin:0;padding:0;box-sizing:border-box}
html{background:#F8F4EA}
body{width:1080px;background:#F8F4EA;color:#1B1B1B;font-family:'Songti SC','STSong','Times New Roman',serif;}
.wrap{padding:56px 76px 0}
.masthead{display:flex;justify-content:space-between;font-size:21px;font-weight:700;letter-spacing:3px;
 border-bottom:3px solid #1B1B1B;padding-bottom:12px;position:relative}
.masthead:after{content:"";position:absolute;left:0;right:0;bottom:-7px;height:1px;background:#1B1B1B}
h1{font-size:60px;font-weight:900;line-height:1.3;letter-spacing:1px;margin:56px 0 24px}
h1 .hl{border-bottom:6px solid #A62F26;padding-bottom:2px}
.meta{font-size:23px;color:#6B6459;letter-spacing:1px}
.sec{margin-top:48px;border-top:1px solid #D8CFBC;padding-top:26px}
h2{font-size:31px;font-weight:900;letter-spacing:3px}
h2:before{content:"■";color:#A62F26;font-size:19px;margin-right:14px;vertical-align:2px}
.summary{font-size:36px;line-height:1.8;font-weight:600;margin-top:24px}
.qm{color:#A62F26}
.row{display:flex;gap:16px;margin-bottom:20px}
.row .cn{color:#A62F26;font-weight:900;font-size:33px;line-height:1.62;min-width:46px}
.row p{font-size:29px;line-height:1.72;font-weight:600}
.qpx{border-top:1px solid #D8CFBC;border-bottom:1px solid #D8CFBC;padding:26px 6px;margin-bottom:2px}
.qpx p{font-size:32px;font-weight:700;line-height:1.62}
.by{display:block;text-align:right;margin-top:12px;font-size:21px;color:#8A8171;letter-spacing:1px}
.act{display:flex;gap:16px;margin-bottom:18px}
.act .cb{color:#A62F26;font-size:27px;font-weight:900;line-height:1.66;min-width:30px}
.act p{font-size:28px;line-height:1.72;font-weight:600}
.foot{margin-top:62px;border-top:3px solid #1B1B1B;padding:18px 0 26px;position:relative;
 display:flex;justify-content:space-between;font-size:20px;letter-spacing:2px;color:#6B6459}
.foot:after{content:"";position:absolute;left:0;right:0;top:6px;height:1px;background:#1B1B1B}
</style></head><body><div class="wrap">
<div class="masthead"><span>eatmoreduck 多吃鸭 · yaya-skills</span><span>X SPACE EDITION</span></div>
<h1>[[TITLE]]</h1>
<p class="meta">[[STATS]]</p>
<div class="sec"><h2>一句话总结</h2>
<p class="summary"><span class="qm">「</span>[[SUMMARY]]<span class="qm">」</span></p></div>
<div class="sec"><h2>核心结论</h2>
[[CONCL]]</div>
<div class="sec"><h2>金句</h2>
[[QUOTES]]</div>
<div class="sec"><h2>可行动项</h2>
[[ACTS]]</div>
<div class="foot"><span>github.com/eatmoreduck/yaya-skills</span><span>X 回放会过期 · 文字留档</span></div>
</div><script>
window.addEventListener('load', function(){
  document.title = 'H' + document.documentElement.scrollHeight;
});
</script></body></html>"""


_RISO = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8"><style>
*{margin:0;padding:0;box-sizing:border-box}
html{background:#F4EDDF}
body{width:1080px;background:#F4EDDF;color:#1D2433;position:relative;
 font-family:'Hiragino Sans GB','Heiti SC','PingFang SC',sans-serif;}
body:after{content:"";position:absolute;inset:0;pointer-events:none;opacity:.4;mix-blend-mode:multiply;
 background:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='240' height='240'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='2' stitchTiles='stitch'/><feColorMatrix type='saturate' values='0'/></filter><rect width='240' height='240' filter='url(%23n)' opacity='0.5'/></svg>") repeat;}
.half{position:absolute;width:260px;height:260px;opacity:.26;
 background-image:radial-gradient(#21387F 2.4px, transparent 2.9px);background-size:16px 16px;
 -webkit-mask-image:linear-gradient(135deg,#000 30%,transparent 78%);
         mask-image:linear-gradient(135deg,#000 30%,transparent 78%);}
.half.tl{top:0;left:0}
.half.br{bottom:0;right:0;transform:rotate(180deg)}
.wrap{position:relative;padding:60px 72px 0}
.top{display:flex;justify-content:space-between;font-size:22px;font-weight:700;letter-spacing:2px;color:#21387F}
h1{font-size:60px;line-height:1.26;font-weight:800;color:#1F2B4D;margin:48px 0 24px;letter-spacing:.5px;
 text-shadow:4px 4px 0 rgba(255,77,46,.85)}
h1 .hl{color:#21387F}
.meta{font-size:23px;color:#4A5570;font-weight:600}
.sec{margin-top:54px}
h2{display:inline-block;background:#21387F;color:#F7F1E3;padding:10px 26px;font-size:27px;
 letter-spacing:6px;font-weight:700;box-shadow:6px 6px 0 rgba(255,77,46,.9);margin-bottom:30px}
.summary{font-size:35px;line-height:1.68;font-weight:700;background:#FBF6EA;border:3px solid #21387F;
 padding:28px 32px;box-shadow:9px 9px 0 rgba(255,77,46,.85)}
.row{display:flex;gap:6px;margin-bottom:24px}
.num{font-size:29px;font-weight:800;color:#FF4D2E;min-width:54px;padding-top:6px;letter-spacing:1px}
.row p{font-size:28px;line-height:1.66;font-weight:600;color:#232B3E}
.qpx{background:rgba(33,56,127,.07);border-left:9px solid #FF4D2E;padding:26px 32px;margin-bottom:22px}
.qpx p{font-size:32px;font-weight:700;line-height:1.55;color:#1D2433}
.qpx .qm{color:#FF4D2E}
.by{display:block;margin-top:12px;text-align:right;font-size:21px;color:#5A6480;font-weight:600}
.act{display:flex;gap:16px;margin-bottom:20px}
.act .sq{flex:none;width:20px;height:20px;background:#21387F;margin-top:10px;box-shadow:3px 3px 0 rgba(255,77,46,.9)}
.act p{font-size:27px;line-height:1.64;font-weight:600;color:#232B3E}
.foot{margin:66px -72px 0;background:#21387F;color:#F7F1E3;border-top:8px solid #FF4D2E;
 display:flex;justify-content:space-between;padding:22px 76px;font-size:22px;font-weight:700;letter-spacing:1px}
</style></head><body>
<div class="half tl"></div><div class="half br"></div>
<div class="wrap">
<div class="top"><span>eatmoreduck 多吃鸭 · yaya-skills</span><span>X SPACE → 干货笔记</span></div>
<h1>[[TITLE]]</h1>
<p class="meta">[[STATS]]</p>
<div class="sec"><h2>一句话总结</h2>
<p class="summary">[[SUMMARY]]</p></div>
<div class="sec"><h2>核心结论</h2>
[[CONCL]]</div>
<div class="sec"><h2>金句</h2>
[[QUOTES]]</div>
<div class="sec"><h2>可行动项</h2>
[[ACTS]]</div>
</div>
<div class="foot"><span>github.com/eatmoreduck/yaya-skills</span><span>X 回放会过期 · 文字留档</span></div>
<script>
window.addEventListener('load', function(){
  document.title = 'H' + document.documentElement.scrollHeight;
});
</script>
</body></html>"""


_MIDNIGHT = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8"><style>
*{margin:0;padding:0;box-sizing:border-box}
html{background:#131109}
body{width:1080px;background:radial-gradient(1100px 520px at 18% -4%,#1D1A12,#131109 68%);
 color:#EDE6D6;font-family:'Songti SC','STSong','Times New Roman',serif;}
.wrap{padding:60px 76px 0}
.top{display:flex;justify-content:space-between;font-size:21px;letter-spacing:3px;color:#B9AE95;font-weight:700}
.goldrule{height:2px;background:linear-gradient(90deg,#C9A227,rgba(201,162,39,.06));margin-top:26px}
h1{font-size:56px;line-height:1.34;font-weight:900;color:#F6F0E0;margin:50px 0 24px;letter-spacing:1px}
h1 .hl{color:#C9A227}
.meta{font-size:23px;color:#9A917F;letter-spacing:1px}
.sec{margin-top:50px;border-top:1px solid rgba(201,162,39,.35);padding-top:26px}
h2{font-size:29px;font-weight:900;color:#C9A227;letter-spacing:6px}
.summary{font-size:35px;line-height:1.75;color:#F2EBDC;margin-top:24px}
.qm{color:#C9A227}
.row{display:flex;gap:6px;margin-bottom:22px}
.num{color:#C9A227;font-weight:900;font-size:29px;min-width:50px;padding-top:6px}
.row p{font-size:28px;line-height:1.68;color:#E4DCC9}
.qpx{border:1px solid rgba(201,162,39,.45);background:rgba(201,162,39,.05);padding:26px 32px;margin-bottom:20px}
.qpx p{font-size:31px;line-height:1.6;color:#F4EEDD}
.by{display:block;text-align:right;margin-top:12px;font-size:21px;color:#9A917F}
.act{display:flex;gap:16px;margin-bottom:20px}
.act .ar{color:#C9A227;font-size:26px;line-height:1.64;min-width:30px}
.act p{font-size:27px;line-height:1.68;color:#E4DCC9}
.foot{margin-top:62px;border-top:1px solid rgba(201,162,39,.35);padding:22px 0 26px;
 display:flex;justify-content:space-between;font-size:20px;letter-spacing:1px;color:#8C836E}
.foot b{color:#C9A227}
</style></head><body><div class="wrap">
<div class="top"><span>eatmoreduck 多吃鸭 · yaya-skills</span><span>X SPACE → 干货笔记</span></div>
<div class="goldrule"></div>
<h1>[[TITLE]]</h1>
<p class="meta">[[STATS]]</p>
<div class="sec"><h2>一句话总结</h2>
<p class="summary"><span class="qm">「</span>[[SUMMARY]]<span class="qm">」</span></p></div>
<div class="sec"><h2>核心结论</h2>
[[CONCL]]</div>
<div class="sec"><h2>金句</h2>
[[QUOTES]]</div>
<div class="sec"><h2>可行动项</h2>
[[ACTS]]</div>
<div class="foot"><span>github.com/eatmoreduck/<b>yaya-skills</b></span><span>X 回放会过期 · 文字留档</span></div>
</div><script>
window.addEventListener('load', function(){
  document.title = 'H' + document.documentElement.scrollHeight;
});
</script></body></html>"""


# ── 手绘风（早期实验款，保留） ──────────────────────────────
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
_GRAIN = ("url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='240' height='240'>"
          "<filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='2' stitchTiles='stitch'/>"
          "<feColorMatrix type='saturate' values='0'/></filter>"
          "<rect width='240' height='240' filter='url(%23n)' opacity='0.55'/></svg>\")")


def _html_hand(d: dict, st: list[str], title_html: str) -> str:
    stats_html = "".join(f'<span class="tag w{i%3+1}">{esc(s)}</span>'
                         for i, s in enumerate(st))
    concl_html = _concl_rows(d, lambda i, body:
                             f'<div class="row"><span class="num w{i%3+1}">{i:02d}</span>'
                             f'<p class="rowtext">{body}</p></div>')
    NOTE_TINTS = ["#FBF2C4", "#E9F2E3", "#FBE5DB", "#E8EFF7"]
    quote_html = ""
    for i, (q, spk) in enumerate(pick_quotes(d["quotes"])):
        tint = NOTE_TINTS[i % len(NOTE_TINTS)]
        rot = [-0.7, 0.5, -0.4, 0.6][i % 4]
        by = f'<span class="by">—— {esc(spk)}</span>' if spk and spk != "？" else ""
        quote_html += (f'<div class="quote" style="background:{tint};transform:rotate({rot}deg)">'
                       f'<p>「{esc(q)}」</p>{by}</div>')
    act_html = "".join(f'<div class="act">{_DOODLE["check"]}<p>{esc(a)}</p></div>'
                       for a in d["actions"])
    tpl = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8"><style>
  @font-face { font-family:'QK'; src:url('ZCOOLQingKeHuangYou-Regular.ttf'); }
  @font-face { font-family:'KL'; src:url('ZCOOLKuaiLe-Regular.ttf'); }
  * { margin:0; padding:0; box-sizing:border-box; }
  html { background:#F5F1E8; }
  body { width:1080px; color:#2B2622; position:relative; overflow:hidden;
    font-family:'KL','PingFang SC',sans-serif; background:#F5F1E8; }
  body::after { content:""; position:absolute; inset:0; pointer-events:none;
    background:[[GRAIN]] repeat; opacity:.5; mix-blend-mode:multiply; }
  .wrap { position:relative; padding:58px 64px 52px; }
  .top { display:flex; justify-content:space-between; align-items:center; margin-bottom:40px; }
  .brand { display:flex; align-items:center; gap:14px;
    font-family:'QK','PingFang SC',sans-serif; font-size:34px; letter-spacing:1px; }
  .brand .doodle { width:56px; height:46px; color:#2B2622; }
  .pill { font-size:23px; padding:9px 22px; background:#FFFDF6;
    border:3px solid #2B2622; border-radius:205px 20px 220px 18px / 18px 210px 20px 215px; }
  h1 { font-family:'QK','PingFang SC',sans-serif; font-size:54px; line-height:1.42;
    font-weight:400; letter-spacing:1px; }
  .hl { background:linear-gradient(transparent 55%, rgba(240,168,92,.65) 55%); padding:0 2px; }
  .stats { margin:28px 0 6px; }
  .tag { display:inline-block; font-size:23px; margin-right:14px;
    padding:8px 20px; background:#FFFDF6; border:3px solid #2B2622; }
  .w1 { border-radius:225px 18px 205px 20px / 20px 205px 18px 225px; }
  .w2 { border-radius:18px 220px 20px 200px / 210px 18px 225px 18px; }
  .w3 { border-radius:205px 20px 220px 18px / 18px 210px 20px 215px; }
  .divider { height:10px; margin:36px 0 44px; background:[[WAVE]] repeat-x left center; }
  .sec { margin-bottom:50px; }
  h2 { display:inline-block; font-family:'QK','PingFang SC',sans-serif; font-size:36px;
    font-weight:400; letter-spacing:3px; padding-bottom:14px; margin-bottom:28px;
    background:[[ULINE]] no-repeat left bottom / 150px 12px; }
  .bubble { display:flex; gap:22px; align-items:flex-start; background:#FFFDF6;
    border:4px solid #2B2622; border-radius:225px 22px 210px 24px / 24px 205px 22px 225px;
    padding:30px 34px; }
  .bubble .doodle { width:56px; height:56px; flex:none; color:#D96F32; margin-top:4px; }
  .bubble p { font-size:33px; line-height:1.7; font-weight:600; }
  .row { display:flex; margin-bottom:24px; align-items:flex-start; }
  .num { flex:none; width:64px; height:64px; margin-right:20px; line-height:58px;
    text-align:center; font-family:'QK','PingFang SC',sans-serif; font-size:32px;
    color:#2B2622; background:#F0A85C; border:4px solid #2B2622; }
  .rowtext { font-size:29px; line-height:1.72; padding-top:6px; }
  .quote { position:relative; border:4px solid #2B2622;
    border-radius:220px 24px 210px 26px / 26px 210px 24px 220px;
    padding:30px 36px 24px; margin:0 10px 26px; }
  .quote::before { content:""; position:absolute; top:-16px; left:50%; width:130px; height:32px;
    transform:translateX(-50%) rotate(-3deg);
    background:linear-gradient(rgba(226,196,110,.6), rgba(226,196,110,.45));
    border-left:2px dashed rgba(150,120,50,.35); border-right:2px dashed rgba(150,120,50,.35); }
  .quote p { font-size:33px; line-height:1.62; font-weight:600; }
  .by { display:block; text-align:right; font-size:23px; color:#7A7168; margin-top:12px; }
  .act { display:flex; align-items:flex-start; margin-bottom:20px; }
  .check { flex:none; width:44px; height:44px; margin-right:16px; margin-top:4px;
    fill:none; stroke:#D96F32; stroke-width:4; stroke-linecap:round; stroke-linejoin:round; }
  .act p { font-size:28px; line-height:1.72; }
  .foot { padding-top:30px; background:[[WAVE]] repeat-x left top / 120px 10px;
    display:flex; justify-content:space-between; align-items:center; }
  .foot .l { display:flex; align-items:center; gap:12px;
    font-family:'QK','PingFang SC',sans-serif; font-size:26px; letter-spacing:.5px; }
  .foot .l .doodle { width:46px; height:38px; color:#2B2622; }
  .foot .r { font-size:22px; color:#7A7168; }
  .doodle { fill:none; stroke:currentColor; stroke-width:4; stroke-linecap:round; stroke-linejoin:round; }
</style></head><body>
<div class="wrap">
  <div class="top">
    <span class="brand">[[DUCK]]eatmoreduck 多吃鸭 · yaya-skills</span>
    <span class="pill">X Space → 干货笔记</span>
  </div>
  <h1>[[TITLE]]</h1>
  <div class="stats">[[STATS]]</div>
  <div class="divider"></div>
  <div class="sec"><h2>一句话总结</h2><div class="bubble">[[BULB]]<p>[[SUMMARY]]</p></div></div>
  <div class="sec"><h2>核心结论</h2>[[CONCL]]</div>
  <div class="sec"><h2>金句</h2>[[QUOTES]]</div>
  <div class="sec"><h2>可行动项</h2>[[ACTS]]</div>
  <div class="foot">
    <span class="l">[[DUCK]]github.com/eatmoreduck/yaya-skills</span>
    <span class="r">X 回放会过期，文字留档</span>
  </div>
</div>
<script>
window.addEventListener('load', function(){
  document.title = 'H' + document.documentElement.scrollHeight;
});
</script>
</body></html>"""
    return _fill(tpl, GRAIN=_GRAIN, WAVE=_DOODLE["wave"], ULINE=_DOODLE["underline"],
                 DUCK=_DOODLE["duck"], BULB=_DOODLE["bulb"],
                 TITLE=title_html, STATS=stats_html, SUMMARY=esc(d["summary"]),
                 CONCL=concl_html, QUOTES=quote_html, ACTS=act_html)


def build_html(d: dict, chars: str = "", style: str = "swiss") -> str:
    lmap = d.get("lmap") or {}
    if lmap:  # 正文里的字母指代全部换成真名（图上永不出现 ABCD）
        d = {**d,
             "summary": _dename(d["summary"], lmap),
             "conclusions": [(h, _dename(b, lmap)) for h, b in d["conclusions"]],
             "quotes": [(_dename(q, lmap), spk) for q, spk in d["quotes"]],
             "actions": [_dename(a, lmap) for a in d["actions"]]}
    st = _stats(d, chars)
    stats_str = " · ".join(st)
    title_hl = _hl(d["title"])

    if style == "hand":
        return _html_hand(d, st, title_hl)

    if style == "swiss":
        concl = _concl_rows(d, lambda i, body:
                            f'<div class="row"><span class="idx">{i:02d}</span>'
                            f'<p>{body}</p></div>')
        quotes = _quote_blocks(pick_quotes(d["quotes"]),
                               '<div class="qpx"><p>', '</p></div>',
                               lambda spk: f'<span class="by">—— {spk}</span>' if spk else "")
        acts = "".join(f'<div class="act"><span class="box"></span><p>{esc(a)}</p></div>'
                       for a in d["actions"])
        return _fill(_SWISS, TITLE=title_hl, STATS=esc(stats_str),
                     SUMMARY=esc(d["summary"]), CONCL=concl, QUOTES=quotes, ACTS=acts)

    if style == "editorial":
        concl = _concl_rows(d, lambda i, body:
                            f'<div class="row"><span class="cn">{CN_NUM[i-1] if i<=10 else i}、</span>'
                            f'<p>{body}</p></div>')
        quotes = _quote_blocks(pick_quotes(d["quotes"]),
                               '<div class="qpx"><p>', '</p></div>',
                               lambda spk: f'<span class="by">—— {spk}</span>' if spk else "")
        acts = "".join(f'<div class="act"><span class="cb">□</span><p>{esc(a)}</p></div>'
                       for a in d["actions"])
        return _fill(_EDITORIAL, TITLE=title_hl, STATS=esc(stats_str),
                     SUMMARY=esc(d["summary"]), CONCL=concl, QUOTES=quotes, ACTS=acts)

    if style == "riso":
        concl = _concl_rows(d, lambda i, body:
                            f'<div class="row"><span class="num">{i:02d}</span>'
                            f'<p>{body}</p></div>',
                            head_open="<b style='color:#21387F'>", head_close="</b>")
        quotes = _quote_blocks(pick_quotes(d["quotes"]),
                               '<div class="qpx"><p>', '</p></div>',
                               lambda spk: f'<span class="by">—— {spk}</span>' if spk else "")
        acts = "".join(f'<div class="act"><span class="sq"></span><p>{esc(a)}</p></div>'
                       for a in d["actions"])
        return _fill(_RISO, TITLE=title_hl, STATS=esc(stats_str),
                     SUMMARY=esc(d["summary"]), CONCL=concl, QUOTES=quotes, ACTS=acts)

    # midnight
    concl = _concl_rows(d, lambda i, body:
                        f'<div class="row"><span class="num">{i:02d}</span>'
                        f'<p>{body}</p></div>', head_open="<b style='color:#C9A227'>", head_close="</b>")
    quotes = _quote_blocks(pick_quotes(d["quotes"]),
                           '<div class="qpx"><p>', '</p></div>',
                           lambda spk: f'<span class="by">—— {spk}</span>' if spk else "")
    acts = "".join(f'<div class="act"><span class="ar">—</span><p>{esc(a)}</p></div>'
                   for a in d["actions"])
    return _fill(_MIDNIGHT, TITLE=title_hl, STATS=esc(stats_str),
                 SUMMARY=esc(d["summary"]), CONCL=concl, QUOTES=quotes, ACTS=acts)


# ══════════════════════════════════════════════════════════════
# Chrome 两遍截图
# ══════════════════════════════════════════════════════════════
def capture(html_path: Path, out_png: Path, bg: str = "#FFFFFF") -> None:
    html_path = html_path.resolve()
    out_png = out_png.resolve()
    chrome = find_chrome()
    if not chrome:
        raise RuntimeError("未找到 Chrome/Chromium，无法出图")

    # 2x 像素密度出图（2160px 宽）：X 上传会二次压缩，1x 原图到手就糊
    base = [chrome, "--headless", "--disable-gpu", "--hide-scrollbars",
            f"--default-background-color={bg.lstrip('#')}FF", "--no-first-run",
            "--force-device-scale-factor=2"]

    # 第一遍：跑 JS 量内容高度（写进 <title>）
    p1 = subprocess.run(
        base + ["--virtual-time-budget=5000", "--window-size=%d,900" % WIDTH,
                "--dump-dom", html_path.as_uri()],
        capture_output=True, text=True, timeout=120)
    m = re.search(r"<title>H(\d+)</title>", p1.stdout)
    height = int(m.group(1)) if m else 3400  # 测量失败宁可多留白，绝不截断
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
           workdir: Path | None = None, style: str = "swiss") -> Path:
    d = parse_distilled(distilled_md.read_text(encoding="utf-8"))
    chars = ""
    dialog = distilled_md.parent / "audio.dialog.txt"
    if dialog.exists():
        # 去掉 "A：" 说话人前缀后再计字数，与蒸馏统计口径一致
        body = "".join(re.sub(r"^[A-Z]+：", "", ln)
                       for ln in dialog.read_text(encoding="utf-8").splitlines() if ln.strip())
        n = len(body)
        chars = f"{n/10000:.1f} 万字" if n >= 10000 else f"{n} 字"
    h = build_html(d, chars=chars, style=style)
    workdir = (workdir or Path(tempfile.mkdtemp(prefix="yaya-card-"))).resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    # 字体拷到 HTML 同目录（相对引用，headless 可直接加载；仅 hand 风格用到）
    if FONTS_DIR.exists():
        for f in FONTS_DIR.glob("*.ttf"):
            shutil.copy2(f, workdir / f.name)
    html_path = workdir / f"{distilled_md.stem}.card.{style}.html"
    html_path.write_text(h, encoding="utf-8")
    out_png = (out_png or distilled_md.with_suffix(".png")).resolve()
    t = time.time()
    capture(html_path, out_png, bg=STYLE_BG.get(style, "#FFFFFF"))
    log(f"分享图已生成 [{style}] {out_png.name} ({out_png.stat().st_size/1e6:.1f}MB, {time.time()-t:.0f}s)")
    return out_png


def main() -> int:
    ap = argparse.ArgumentParser(description="yaya-xspace：distilled.md → 分享图 PNG")
    ap.add_argument("md", help="distilled.md 路径")
    ap.add_argument("--style", choices=STYLES, default="swiss", help="视觉风格（默认 swiss）")
    ap.add_argument("--out", type=Path, default=None, help="输出 PNG（默认同名 .png）")
    ap.add_argument("--workdir", type=Path, default=None, help="HTML 中间产物目录（默认临时目录）")
    args = ap.parse_args()
    md = Path(args.md).expanduser().resolve()
    if not md.exists():
        sys.exit(f"❌ 找不到 {md}")
    render(md, out_png=args.out, workdir=args.workdir, style=args.style)
    return 0


if __name__ == "__main__":
    sys.exit(main())
