# yaya-skills

English | [简体中文](README.md)

![yaya-skills](assets/banner.png)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/eatmoreduck/yaya-skills?style=social)](https://github.com/eatmoreduck/yaya-skills)
[![Works with](https://img.shields.io/badge/Works%20with-Claude%20Code%20%7C%20Codex%20%7C%20Cursor%20%7C%20Windsurf%20%7C%20ZCode-blueviolet)](#install)
![Platform](https://img.shields.io/badge/macOS-Apple%20Silicon-black?logo=apple)
![Local](https://img.shields.io/badge/audio-never%20leaves%20your%20machine-success)

> **Wave 1: turn X Space audio into text.** You catch something great while driving or cooking and want to note it down — but your hands are busy. By the time you're free, all that's left is a vague impression, and the replay gets deleted after 30 days anyway. One link turns a two-hour Space into speaker-grouped notes with every quotable line preserved verbatim — **plus a ready-to-post share card**.

**yaya-skills is a toolset that helps writers work faster.** Wave 1 is a **distiller for X Spaces** ([yaya-xspace](skills/yaya-xspace/)): it turns Spaces you had no time to listen to into ready-to-use notes, backed by three atomic skills for download / transcription / speaker separation. More tools for writers will follow. Audio never leaves your machine.

> Note: the distilled notes are written in Chinese (the pipeline is tuned for Chinese-language Spaces).

## Quick start (the hero scenario)

```bash
bash skills/yaya-xspace/run.sh "https://x.com/i/spaces/<13-char-id>"
# → skills/yaya-xspace/out/<id>/distilled.md
```

Models download automatically on first run. A two-hour Space takes about 30 minutes — GPU transcription and speaker separation run in parallel.

## See it on a real session

The full pipeline output of a real 119-minute Space — **["Noise After: Why Your IP Needs Its Own 'Theory'"](https://x.com/i/spaces/1AKEmvYqbrOKL)** (Chinese, 10 speakers — on personal IP, persona and monetization):

| Artifact | What you're looking at |
|---|---|
| [**distilled.png**](demo/1AKEmvYqbrOKL/distilled.png) | ★ **The one-image card** — the notes auto-rendered into a share card, ready to post |
| [**distilled.md**](demo/1AKEmvYqbrOKL/distilled.md) | ★ The final distilled notes (Chinese): one-line summary / key conclusions / per-speaker points / master term list / disagreements / action items |
| [Speaker-labeled transcript (excerpt)](demo/1AKEmvYqbrOKL/dialog-excerpt.txt) | Intermediate artifact: raw audio → who-said-what (full transcript: 29,930 chars, 10 speakers) |

<img src="demo/1AKEmvYqbrOKL/distilled.png" width="520" alt="Share card (Swiss style, full-length card — click to enlarge)">

Four card styles are built in — switch with `--style` (click a name to open the full-size card):

- [**Swiss**](assets/styles/swiss.png) (default) — off-white, heavy grotesk, red sound-wave arcs, hairlines
- [**Editorial**](assets/styles/editorial.png) — cream paper, Songti serif, vermilion blocks, newsprint feel
- [**Riso**](assets/styles/riso.png) — risograph blue/orange misregistration, halftone dots
- [**Midnight**](assets/styles/midnight.png) — dark, gold hairlines, serif, premium feel

> 119 minutes of audio → a distilled note plus a share card in 29.5 minutes (GPU transcription and CPU speaker separation run in parallel the whole way). Source Space ID: `1AKEmvYqbrOKL`. X replays expire after 30 days — the text artifacts are archived here; the audio stays in the local `out/`. There is also an experimental hand-drawn style, `hand`.

## Architecture

<img src="assets/architecture.png" width="440" alt="yaya-skills pipeline">

**Layering rule: upper layers depend on lower ones, one direction only.**

- **Atomic skills know nothing about each other**: `yaya-xdl` only downloads — a Space link in, `audio.m4a` out (download = archive); `yaya-asr` only transcribes — audio in, speaker-labeled text out; `yaya-diarize` only separates — audio in, a "who spoke when" timeline out. No business concepts in any of them.
- **`yaya-asr` is a pipeline inside**: transcription (MLX/GPU) spawns separation ([yaya-diarize](skills/yaya-diarize/), CPU) in a background process the moment it starts. Both run **in parallel** without contending for resources.
- **`yaya-xspace` is the orchestrator**: it chains xdl and asr, then adds its own distillation step. Every stage is invoked through the sibling skill's `run.sh` — no duplicated implementation.

The payoff of this split is straightforward: only want the audio archived? Use `yaya-xdl`. Only need speaker turns? `yaya-diarize`. Need a transcript? `yaya-asr`. Only the full X Space → notes flow needs `yaya-xspace`.

> 📐 **Implementation details and measured performance** live in [TECHNICAL.md](TECHNICAL.md) (in Chinese): model list, caching, parallel design, per-stage timings (119-minute audio → a 29.3-minute run).

## Why this exists

**Good content has to be saved before it can be processed.** X offers no archive or search for Spaces, and replays are deleted after 30 days — **download is archiving**, otherwise that audio is gone forever. What you save no longer evaporates with a platform's policies: note by note, it compounds into a content library of your own — cite it any time, replay it any time.

Running locally also means: free, zero logins, no cloud accounts.

## Skills

**Hero (scenario skill)**

| Skill | What it does |
|---|---|
| [yaya-xspace](skills/yaya-xspace/) | X Space link → distilled Chinese notes (verbatim quotes / key terms / enumerations fully preserved) |

**Supporting (atomic skills — the pipeline above is built from these, usable standalone)**

| Skill | What it does |
|---|---|
| [yaya-xdl](skills/yaya-xdl/) | X Space link → audio.m4a (download = archive) |
| [yaya-asr](skills/yaya-asr/) | Any audio/video → speaker-labeled text (transcribe ∥ separate, in parallel) |
| [yaya-diarize](skills/yaya-diarize/) | Audio → speaker timeline turns.json (who spoke when) |

## Roadmap

- ✅ **Wave 1**: X Space → notes + share card (the pipeline above)
- 🔜 **Next**: web-first outputs & self-hosted archiving — each Space becomes an interactive page (click a segment, hear that moment), audio lands in your own storage; the 30-day replay expiry is no longer the end
- 🔜 **Later**: more tools for writers (transcription/separation are atomic — podcasts, videos, or voice memos from any source can enter the same pipeline)

## Models (auto-downloaded on first run, nothing to prepare)

| Model | Purpose | Size | Location | Source |
|---|---|---|---|---|
| whisper-large-v3-turbo (MLX) | Transcription | **~1.5GB** | `~/.cache/huggingface/` (shared globally) | HuggingFace |
| pyannote segmentation + CAM++ voiceprint | Speaker separation | ~33MB | `skills/yaya-asr/models/` (gitignored) | GitHub Releases |

- Both are **token-free**; they download on the first run of the corresponding skill and never again.
- Downloading Whisper requires access to HuggingFace. On unstable networks set a mirror first: `export HF_ENDPOINT=https://hf-mirror.com`.
- Disk-sensitive? The 1.5GB transcription model is the big one; separation models are only 33MB.

## Where your data lives (outputs & archives)

**Data follows the skill**: outputs, audio archives and caches all live under the skill's own `out/` — deleting the skill folder deletes the data, and `git pull` updates leave it untouched (`out/` is gitignored).

```
skills/yaya-xspace/out/<space-id>/   ← one directory per Space, everything inside
├── audio.m4a                        audio archive (kept by default — download = archive)
├── distilled.md                     ★ the distilled notes
├── audio.labeled.json / audio.dialog.txt / …   transcript artifacts
└── .audio.asr/                      intermediate caches (deleting only costs recompute time)
```

- Deleting one Space = deleting one directory. Don't want the audio kept? Add `--no-keep-audio`.
- ⚠️ `out/` is your private data (notes + audio) and is listed in `.gitignore` — it will never be committed. (`demo/` is a hand-picked public sample, unrelated to `out/`.)

## Install

Skills are plain Markdown + scripts (the Agent Skills format) — **not bound to any single agent**. Claude Code, Codex, Cursor, Windsurf, ZCode, and anything else that supports the format can install and run them.

```bash
# Option 1: plugin marketplace (incremental updates)
/plugin marketplace add eatmoreduck/yaya-skills
/plugin install yaya-skills@yaya-skills

# Option 2: skills CLI
npx skills add eatmoreduck/yaya-skills

# Option 3: manual (project-level)
# Copy or symlink the skills/<name>/ directories you need into <project>/.agents/skills/
# ⚠️ yaya-xspace depends on yaya-xdl and yaya-asr; yaya-asr depends on yaya-diarize — copying one alone breaks it
```

## Design principles

1. **Local-first**: if it can run locally, it never touches the cloud. Audio never leaves your machine (transcription is fully local; only the extracted text goes to the LLM).
2. **Cut filler, never information**: distillation means removing redundancy, not summarizing away substance. Quotable lines, key terms, and enumerations must survive intact.
3. **Atomic capabilities, decoupled from business**: `yaya-asr` doesn't know what a Space is; scenario skills only add the part that is uniquely theirs.
4. **Honest boundaries**: every skill states what it cannot do, instead of pretending to handle everything.

## Repository layout

```
yaya-skills/
├── .claude-plugin/
│   └── marketplace.json     ★ declares which skills this repo ships
├── demo/                    ★ sample output from a real session (hand-picked, public)
├── skills/
│   ├── yaya-asr/            atomic (no deps)
│   │   ├── SKILL.md
│   │   ├── README.md
│   │   ├── run.sh
│   │   ├── scripts/asr.py
│   │   └── models/          separation models (gitignored, auto-downloaded)
│   ├── yaya-xdl/            atomic (no deps)
│   │   └── SKILL.md / README.md / run.sh / xdl.py
│   ├── yaya-diarize/        atomic (no deps)
│   │   └── SKILL.md / README.md / run.sh / diarize.py
│   └── yaya-xspace/         scenario orchestrator (depends on yaya-xdl + yaya-asr)
│       ├── SKILL.md
│       ├── README.md
│       ├── run.sh
│       ├── distill.py
│       ├── card.py          share-card renderer: distilled.md → hand-drawn PNG
│       ├── fonts/           handwriting fonts (OFL, used by the renderer)
│       └── out/             outputs & audio archives (gitignored — data follows the skill)
├── README.md
└── TECHNICAL.md             architecture overview + measured performance
```

## Adding a new skill

This repo is **one repository, many skills**. Three steps:

1. **Create the directory**: `skills/yaya-<name>/` with a `SKILL.md` (the frontmatter must include `name`/`description` — the description decides when an agent thinks to use it).
2. **Register**: add one line `"./skills/yaya-<name>"` to `plugins[0].skills[]` in `.claude-plugin/marketplace.json`. **This step is mandatory**: when `source` is `"./"` with an explicit skills list, only the listed directories are loaded — `skills/` is not scanned automatically.
3. **Declare dependencies**: if it depends on another skill in this repo (e.g. yaya-asr), state the dependency direction and the addressing path in its SKILL.md (the current convention: sibling directory `../yaya-asr`), and what happens when it's missing.

Keep the `yaya-` prefix for all skills. A local skill directory (e.g. `~/.zcode/skills/`) is a different thing from this repo: the repo is the source; installation happens via the marketplace or manual symlinks.

## Naming

All skills use the `yaya-` prefix.

## Follow & Contact

<table>
  <tr>
    <td align="center" width="50%">
      <img src="assets/official-account.jpg" width="200" alt="WeChat official account QR"><br>
      <sub>WeChat Official Account 「多吃鸭」 · updates, requests, chat</sub>
    </td>
    <td align="center" width="50%">
      <img src="assets/wechat-personal-qr.png" width="200" alt="Personal WeChat QR"><br>
      <sub>Personal WeChat · questions & requests, I reply fast</sub>
    </td>
  </tr>
</table>

## License

MIT
