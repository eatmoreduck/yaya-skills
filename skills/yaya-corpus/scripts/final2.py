#!/usr/bin/env python3
"""最终解码：多候选映射 + 三元组择优，并输出「可疑词」清单供人工核校。"""
import re, json, glob, os, sys, math, statistics
from collections import defaultdict, Counter
import cipher as C
import crib as CR
from pdftext import lines_of

DICT = C.DICT
MARK = C.MARK

TRI = defaultdict(Counter)
for w in DICT:
    s = f'#{w}$'
    for i in range(len(s) - 2):
        TRI[s[i:i+2]][s[i+2]] += 1
TOTAL = {k: sum(v.values()) for k, v in TRI.items()}
FLOOR = 1e-5

def word_ll(w):
    s = f'#{w.lower()}$'
    tot = 0.0
    for i in range(len(s) - 2):
        key = s[i:i+2]
        c = TRI.get(key)
        p = (c[s[i+2]] / TOTAL[key]) if c and c[s[i+2]] and TOTAL.get(key) else FLOOR
        tot += math.log(p)
    return tot / max(1, len(s) - 2)

def text_ll(t):
    vs = [word_ll(w) for w in re.findall(r"[A-Za-z']+", t) if len(w) > 1]
    return statistics.mean(vs) if vs else -99


# /usr/share/dict/words 是 Webster 1913 词根词典，不含屈折形式（walked 查不到）。
# 剥后缀再查一次，否则可疑词清单会被 walked / buildings / visitors 全部淹没。
SUFFIXES = ('s', 'es', 'ed', 'd', 'ing', 'ly', 'er', 'est', 'ies', 'ied')


def in_dict(w):
    """词在词典里，或剥掉常见屈折后缀后词干在词典里。"""
    w = w.lower().strip("'")
    if not w:
        return False
    if w in DICT:
        return True
    for suf in SUFFIXES:
        if not w.endswith(suf):
            continue
        stem = w[:-len(suf)]
        if len(stem) >= 3 and stem in DICT:
            return True
        # cry -> cries/ried，y 还原
        if suf in ('ies', 'ied') and len(stem) >= 2 and (stem + 'y') in DICT:
            return True
        # walk -> walking 的词干双写情形（stopped -> stop）
        if len(stem) >= 3 and stem[-1] == stem[-2] and stem[:-1] in DICT:
            return True
    return False

def candidates(lines):
    cl = [l for l in lines if any(c in MARK for c in l)]
    out = {'seed': dict(C.SEED_0003),
           'seed+': C.solve(cl, C.SEED_0003),
           'free': C.solve(cl, None)}
    cm, _ = CR.crib_map(lines)
    if cm:
        out['crib'] = cm
        out['crib+'] = C.solve(cl, cm)
    return out, cl

def pick_map(lines):
    cands, cl = candidates(lines)
    if not cl:
        return {}, 1.0, 'plain'
    best = max(((mp, text_ll('\n'.join(C.decode_line(l, mp) for l in cl)), n)
                for n, mp in cands.items()), key=lambda x: x[1])
    return best


if __name__ == '__main__':
    print('本脚本是库，命令行入口请用: run.sh decrypt <pdf> ...', file=sys.stderr)
    sys.exit(1)
