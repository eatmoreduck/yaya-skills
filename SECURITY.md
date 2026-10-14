# 安全政策 / Security Policy

> 中文优先；English below。Chinese first, English below.

## 中文

### 支持的版本

个人项目，只为 `master` 最新提交提供安全修复，没有版本化发布。

### 如何报告安全问题

**请勿开公开 Issue**。请私信 [@eatmoreduck](https://x.com/eatmoreduck)（X / Twitter），描述问题与复现方式。会在尽力范围内尽快回应与修复。

### 范围说明（报告前先看）

- 本仓库是**本地运行的工具**：下载 X Space 音频、本地转写（MLX）、调用外部 LLM API（智谱）蒸馏。不部署任何服务端。
- 已知边界（属设计行为，不算漏洞）：转写稿与蒸馏文本会发送给 LLM API 提供商（这是蒸馏的必要条件，介意者可用 `--transcript-only` 只转写不蒸馏）；Space 音频与笔记落在本地 `out/`。
- **密钥安全**：`ZAI_CODING_CN_API_KEY` 等凭据只放环境变量或本机 shell 配置，**绝不提交进仓库**；发现含密钥的提交请立即报告。

## English

### Supported versions

Personal project — security fixes land on the latest `master` only. No versioned releases.

### Reporting a vulnerability

**Do NOT open a public issue.** DM [@eatmoreduck](https://x.com/eatmoreduck) on X/Twitter with a description and reproduction steps. I'll respond and fix on a best-effort basis.

### Scope notes (read before reporting)

- This repo is a **locally-run toolset**: X Space download, on-device transcription (MLX), and LLM distillation via an external API (Zhipu). Nothing is deployed as a service.
- Known boundaries (by design, not vulnerabilities): transcripts and distilled notes are sent to the LLM API provider (that's what distillation requires; use `--transcript-only` if you mind). Space audio and notes stay in your local `out/`.
- **Key hygiene**: credentials like `ZAI_CODING_CN_API_KEY` belong in env vars or local shell config, **never committed**. If you find a commit containing a key, report it immediately.
