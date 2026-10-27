#!/usr/bin/env python3
"""PDF 字体子集密码解码器（按词判定，词典二选一）。"""
import re, json, glob, os, sys
from collections import defaultdict, Counter

DICT = set()
for _p in ('/usr/share/dict/words', '/usr/share/dict/web2a', '/usr/share/dict/propernames'):
    try:
        with open(_p, errors='ignore') as f:
            for w in f:
                w = w.strip()
                if w.isalpha(): DICT.add(w.lower())
    except FileNotFoundError:
        pass
DICT |= {'waibaidu','huangpu','lujiazui','shikumen','zhujiajiao','xujiahui','zongzi',
         'qingtuan','yuanxiao','tangyuan','guzheng','cloisonne','sakyamuni',
         'bund','pudong','nanjing','suzhou','yangtze','dianshan','wusong','chunshen'}

MARK = set('!#$%&*+/<=>@[\\]^_`{|}~:;')
STRIP_R = '.,;:!?)]}"”’、'
STRIP_L = '([{"“‘'

def pat(w):
    m, out = {}, []
    for c in w:
        if c not in m: m[c] = len(m)
        out.append(m[c])
    return tuple(out)

IDX = defaultdict(list)
for _w in DICT:
    IDX[(len(_w), pat(_w))].append(_w)

SEED_0003 = {
 '!':'W','"':'a','#':'i','$':'b','%':'d','&':'u',"'":'B','(':'r',')':'g','*':'e',
 '+':'m',',':'o','-':'s','.':'t','/':'f','0':'n','1':'S','2':'h','3':'l','4':'c',
 '5':'y','6':'v','7':'1','8':'9','9':'0',':':'7',';':'G','<':'H','=':'p','>':'P',
 '?':'k','@':'w','A':'8','B':'6','C':'C','D':'M','E':'2','F':'O','G':'F','H':'L',
}

def split_tok(t):
    i, j = 0, len(t)
    while i < j and t[i] in STRIP_L: i += 1
    while j > i + 1 and t[j-1] in STRIP_R: j -= 1
    return t[:i], t[i:j], t[j:]

def decode_core(core, mp):
    plain = core
    dec = ''.join(mp.get(c, c) for c in core)
    has_mark = any(c in MARK for c in core)
    p_ok = plain.lower().strip("'") in DICT
    d_ok = dec.lower().strip("'") in DICT
    if has_mark and not p_ok: return dec
    if d_ok and not p_ok:    return dec
    if p_ok:                 return plain
    return dec if has_mark else plain

def score(mp, lines):
    hit = tot = 0
    for l in lines:
        for t in l.split():
            _, core, _ = split_tok(t)
            if len(core) < 3: continue
            tot += 1
            if decode_core(core, mp).lower().strip("'") in DICT: hit += 1
    return hit / max(1, tot)

def solve(lines, seed=None, rounds=12):
    mp = dict(seed or {})
    words = []
    for l in lines:
        for t in l.split():
            _, core, _ = split_tok(t)
            if len(core) >= 2 and any(c.isalpha() or c in MARK for c in core):
                words.append(core)
    words.sort(key=len)
    for _ in range(rounds):
        gain = 0
        for w in words:
            lw = w.lower()
            cands = IDX.get((len(lw), pat(lw)))
            if not cands: continue
            good = [c for c in cands
                    if all((cc not in mp) or mp[cc] == pc for cc, pc in zip(lw, c))]
            if len(good) == 1:
                for cc, pc in zip(lw, good[0]):
                    if cc not in mp: mp[cc] = pc; gain += 1
        for _v in range(4):
            votes = defaultdict(Counter)
            for w in words:
                lw = w.lower()
                cands = IDX.get((len(lw), pat(lw)))
                if not cands: continue
                good = [c for c in cands
                        if all((cc not in mp) or mp[cc] == pc for cc, pc in zip(lw, c))]
                if not good or len(good) > 25: continue
                for cc, pc in zip(lw, good[0]):
                    if cc not in mp: votes[cc][pc] += 1
            used = Counter(mp.values()); g2 = 0
            for cc, cnt in votes.items():
                if cc in mp: continue
                for pc, _n in cnt.most_common():
                    if used[pc] == 0:
                        mp[cc] = pc; used[pc] += 1; g2 += 1; break
            gain += g2
            if not g2: break
        if not gain: break
    return mp

def decode_line(l, mp):
    out = []
    for piece in re.split(r'(\s+)', l):
        if not piece.strip():
            out.append(piece); continue
        L, core, R = split_tok(piece)
        out.append(L + decode_core(core, mp) + R)
    return ''.join(out)

CACHE = 'cipher_maps.json'

def build_maps(paths=None, quiet=False):
    from pdftext import lines_of
    if paths is None:
        raise SystemExit('build_maps 需要显式给出 pdf 路径列表（命令行入口见 run.sh decrypt）')
    res = {}
    for f in paths:
        ls = lines_of(f)
        cl = [l for l in ls if sum(1 for c in l if c in MARK) >= 1]
        best, bs = {}, 0.0
        if cl:
            for sd in ((None, SEED_0003) if '0003' in f else (None,)):
                mp = solve(cl, sd); s = score(mp, cl)
                if s > bs: best, bs = mp, s
        res[os.path.basename(f)] = {'map': best, 'score': round(bs, 3), 'lines': len(cl)}
        if not quiet:
            print(f'{os.path.basename(f)[:6]}  候选行={len(cl):4d}  词典命中={bs:6.1%}  已知码={len(best)}')
    json.dump(res, open(CACHE, 'w'), ensure_ascii=False, indent=1)
    return res

if __name__ == '__main__':
    print('本脚本是库，命令行入口请用: run.sh decrypt <pdf> ...', file=sys.stderr)
    sys.exit(1)
