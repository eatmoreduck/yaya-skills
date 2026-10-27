#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 docx / pdf / txt 抽出纯文本（语料准备的第一步）。

用法：
  python3 extract.py <稿件.docx|.pdf|.txt> [-o 输出.txt] [--headings] [--raw]

- docx：走 zipfile 解析 word/document.xml，--headings 只列疑似小标题的行
- pdf ：走 pdftext（含水印行过滤、康熙部首归一）。文本层被混淆时输出会是乱码，
        此时改用 `run.sh decrypt` 破密，别在 extract 上打转
- txt ：原样读出
默认带清洗（全角标点转半角、剔除中文残句、修粘连与缺空格）；--raw 则原样输出。
"""
import argparse, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dump_docx import load_paragraphs, is_heading, clean_en


def read_docx(path, headings=False):
    paras = load_paragraphs(path)
    if headings:
        return None, [(i, st, t) for i, (st, t) in enumerate(paras) if is_heading(st, t)], len(paras)
    return [t for _, t in paras], None, len(paras)


def read_pdf(path):
    from pdftext import lines_of
    return lines_of(path)


def read_txt(path):
    return [l.rstrip('\n') for l in open(path, encoding='utf-8', errors='replace')]


def looks_encrypted(lines):
    """文本层被字体子集混淆的粗判：大量 0x21-0x7E 标点连排、几乎没有正常英文词。"""
    sample = '\n'.join(lines[:200])
    if not sample.strip():
        return False
    words = re.findall(r'[A-Za-z]{3,}', sample)
    marks = sum(1 for c in sample if c in '!#$%&*+/<=>@[\\]^_`{|}~')
    return marks > 30 and len(words) < marks * 0.3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('input')
    ap.add_argument('-o', '--output', default=None)
    ap.add_argument('--headings', action='store_true', help='只列出疑似小标题（docx）')
    ap.add_argument('--raw', action='store_true', help='不做英文清洗')
    args = ap.parse_args()

    ext = os.path.splitext(args.input)[1].lower()
    if ext == '.docx':
        lines, heads, total = read_docx(args.input, args.headings)
        if heads is not None:
            print(f'TOTAL {total} paragraphs，疑似小标题 {len(heads)} 条')
            for i, st, t in heads:
                print(f'{i}\t{st}\t{t}')
            return 0
    elif ext == '.pdf':
        lines = read_pdf(args.input)
        if looks_encrypted(lines):
            print('⚠️ 文本层疑似被字体子集混淆（提取结果是乱码）。', file=sys.stderr)
            print('   别在这里打转，改用: run.sh decrypt <这个pdf>', file=sys.stderr)
    elif ext in ('.txt', '.md'):
        lines = read_txt(args.input)
    else:
        print(f'不支持的类型: {ext}（只认 docx / pdf / txt / md）', file=sys.stderr)
        return 1

    if not args.raw:
        lines = [clean_en(l) for l in lines]
    lines = [l for l in lines if l.strip()]

    text = '\n'.join(lines) + '\n'
    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)  # -o 父目录不存在时自动建
        open(args.output, 'w', encoding='utf-8').write(text)
        print(f'OK {len(lines)} 行 -> {args.output}')
    else:
        sys.stdout.write(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
