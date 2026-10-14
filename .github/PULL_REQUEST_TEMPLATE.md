<!-- 中文优先；English welcome。PR 前请通读 AGENTS.md，尤其「硬约束（踩过坑的，别回退）」一节 / Read AGENTS.md first, especially "Hard constraints (learned the hard way, do not revert)" -->

## 改了什么 & 为什么 / What & Why

<!-- 一句话讲清楚，评审视角：fix / feat / polish / docs 哪类 -->

## 改动范围 / Scope

- [ ] 只动了实现目标必需的代码，没有连带重构 / Only code necessary for the goal; no drive-by refactoring
- [ ] `out/` 产物（音频/笔记/缓存）不在本次改动里 / No `out/` artifacts (audio/notes/caches) in this change
- [ ] 对外文本产物（dialog.txt / dialog.srt / distilled.md）无说话人字母标签 / No speaker letter labels in user-facing artifacts

## 验证方式 / Verification

- [ ] `py_compile` + `bash -n` 全过（命令见 AGENTS.md「验证命令」/ see AGENTS.md "验证命令"）
- [ ] 端到端跑过一场已有缓存的 Space（缓存命中，只花一次 LLM 调用）/ End-to-end run of a cached Space (single LLM call on cache hit)
- [ ] 涉及蒸馏提示词 / 分享卡 / 说话人改名：不破坏既有格式兼容（`- ` 与 `1. ` 列表、多种署名格式）/ If touching distillation prompt / card / speaker renaming: existing format compatibility intact (both `- ` and `1. ` lists, all signature formats)

## 回滚方式 / Rollback

<!-- 一句话：git revert <sha> 能干净回退，或说明需要手动步骤 / git revert <sha> reverts cleanly, or describe manual steps -->
