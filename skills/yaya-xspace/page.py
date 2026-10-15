#!/usr/bin/env python3
"""
yaya-xspace 网页化 —— 蒸馏稿 + 逐字稿 + 原声，合成一个可交互页面（distilled.html）。

左栏蒸馏笔记（一句话/核心结论/金句/可行动项），右栏逐字稿时间流：
点任意段落从该处收听原声，播放时高亮跟随；说话人 chips 可只看某人。
音频走同目录 audio.m4a 相对引用——本地 file:// 直接能用，M2 上云时
把 distilled.html + audio.m4a 一起传 R2/Pages 即可，路径无需改动。

说话人一律显示真名（speaker_names.json 映射），页面绝不出现 A/B/C 字母
（AGENTS.md 硬约束 9 同款口径）。逐字稿忠实呈现机器转写原文，标注未校对。

用法（distill.py 自动调用；也可单独重建）:
    python3 page.py <outdir>
依赖：同目录 card.py（复用蒸馏解析）；纯标准库，无外部服务。
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import card  # 同目录模块：复用 parse_distilled / esc

SKILL_DIR = Path(__file__).resolve().parent
RED = "#E02B20"       # swiss 品牌红
BG = "#F1F0EC"
# 说话人色点轮转（克制、和谐、白底可辨）
DOTS = ("#E02B20", "#1F5FA8", "#1E7A46", "#B0680A", "#7A3E9D",
        "#0F7B8A", "#A8385A", "#5B5BD6", "#4E6E00", "#8A5A2B")


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _fmt(sec: float) -> str:
    s = int(sec)
    h, rem = divmod(s, 3600)
    m, sec2 = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec2:02d}" if h else f"{m:02d}:{sec2:02d}"


def _load(outdir: Path) -> dict:
    labeled = outdir / "audio.labeled.json"
    if not labeled.exists():
        raise FileNotFoundError(f"缺少 {labeled.name}（先跑一遍完整转写）")
    data = json.loads(labeled.read_text(encoding="utf-8"))
    segs = [(float(s["start"]), float(s["end"]), s["speaker"], s["text"])
            for s in data.get("segments", []) if (s.get("text") or "").strip()]
    if not segs:
        raise ValueError("labeled.json 里没有可用段落")

    names: dict[str, str] = {}
    nj = outdir / "speaker_names.json"
    if nj.exists():
        try:
            names = json.loads(nj.read_text(encoding="utf-8")).get("mapping") or {}
        except (OSError, json.JSONDecodeError):
            names = {}

    meta = {}
    mj = outdir / "meta.json"
    if mj.exists():
        try:
            meta = json.loads(mj.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            meta = {}

    distill = {}
    md = outdir / "distilled.md"
    if md.exists():
        distill = card.parse_distilled(md.read_text(encoding="utf-8"))
    return {"segs": segs, "names": names, "meta": meta, "distill": distill}


def _speaker_meta(segs: list, names: dict) -> list[dict]:
    """按发言量排序的说话人列表：字母、真名、色点、时长合计。"""
    total: dict[str, float] = {}
    for s, e, spk, _ in segs:
        total[spk] = total.get(spk, 0.0) + (e - s)
    out = []
    for i, (spk, t) in enumerate(sorted(total.items(), key=lambda kv: -kv[1])):
        out.append({"letter": spk,
                    "name": names.get(spk) or spk,  # 拿不到真名保留字母（宁字母不编造）
                    "dot": DOTS[i % len(DOTS)],
                    "secs": int(t)})
    return out


def _distill_html(d: dict) -> str:
    e = card.esc
    parts = []
    if d.get("summary"):
        parts.append(f'<section class="dsum"><h3>一句话总结</h3><p>{e(d["summary"])}</p></section>')
    if d.get("conclusions"):
        rows = "".join(
            f'<li>{"<b>%s：</b>" % e(h) if h else ""}{e(b)}</li>'
            for h, b in d["conclusions"])
        parts.append(f'<section><h3>核心结论</h3><ol class="ccl">{rows}</ol></section>')
    quotes = card.pick_quotes(d.get("quotes") or [])
    if quotes:
        rows = "".join(f'<blockquote>「{e(q)}」<cite>—— {e(s)}</cite></blockquote>'
                       for q, s in quotes if s and s != "？")
        parts.append(f'<section><h3>金句</h3>{rows}</section>')
    if d.get("actions"):
        rows = "".join(f"<li>{e(a)}</li>" for a in d["actions"])
        parts.append(f'<section><h3>可行动项</h3><ul class="act">{rows}</ul></section>')
    return "\n".join(parts)


_TMPL = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>[[TITLE]] · yaya 收听页</title>
<style>
:root{--bg:[[BG]];--ink:#101010;--red:[[RED]];--line:#101010;--card:#FBFAF7}
*{margin:0;padding:0;box-sizing:border-box}
html{background:var(--bg)}
body{font-family:-apple-system,'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif;
 color:var(--ink);line-height:1.7}
/* ── 吸顶播放条 ── */
#bar{position:sticky;top:0;z-index:9;background:var(--bg);
 border-bottom:2px solid var(--line);padding:10px 18px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
#bar .btn{flex:none;width:44px;height:44px;border-radius:50%;border:2px solid var(--line);
 background:var(--red);color:#fff;font-size:18px;cursor:pointer}
#bar .btn:active{transform:scale(.94)}
#prog{flex:1 1 200px;accent-color:var(--red);height:6px;cursor:pointer}
#tm{font-variant-numeric:tabular-nums;font-size:13px;opacity:.75;white-space:nowrap}
#rate{border:1.5px solid var(--line);background:transparent;border-radius:14px;
 padding:3px 12px;font-size:13px;font-weight:700;cursor:pointer}
/* ── 头部 ── */
header{padding:34px 22px 10px;max-width:1200px;margin:0 auto}
header .kicker{font-size:13px;font-weight:700;letter-spacing:2px;opacity:.6}
header h1{font-size:clamp(24px,4vw,40px);line-height:1.3;font-weight:900;margin:8px 0 12px}
header .src a{color:var(--red);font-size:14px;text-decoration:none}
.stats{display:flex;gap:20px;flex-wrap:wrap;font-size:14px;opacity:.72;margin-top:10px}
.stats b{font-variant-numeric:tabular-nums}
/* ── 主体双栏 ── */
main{max-width:1200px;margin:18px auto 60px;padding:0 18px;
 display:grid;grid-template-columns:minmax(320px,5fr) 7fr;gap:26px;align-items:start}
@media (max-width:960px){main{grid-template-columns:1fr}}
/* 蒸馏栏 */
#dnotes{position:sticky;top:78px;background:var(--card);border:1.5px solid var(--line);
 padding:22px 24px;box-shadow:6px 6px 0 rgba(16,16,16,.12)}
@media (max-width:960px){#dnotes{position:static}}
#dnotes h2{font-size:15px;letter-spacing:3px;border-bottom:2px solid var(--line);
 padding-bottom:8px;margin-bottom:14px}
#dnotes h3{font-size:13px;letter-spacing:2px;color:var(--red);margin:18px 0 8px}
#dnotes .dsum p{font-size:17px;font-weight:700;line-height:1.7}
#dnotes .ccl{padding-left:20px}
#dnotes .ccl li{margin-bottom:9px;font-size:14.5px}
#dnotes blockquote{border-left:3px solid var(--red);padding:2px 0 2px 12px;margin:10px 0;
 font-size:14.5px;font-weight:600}
#dnotes blockquote cite{display:block;font-style:normal;opacity:.55;font-size:12.5px;margin-top:4px}
#dnotes .act{padding-left:20px}
#dnotes .act li{margin-bottom:7px;font-size:14.5px}
#dnotes .empty{font-size:13.5px;opacity:.6}
/* 逐字稿栏 */
#tl .tip{font-size:12.5px;opacity:.6;margin-bottom:10px}
#chips{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px}
#chips .chip{display:inline-flex;align-items:center;gap:6px;border:1.5px solid var(--line);
 background:var(--card);border-radius:999px;padding:3px 12px 3px 8px;font-size:13px;
 font-weight:600;cursor:pointer;user-select:none}
#chips .chip .dt{width:9px;height:9px;border-radius:50%;flex:none}
#chips .chip .dur{opacity:.5;font-weight:400;font-size:11.5px}
#chips .chip.on{background:var(--ink);color:#fff}
.seg{display:flex;gap:10px;padding:9px 10px;border-radius:10px;cursor:pointer;
 scroll-margin:140px;align-items:baseline}
.seg:hover{background:rgba(16,16,16,.055)}
.seg .t{flex:none;font-variant-numeric:tabular-nums;font-size:12.5px;opacity:.55;
 padding-top:2px;min-width:44px;text-align:right}
.seg .n{flex:none;font-size:13px;font-weight:800;display:flex;align-items:center;gap:6px;
 min-width:74px}
.seg .n .dt{width:8px;height:8px;border-radius:50%;flex:none}
.seg p{font-size:15px}
.seg.now{background:rgba(224,43,32,.09);outline:1.5px solid rgba(224,43,32,.45)}
.seg.now .t{opacity:1;color:var(--red);font-weight:800}
body.hide .seg{opacity:.18}
body.hide .seg.hit{opacity:1}
footer{max-width:1200px;margin:0 auto;padding:0 18px 40px;font-size:12.5px;opacity:.55}
</style></head><body>

<div id="bar">
  <button class="btn" id="play" aria-label="播放/暂停">▶</button>
  <span id="tm">00:00 / 00:00</span>
  <input id="prog" type="range" min="0" max="1000" value="0" step="1" aria-label="进度">
  <button id="rate" aria-label="倍速">1.0×</button>
</div>
<audio id="au" src="audio.m4a" preload="metadata"></audio>

<header>
  <div class="kicker">X SPACE · 收听页</div>
  <h1>[[TITLE]]</h1>
  <p class="stats">[[STATS]]</p>
  <p class="src">[[SRC]]</p>
</header>

<main>
  <aside id="dnotes">
    <h2>蒸馏笔记</h2>
    [[DISTILL]]
  </aside>
  <section id="tl">
    <p class="tip">机器转写原文，未人工校对。点任意段落从该处收听；播放时自动跟随高亮。点说话人名可只看 TA。</p>
    <div id="chips"></div>
    <div id="flow"></div>
  </section>
</main>

<footer>由 yaya-skills 本地生成 · 音频与文字均来自公开 Space 回放的机器转写 · 源 <span id="srcid">[[ID]]</span></footer>

<script>
const DATA = [[DATA]];

const au = document.getElementById('au');
const flow = document.getElementById('flow');
const playBtn = document.getElementById('play');
const tmEl = document.getElementById('tm');
const prog = document.getElementById('prog');
const rateBtn = document.getElementById('rate');
const RATES = [1.0, 1.25, 1.5, 1.75, 2.0];

/* ── 说话人 chips ── */
const chips = document.getElementById('chips');
let activeSpk = null;
DATA.speakers.forEach(sp => {
  const b = document.createElement('span');
  b.className = 'chip';
  b.innerHTML = `<span class="dt" style="background:${sp.dot}"></span>`
    + `${sp.name}<span class="dur">${Math.round(sp.secs/60)}min</span>`;
  b.onclick = () => {
    activeSpk = (activeSpk === sp.letter) ? null : sp.letter;
    chips.querySelectorAll('.chip').forEach(c => c.classList.remove('on'));
    if (activeSpk) b.classList.add('on');
    document.body.classList.add('hide');
    document.body.classList.toggle('hide', !!activeSpk);
    if (activeSpk) {
      flow.querySelectorAll('.seg').forEach(el =>
        el.classList.toggle('hit', el.dataset.spk === activeSpk));
      const first = flow.querySelector(`.seg[data-spk="${activeSpk}"]`);
      if (first) first.scrollIntoView({block:'start', behavior:'smooth'});
    }
  };
  chips.appendChild(b);
});

/* ── 逐字稿渲染 ── */
const nameOf = l => (DATA.names[l] || l);
const dotOf = l => { const s = DATA.speakers.find(x => x.letter === l); return s ? s.dot : '#888'; };
const frag = document.createDocumentFragment();
DATA.segments.forEach((sg, i) => {
  const [s, e, spk, text] = sg;
  const div = document.createElement('div');
  div.className = 'seg'; div.dataset.s = s; div.dataset.e = e; div.dataset.spk = spk;
  div.innerHTML = `<span class="t">${fmtT(s)}</span>`
    + `<span class="n"><span class="dt" style="background:${dotOf(spk)}"></span>${esc(nameOf(spk))}</span>`
    + `<p>${esc(text)}</p>`;
  div.onclick = () => { au.currentTime = s; au.play(); };
  frag.appendChild(div);
});
flow.appendChild(frag);
const segEls = [...flow.children];

function esc(s){ return s.replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function fmtT(sec){ const s = Math.floor(sec), m = Math.floor(s/60);
  return (s%3600>=3600? Math.floor(s/3600)+':'+String(m%60).padStart(2,'0') : String(m).padStart(2,'0'))
    + ':' + String(s%60).padStart(2,'0'); }

/* ── 播放控制 ── */
playBtn.onclick = () => au.paused ? au.play() : au.pause();
au.onplay  = () => playBtn.textContent = '⏸';
au.onpause = () => playBtn.textContent = '▶';
au.onloadedmetadata = () => tick(au.currentTime);
au.ontimeupdate = () => tick(au.currentTime);
prog.oninput = () => { if (au.duration) au.currentTime = prog.value/1000*au.duration; };
rateBtn.onclick = () => {
  const i = RATES.indexOf(au.playbackRate);
  au.playbackRate = RATES[(i+1) % RATES.length];
  rateBtn.textContent = au.playbackRate + '×';
};
document.addEventListener('keydown', ev => {
  if (ev.code === 'Space' && ev.target === document.body) { ev.preventDefault(); playBtn.click(); }
});

/* ── 高亮跟随（用户滚动后 4s 内不打架）── */
let curIdx = 0, follow = true, followTimer = null;
addEventListener('wheel', bump, {passive:true});
addEventListener('touchmove', bump, {passive:true});
function bump(){ follow = false; clearTimeout(followTimer);
  followTimer = setTimeout(() => follow = true, 4000); }

function tick(t){
  if (au.duration) {
    tmEl.textContent = fmtT(t) + ' / ' + fmtT(au.duration);
    if (!prog.matches(':active')) prog.value = Math.round(t/au.duration*1000);
  }
  let i = Math.max(0, curIdx - 2);
  while (i < DATA.segments.length && DATA.segments[i][1] <= t) i++;
  if (i !== curIdx) {
    if (curIdx < segEls.length) segEls[curIdx].classList.remove('now');
    curIdx = i;
    if (i < segEls.length) {
      const el = segEls[i];
      el.classList.add('now');
      if (follow) el.scrollIntoView({block:'center', behavior:'smooth'});
    }
  }
}
</script></body></html>"""


def build(outdir: Path) -> Path:
    """outdir（含 audio.m4a / audio.labeled.json / distilled.md …）→ distilled.html"""
    d = _load(outdir)
    segs, names, meta, dist = d["segs"], d["names"], d["meta"], d["distill"]
    speakers = _speaker_meta(segs, names)
    title = (dist.get("title") or meta.get("title") or outdir.name).strip()
    dur = int(segs[-1][1])
    nchars = sum(len(t) for _, _, _, t in segs)
    stats = (f"<span><b>{len(speakers)}</b> 位说话人</span>"
             f"<span><b>{len(segs)}</b> 段</span>"
             f"<span>时长 <b>{_fmt(dur)}</b></span>"
             f"<span><b>{nchars:,}</b> 字逐字稿</span>")
    src_html = (f'<a href="{card.esc(meta["url"])}" target="_blank" rel="noopener">'
                f'源 Space：{card.esc(meta.get("id") or outdir.name)}</a>'
                if meta.get("url") else "")
    dist_html = _distill_html(dist) or '<p class="empty">没有蒸馏稿（distilled.md），只有逐字稿。</p>'

    # 嵌入数据：段落精简为 [start, end, 字母, 文本]，名字/色点前端解
    data = json.dumps({
        "segments": [[round(s, 2), round(e, 2), spk, t] for s, e, spk, t in segs],
        "speakers": speakers,
        "names": names,
    }, ensure_ascii=False, separators=(",", ":"))

    html_out = (_TMPL.replace("[[TITLE]]", card.esc(title))
                .replace("[[STATS]]", stats)
                .replace("[[SRC]]", src_html)
                .replace("[[DISTILL]]", dist_html)
                .replace("[[ID]]", card.esc(meta.get("id") or outdir.name))
                .replace("[[DATA]]", data)
                .replace("[[BG]]", BG).replace("[[RED]]", RED))
    out = outdir / "distilled.html"
    out.write_text(html_out, encoding="utf-8")
    log(f"收听页已生成 {out.name}（{out.stat().st_size/1e3:.0f}KB，配同目录 audio.m4a 播放）")
    return out


def main() -> int:
    if len(sys.argv) != 2:
        sys.exit("用法: python3 page.py <outdir>（含 audio.m4a 与 audio.labeled.json 的目录）")
    build(Path(sys.argv[1]).expanduser().resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
