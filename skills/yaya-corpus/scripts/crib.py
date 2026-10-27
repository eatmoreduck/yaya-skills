#!/usr/bin/env python3
"""已知明文攻击：用同一 PDF 内的干净文本（标题、重复短语）破解该文件的字体密码。

原理：加密只是「按首次出现顺序」把字符重排到 ASCII 连续码位，
      所以同一份文档里同一个英文短语的干净形式与密文形式，词形（长度+重复模式）完全一致。
      拿标题/干净句做 crib，即可零歧义锁定字母映射，再做约束传播补全。
"""
import re, json, glob, os, sys
from collections import defaultdict, Counter
import cipher as C
from pdftext import lines_of, cjk_ratio

MARK = C.MARK

def tokens_of(lines):
    clean, cipher = [], []
    for l in lines:
        for t in l.split():
            head, core, tail = C.split_tok(t)
            if len(core) < 2: continue
            if any(c in MARK for c in core):
                cipher.append(core)
            elif core.replace("'", "").isalpha():
                clean.append((core, l))
    return clean, cipher

def crib_map(lines, min_support=1):
    clean, cipher = tokens_of(lines)
    # 干净词的词形索引
    cw = defaultdict(set)
    for w, _ in clean:
        lw = w.lower()
        cw[(len(lw), C.pat(lw))].add(lw)
    votes = defaultdict(Counter)
    support = defaultdict(set)
    for tok in cipher:
        lt = tok.lower()
        cands = cw.get((len(lt), C.pat(lt)))
        if not cands or len(cands) > 2:      # 歧义大就跳过
            continue
        for cand in cands:
            for cc, pc in zip(lt, cand):
                votes[cc][pc] += 1
                support[(cc, pc)].add(cand)
    mp = {}
    for cc, cnt in votes.items():
        pc, n = cnt.most_common(1)[0]
        if n >= min_support:
            mp[cc] = pc
    # 去冲突：同一明文字母只能被一个密码字符占用（保留票数高的）
    return mp, votes

if __name__ == '__main__':
    print('本脚本是库，命令行入口请用: run.sh decrypt <pdf> ...', file=sys.stderr)
    sys.exit(1)
