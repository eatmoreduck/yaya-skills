#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""破解 PDF 字体子集混淆（文本层被"加密"），输出可读文本 + 可疑词清单。

典型病症：PDF 页面显示正常，但复制/提取出来是 `!"#$"#%& '(#%)*.`。
规律是按首次出现顺序把第 k 个不同字符映射到 0x21+k，同一份 PDF 内稳定。

用法：
  python3 decrypt.py <a.pdf | 目录> [-o 输出目录] [--calib 干净稿.pdf ...]

流程：pdftext 提取+水印过滤 → final2 多候选映射择优 → normalize 逐类修补
产物：<base>.txt（解码文本）、<base>.suspect.txt（词典外可疑词，供人工核）、decode_report.json
"""
import argparse, glob, json, os, re, sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cipher as C
import final2 as F
import normalize as N
from pdftext import lines_of


def collect(paths):
    """接受 pdf 文件或目录，返回 pdf 文件列表（按名排序）。"""
    out = []
    for p in paths:
        if os.path.isdir(p):
            out.extend(sorted(glob.glob(os.path.join(p, '*.pdf'))))
        elif os.path.isfile(p) and p.lower().endswith('.pdf'):
            out.append(p)
        else:
            print(f'! 跳过（不是 pdf）: {p}', file=sys.stderr)
    return out


def decode_one(pdf, outdir):
    """单文件解码，返回 (报告 dict, 可疑词列表)。"""
    lines = lines_of(pdf)
    mp, score, scheme = F.pick_map(lines)
    decoded = [C.decode_line(l, mp) for l in lines]

    base = os.path.splitext(os.path.basename(pdf))[0]
    raw_path = os.path.join(outdir, base + '.txt')
    open(raw_path, 'w', encoding='utf-8').write('\n'.join(decoded) + '\n')

    # FIX 表是个案知识，只在确实有密文残余时套用——干净文本绝不能走，
    # 否则 `The market,` 会被 't,'->'to,' 这类条目改成 `The marketo`。
    encrypted = scheme != 'plain'
    clean_txt = N.clean_file(raw_path, raw_path, apply_fixes=encrypted)

    # 可疑词 = 词典外的词（含专名，故必须人工过一遍），按语言分升序排（最可疑在前）。
    # 不用阈值过滤：实测 `Nanjin`(-3.16) 比校准阈值(-3.78) 还高，阈值会漏掉真错词。
    suspect = Counter()
    for line in clean_txt.split('\n'):
        for w in re.findall(r"[A-Za-z]{3,}", line):
            if F.in_dict(w):
                continue
            suspect[w] += 1

    if suspect:
        sus_path = os.path.join(outdir, base + '.suspect.txt')
        ranked = sorted(suspect.items(), key=lambda kv: F.word_ll(kv[0]))
        with open(sus_path, 'w', encoding='utf-8') as f:
            f.write('# 词典外词，按语言分升序（越靠前越像解码残留）；'
                    '专名属正常，人工逐条确认\n')
            for w, n in ranked:
                f.write(f'{n}\t{F.word_ll(w):7.3f}\t{w}\n')

    report = {'scheme': scheme, 'score': round(score, 2), 'chars': len(mp),
              'lines': len(lines), 'suspect': suspect.most_common(60)}
    return report, suspect


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('inputs', nargs='+', help='PDF 文件或目录')
    ap.add_argument('-o', '--outdir', default=None, help='输出目录（默认 skill 的 out/decrypt/）')
    args = ap.parse_args()

    outdir = args.outdir or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'out', 'decrypt')
    os.makedirs(outdir, exist_ok=True)

    pdfs = collect(args.inputs)
    if not pdfs:
        print('没有可处理的 pdf', file=sys.stderr)
        return 1

    report = {}
    for pdf in pdfs:
        try:
            rep, sus = decode_one(pdf, outdir)
        except Exception as e:
            print(f'❌ {os.path.basename(pdf)}: {e}', file=sys.stderr)
            continue
        report[os.path.splitext(os.path.basename(pdf))[0]] = rep
        print(f"{os.path.basename(pdf)[:28]:30s} 方案={rep['scheme']:6s} "
              f"语言分={rep['score']:7.2f} 码表={rep['chars']:3d} 可疑={len(sus):3d}")

    json.dump(report, open(os.path.join(outdir, 'decode_report.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print(f'\nDONE {len(report)} 个文件 -> {outdir}')
    print('⚠️ 可疑词清单（*.suspect.txt）必须人工核：按语言分升序，越靠前越像残留；'
          '年份/专名/数字最容易错，别直接信。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
