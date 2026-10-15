#!/usr/bin/env python3
"""
yaya-xspace 发布 —— 一场 Space 的收听页 + 音频上云，成为自己的线上内容资产。

架构（全部 Cloudflare 免费档，一条命令搞定）：
  音频 → R2 桶（yaya-audio），经一个极小 Worker（yaya-audio-cdn）代理：
        支持 Range 请求（拖动进度条即点即播），Worker 免 10 万请求/天
  页面 → Cloudflare Pages（yaya-assets）：
        /            全部场次列表（manifest.json 生成，每次发布重建）
        /s/<id>/     单场收听页（distilled.html，音频指向 Worker 域名）

默认绝不发布（out/ 里有私人场）——只有显式 `--publish` 指定场次才上传。
发布即声明：该场为公开内容、发言者知情可接受。

用法:
    python3 publish.py <outdir> [--dry-run]
    （distill.py 会经 --publish 调用）
依赖：wrangler（npx，OAuth 已登录）；wrangler 未登录先 `npx wrangler login`。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import card    # 同目录：esc / parse_distilled
import page    # 同目录：收听页生成（audio_url 参数化）

SKILL_DIR = Path(__file__).resolve().parent
OUT_ROOT = SKILL_DIR / "out"
PUB_ROOT = OUT_ROOT / ".publish"      # 发布工位：site 本地镜像 + 缓存（out/ 已 gitignore）
SITE_DIR = PUB_ROOT / "site"

R2_BUCKET = "yaya-audio"
WORKER_NAME = "yaya-audio-cdn"
PAGES_PROJECT = "yaya-assets"
PAGES_BASE = f"https://{PAGES_PROJECT}.pages.dev"

WORKER_JS = """export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const m = url.pathname.match(/^\\/audio\\/([A-Za-z0-9._\\-]+)$/);
    if (!m) return new Response('not found', { status: 404 });
    const key = decodeURIComponent(m[1]);
    const base = {
      'Content-Type': 'audio/mp4',
      'Accept-Ranges': 'bytes',
      'Cache-Control': 'public, max-age=86400',
    };
    let obj, status = 200, extra = {};
    const rng = request.headers.get('range');
    const mm = rng && /bytes=(\\d+)-(\\d*)/.exec(rng);
    if (mm) {
      const offset = Number(mm[1]);
      const length = mm[2] ? Number(mm[2]) - offset + 1 : undefined;
      obj = await env.R2.get(key, { range: { offset, length } });
      if (obj) {
        // R2 约定：obj.size 是对象总长，obj.range.length 是本次片段长
        const len = (obj.range && obj.range.length) || (obj.size - offset);
        status = 206;
        extra = { 'Content-Range': `bytes ${offset}-${offset + len - 1}/${obj.size}` };
      }
    } else {
      obj = await env.R2.get(key);
    }
    if (!obj) return new Response('not found', { status: 404 });
    return new Response(obj.body, { status, headers: { ...base, ...extra } });
  },
};
"""

WORKER_TOML = f"""name = "{WORKER_NAME}"
main = "worker.js"
compatibility_date = "2025-01-01"

[[r2_buckets]]
binding = "R2"
bucket_name = "{R2_BUCKET}"
"""


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def wrangler(*args: str, timeout: int = 600, check: bool = True) -> str:
    """跑 wrangler 命令，返回 stdout+stderr（wrangler 的报错多在 stderr）。"""
    cmd = ["npx", "--yes", "wrangler", *args]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    out = p.stdout + ("\n" + p.stderr if p.stderr.strip() else "")
    if check and p.returncode != 0:
        raise RuntimeError(f"wrangler {' '.join(args[:2])} 失败：\n{out[-800:]}")
    return out


def _ensure_worker() -> str:
    """确保 R2 桶 + Range 代理 Worker 就位，返回 Worker 公网基址。"""
    out = wrangler("r2", "bucket", "create", R2_BUCKET, check=False)
    if "10042" in out or "enable R2" in out.lower():
        sys.exit("❌ 这个 Cloudflare 账号还没开通 R2（免费档 10GB，流出流量免费）。\n"
                 "   开通：https://dash.cloudflare.com → 左侧 R2 → 按提示开通\n"
                 "   （需绑一张卡做验证；不放音频不产生扣费）。开通后重跑 --publish。")
    with tempfile.TemporaryDirectory(prefix="yaya-worker-") as td:
        td = Path(td)
        (td / "worker.js").write_text(WORKER_JS, encoding="utf-8")
        (td / "wrangler.toml").write_text(WORKER_TOML, encoding="utf-8")
        out = wrangler("deploy", "--config", str(td / "wrangler.toml"))
    m = re.search(r"https://[a-zA-Z0-9-]+\.[a-zA-Z0-9.-]+\.workers\.dev", out)
    if not m:
        raise RuntimeError(f"部署成功但没拿到 workers.dev 域名，输出：\n{out[-500:]}")
    return m.group(0).rstrip("/")


def _entry(outdir: Path, audio_url: str, ctype: str = "auto") -> dict:
    """单场 manifest 条目（资产库的"表结构"）+ 生成收听页 HTML。

    type 是来源类型位：space / interview / youtube / audio——
    现在只有 Space，字段先立好，以后 YouTube 拆解、视频访谈直接归档不迁移。"""
    meta = {}
    mj = outdir / "meta.json"
    if mj.exists():
        meta = json.loads(mj.read_text(encoding="utf-8"))
    dist = card.parse_distilled((outdir / "distilled.md").read_text(encoding="utf-8"))
    if ctype == "auto":
        u = meta.get("url") or ""
        ctype = "space" if ("x.com/i/spaces" in u or "twitter.com/i/spaces" in u) else "audio"
    duration_sec, chars = 0, 0
    lj = outdir / "audio.labeled.json"
    if lj.exists():
        try:
            segs = json.loads(lj.read_text(encoding="utf-8")).get("segments") or []
            if segs:
                duration_sec = int(float(segs[-1]["end"]))
                chars = sum(len(s.get("text") or "") for s in segs)
        except (OSError, json.JSONDecodeError, KeyError, ValueError):
            pass
    sid = meta.get("id") or outdir.name
    # write=False：只取 HTML 内容组装线上页，别把占位音频地址写进本地收听页
    page_html = page.build(outdir, audio_url=audio_url, write=False)
    summary = dist.get("summary") or ""
    return {"id": sid, "type": ctype, "lang": "zh",
            "title": dist.get("title") or meta.get("title") or sid,
            "summary": summary[:120], "url": meta.get("url") or "",
            "n_spk": dist.get("n_spk") or "", "duration_sec": duration_sec,
            "chars": chars, "published_at": time.strftime("%Y-%m-%d"),
            "page_html": page_html}


TYPE_LABEL = {"space": "SPACE", "interview": "INTERVIEW", "youtube": "YOUTUBE", "audio": "AUDIO"}


def _index_html(entries: list[dict]) -> str:
    e = card.esc
    def _fmt_dur(sec: int) -> str:
        h, rem = divmod(sec, 3600)
        return f"{h}h{rem // 60:02d}m" if h else f"{sec // 60}min"
    cards = ""
    for it in sorted(entries, key=lambda x: x.get("published_at", ""), reverse=True):
        t = it.get("type") or "audio"
        label = TYPE_LABEL.get(t, t.upper())
        summary = f'<p class="sum">{e(it["summary"])}</p>' if it.get("summary") else ""
        meta_bits = [e(it["published_at"])]
        if it.get("duration_sec"):
            meta_bits.append(_fmt_dur(int(it["duration_sec"])))
        if it.get("n_spk"):
            meta_bits.append(f'{e(str(it["n_spk"]))} speakers')
        if it.get("chars"):
            meta_bits.append(f'{int(it["chars"]):,} 字')
        cards += (f'<a class="card" data-type="{e(t)}" href="s/{e(it["id"])}/">'
                  f'<div class="row1"><h3>{e(it["title"])}</h3>'
                  f'<span class="badge">{e(label)}</span></div>'
                  f'<div class="meta"><span class="dt"></span>{" · ".join(meta_bits)}</div>'
                  f'{summary}</a>')
    return f"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>yaya · audio assets</title>
<style>
:root{{--bg:#F1F0EC;--ink:#101010;--red:#E02B20}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:var(--bg);color:var(--ink);font-family:-apple-system,'PingFang SC','Hiragino Sans GB',sans-serif}}
.wrap{{max-width:860px;margin:0 auto;padding:48px 20px 60px}}
.top{{display:flex;justify-content:space-between;align-items:baseline;
 border-bottom:2px solid var(--ink);padding-bottom:14px}}
.top h1{{font-size:26px;font-weight:900;letter-spacing:2px}}
.top a{{color:var(--red);font-size:13px;text-decoration:none}}
#filters{{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0 6px}}
#filters .f{{border:1.5px solid var(--ink);background:transparent;border-radius:999px;
 padding:3px 14px;font-size:12.5px;font-weight:700;cursor:pointer;letter-spacing:1px}}
#filters .f.on{{background:var(--ink);color:#fff}}
.note{{font-size:13px;opacity:.6;margin:8px 0 24px}}
.card{{display:block;background:#FBFAF7;border:1.5px solid var(--ink);
 padding:18px 22px;margin-bottom:16px;text-decoration:none;color:inherit;
 box-shadow:5px 5px 0 rgba(16,16,16,.12);transition:transform .08s}}
.card:hover{{transform:translate(-2px,-2px)}}
.card[hidden]{{display:none}}
.row1{{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}}
.card h3{{font-size:18px;font-weight:800;line-height:1.5}}
.badge{{flex:none;border:1.5px solid var(--ink);border-radius:4px;padding:1px 8px;
 font-size:10.5px;font-weight:800;letter-spacing:1.5px}}
.card .meta{{font-size:12.5px;opacity:.65;margin-top:6px;display:flex;align-items:center;gap:6px;flex-wrap:wrap}}
.card .dt{{width:8px;height:8px;border-radius:50%;background:var(--red);flex:none}}
.card .sum{{font-size:14px;opacity:.8;margin-top:8px;line-height:1.7}}
.foot{{margin-top:30px;font-size:12.5px;opacity:.55}}
</style></head><body><div class="wrap">
<div class="top"><h1>YAYA · AUDIO ASSETS</h1><a href="https://github.com/eatmoreduck/yaya-skills" target="_blank" rel="noopener">yaya-skills ↗</a></div>
<div id="filters"></div>
<p class="note">语音内容的文字沉淀与原声存档——平台回放会过期，这里长期在。点卡片收听，点哪段听哪段。</p>
{cards}
<p class="foot">由 yaya-skills 本地蒸馏生成 · 托管于 Cloudflare</p>
</div>
<script>
const cards = [...document.querySelectorAll('.card')];
const types = [...new Set(cards.map(c => c.dataset.type))];
const box = document.getElementById('filters');
let active = null;
function chip(label, val) {{
  const b = document.createElement('button');
  b.className = 'f'; b.textContent = label;
  b.onclick = () => {{
    active = (active === val) ? null : val;
    box.querySelectorAll('.f').forEach(x => x.classList.remove('on'));
    if (active) b.classList.add('on');
    cards.forEach(c => c.hidden = !!(active && c.dataset.type !== active));
  }};
  box.appendChild(b);
  return b;
}}
chip('全部', null);
types.forEach(t => chip(t.toUpperCase(), t));
</script></body></html>"""


def publish(outdir: Path, dry_run: bool = False, ctype: str = "auto") -> dict:
    """发布单场：音频→R2，收听页+列表→Pages。返回 {listen_url, site_url}。"""
    outdir = outdir.resolve()
    md, audio = outdir / "distilled.md", outdir / "audio.m4a"
    if not md.exists():
        sys.exit(f"❌ {outdir} 下没有 distilled.md，先完整蒸馏")
    if not audio.exists():
        sys.exit(f"❌ {outdir} 下没有 audio.m4a（音频被删的场发不了，回放还在就重跑一遍下载）")
    SITE_DIR.mkdir(parents=True, exist_ok=True)

    sid_full = (outdir / "meta.json")
    sid = "space"
    if sid_full.exists():
        sid = json.loads(sid_full.read_text(encoding="utf-8")).get("id") or outdir.name
    audio_key = f"audio/{sid}.m4a"

    if dry_run:
        # 离线组装：不碰 Cloudflare，Worker 域名用占位（只看站点结构与页面效果）
        worker_base = f"https://{WORKER_NAME}.example.workers.dev"
        log(f"① dry-run：跳过 R2/Worker，音频地址用占位 {worker_base}")
    else:
        log("① 准备 R2 桶与 Range 代理 Worker…")
        worker_base = _ensure_worker()
        log(f"   Worker: {worker_base}")
    audio_url = f"{worker_base}/{audio_key}"

    log("② 生成线上版收听页…")
    entry = _entry(outdir, audio_url, ctype=ctype)

    if not dry_run:
        log(f"③ 上传音频到 R2（{audio.stat().st_size/1e6:.0f}MB，几分钟看带宽）…")
        wrangler("r2", "object", "put", f"{R2_BUCKET}/{audio_key}",
                 f"--file={audio}", "--remote", timeout=1800)

    # ④ 组装站点：manifest upsert（v2：version+entries；旧数组格式兼容读）→ 单场页 → 索引页
    log("④ 组装站点与索引页…")
    man_path = SITE_DIR / "manifest.json"
    try:
        data = json.loads(man_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = []
    entries = data.get("entries") if isinstance(data, dict) else data
    entries = [m for m in (entries or []) if m.get("id") != entry["id"]]
    entries.append({k: v for k, v in entry.items() if k != "page_html"})
    man_path.write_text(json.dumps({"version": 2, "entries": entries},
                                   ensure_ascii=False, indent=1), encoding="utf-8")
    d = SITE_DIR / "s" / entry["id"]
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.html").write_text(entry["page_html"], encoding="utf-8")
    (SITE_DIR / "index.html").write_text(_index_html(entries), encoding="utf-8")

    if dry_run:
        log("✔ dry-run 完成：站点已组装在 " + str(SITE_DIR) + "，未上传")
        return {"listen_url": "(dry-run)", "site_url": "(dry-run)"}

    log("⑤ 部署到 Cloudflare Pages…")
    wrangler("pages", "project", "create", PAGES_PROJECT,
             "--production-branch=main", check=False)  # 已存在不算错
    wrangler("pages", "deploy", str(SITE_DIR), f"--project-name={PAGES_PROJECT}")

    listen = f"{PAGES_BASE}/s/{entry['id']}/"
    log("=" * 60)
    log(f"🎉 已发布：{listen}")
    log(f"📚 资产库：{PAGES_BASE}")
    log("=" * 60)
    return {"listen_url": listen, "site_url": PAGES_BASE}


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit("用法: python3 publish.py <outdir> [--dry-run] [--type space|interview|youtube|audio]")
    ctype = "auto"
    if "--type" in sys.argv:
        i = sys.argv.index("--type")
        ctype = sys.argv[i + 1] if i + 1 < len(sys.argv) else "auto"
    publish(Path(args[0]).expanduser().resolve(),
            dry_run="--dry-run" in sys.argv, ctype=ctype)
    return 0


if __name__ == "__main__":
    sys.exit(main())
