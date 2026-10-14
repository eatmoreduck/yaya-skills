# Contributing Guide

> [中文版](CONTRIBUTING.md)

Thanks for wanting to contribute to yaya-skills. All the rules of this repo live in [AGENTS.md](AGENTS.md) — **read it end to end before touching anything**, especially the "Hard constraints (learned the hard way, do not revert)" section. Below are only the most critical bits.

## Before you start

1. **Read AGENTS.md**. Every hard constraint in there corresponds to a real incident (accidental file deletion, cache invalidation, speaker letter leakage…). If your change conflicts with a hard constraint, assume you are wrong.
2. **Read the contract before changing the contract**:
   - Changing transcription/diarization/caching in `yaya-asr` → read `skills/yaya-asr/SKILL.md` first (the output file list is a stable interface; `<name>.labeled.json` is consumed by downstream programs — its format must not change)
   - Changing the distillation prompt in `yaya-xspace` → read `skills/yaya-xspace/SKILL.md` and the design principles in the root README first
3. **New skills must be registered** in `.claude-plugin/marketplace.json` under `plugins[0].skills[]` — when `source: "./"` and skills are listed explicitly, `skills/` is not auto-scanned. Steps in the root README ("如何新增一个 skill").

## Iron rules of this repo

- **One-way dependencies**: orchestration layer → atomic skills; sibling skills call each other via `run.sh` subprocesses only. No reverse dependencies, no copy-paste implementations.
- **Data lives with the skill**: outputs, audio, and caches go into the skill's own `out/`. There is no relocation switch. `out/` is gitignored wholesale — audio and notes from private Spaces must **never** enter this public repo. `demo/` contains hand-picked public samples; never mix it with `out/`.
- **"Distill" is not "summarize"**: the contract is yield — cut small talk and filler, but verbatim quotes, key terms, each speaker's positions, and enumerated lists must all survive. Putting "summarize" in the prompt makes the LLM optimize for brevity, which is wrong.
- **No speaker letter labels in user-facing text**: `dialog.txt` / `dialog.srt` / `distilled.md` use real names; `labeled.json` / `turns.json` keep letters (machine interface).

## Commits & verification

There is no test suite. Verification is this command set (see AGENTS.md):

```bash
skills/yaya-asr/.venv/bin/python -m py_compile skills/yaya-asr/scripts/asr.py skills/yaya-xspace/distill.py skills/yaya-xdl/xdl.py skills/yaya-diarize/diarize.py
bash -n skills/yaya-asr/run.sh && bash -n skills/yaya-xspace/run.sh && bash -n skills/yaya-xdl/run.sh && bash -n skills/yaya-diarize/run.sh
# End-to-end: run a Space that already has cached data; on a cache hit it costs a single LLM call
bash skills/yaya-xspace/run.sh "https://x.com/i/spaces/<id>"
```

- Commit messages in Chinese (see `git log` for style: `feat:` / `fix:` / `polish:` / `docs:` + one sentence covering what and why). English is fine for PR discussions.
- In your PR description, state: what changed, why, and how you verified it (which of the commands above you ran).

## Communication

Chinese is the working language; English is welcome. Use the issue templates; if you are not sure it's a bug, open an issue describing the phenomenon.
