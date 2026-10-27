#!/usr/bin/env python3
"""清洗解码文本：去水印碎片、去 Markdown 星号、修个别错词，输出到 clean/。"""
import re, glob, os, sys

# 密文标记：字体子集混淆后的字符落在这些符号上，正常英文里几乎不出现
CIPHER_MARKS = set('?!"()# $%&*+/<=>@[\\]^_`{|}~;:')

FIX = {
 "WellsB Bridge": "Wells' Bridge",
 '"ncien. Gree?': 'ancient Greek',
 '"ncien. Greek': 'ancient Greek',
 '"ncien Gree?': 'ancient Greek',
 'Gree? style': 'Greek style',
 'Par?.': 'Park.',
 'Par?': 'Park',
 'Ban?': 'Bank',
 'bronKe': 'bronze',
 'Ban? of Chin"': 'Bank of China',
 'Chin"': 'China',
 'tw,': 'two',
 't,': 'to',
 'Wnion': 'Union',
 'Sowin)': 'Savings',
 'Or. Lec,': 'Art Deco',
 'Q"-."': 'East',
 'V"KK': 'Jazz',
 'S9yvo': '1856',
 # 0003 年份/专名（子集数字映射：7=1 8=9 9=0 :=7 E=2 J=3 A=8 B=6 I=4 M=5）
 '788B': '1996', '78E8': '1929', '78EJ': '1923', '78E:': '1927', '78J:': '1937',
 '7ABA': '1868', '7ABI': '1864', '7AI8': '1848', '7BAM': '1685', 'E99J': '2003',
 'JI stories': '34 stories', '7: stories': '17 stories',
 '43,4? tower': 'clock tower',
 'Phe Q"-. R- Sed': 'The East Is Red',
 'Far Q"-."': 'Far East.',
 'Far Q"-.”': 'Far East',
 'merchanto Sir Uictor 1"--,,0': 'merchant, Sir Victor Sassoon',
 '1"--,,0 House': 'Sassoon House',
 'Uictor 1"--,,0': 'Victor Sassoon',
 'Fairmon. Peace': 'Fairmont Peace',
 'Buildin)': 'Building',
 'merchanto': 'merchant,',
 # 0003 片段级修复（子集混用残留）
 'the first page of th". b,,?': 'the first page of the book',
 'the firs. page of th". b,,?': 'the first page of the book',
 'development "nd changes': 'development and changes',
 'the former church "partments': 'the former church apartments',
 'NanTin) Soad "nd the Bund': 'Nanjing Road and the Bund',
 '43,4? in Osi"': 'clock in Asia',
 'par? in China': 'park in China',
 'films "nd television': 'films and television',
 'developmen. "nd changes': 'development and changes',
 '"partments': 'apartments',
 'piewipe': 'museums',
 'glaKed': 'glazed',
 '120smetreslon)': '120-metre-long',
 '(espec.': 'respect.',
 '(elief': 'relief',
 'ceilin)': 'ceiling',
 '(oof': 'roof',
 'weddin)': 'wedding',
 'buildin)': 'building',
 'peopleBs': "People's",
 'PeopleBs': "People's",
 '789:': '1907',
 '(enamed': 'renamed',
}


DICT = set()
for _p in ('/usr/share/dict/words', '/usr/share/dict/web2a'):
    try:
        for _w in open(_p, errors='ignore'):
            _w = _w.strip().lower()
            if _w.isalpha(): DICT.add(_w)
    except FileNotFoundError:
        pass

def fix_t(text):
    """词尾 '.' 实为 t 的情况：developmen. -> development。"""
    def f(m):
        w = m.group(1)
        if w.lower() not in DICT and (w + 't').lower() in DICT:
            return w + 't'
        return m.group(0)
    return re.sub(r'\b([A-Za-z]{3,})\.(?=\s|$)', f, text)

def fix_trailing_o(text):
    """词尾 o 实为逗号：monumento there -> monument, there。"""
    def f(m):
        w = m.group(1)
        if (w + 'o').lower() not in DICT and w.lower() in DICT:
            return w + ','
        return m.group(0)
    return re.sub(r'\b([A-Za-z]{3,})o(?=\s)', f, text)

def join_hyphen(text):
    """行尾连字符断词：eye- catching -> eye-catching。"""
    return re.sub(r'([A-Za-z])-\s+([A-Za-z])', r'\1-\2', text)

# 水印/页脚碎片（整行匹配才删）
JUNK_EXACT = {'师在', 'aosi', 'glaosi', '龙老师在上', '龙老师在', '龙老师在',
              '8911988343', '小红书账号8911988343', '上海英语导游证', '考试面试', '口', '译'}

def is_junk(l):
    t = l.strip()
    if t in JUNK_EXACT: return True
    if re.fullmatch(r'[a-z]{3,6}', t) and t in ('aosi', 'glaosi'): return True
    if re.search(r'音标参考|中文谐音', t): return True
    if re.fullmatch(r'[.\s·…]+', t): return True
    return False

def clean_line(l):
    l = l.replace('**', '')
    l = re.sub(r'\.{6,}\s*\d*$', '', l)      # 目录点线
    return l.rstrip()

def apply_fix(text):
    """逐类应用 FIX 表。安全规则（踩过坑，别改回无条件 replace）：

    - 含密文标记（? " ( )）的键：正常英文不会出现这些组合，直接替换安全
    - 纯字母数字键：必须整词匹配 + 词典保护
      曾用 `s.replace('t,', 'to,')` 无条件全局替换，把
      `The market, the park` 改成 `The marketo the park`——真实事故。
    """
    for a, b in FIX.items():
        if any(ch in a for ch in CIPHER_MARKS):
            text = text.replace(a, b)
            continue

        pattern = re.compile(r'(?<![A-Za-z0-9])' + re.escape(a) + r'(?![A-Za-z0-9])')

        def repl(m, _src=a, _dst=b):
            if _src.lower() in DICT:      # 原词本就是正常英文，不动
                return m.group(0)
            return _dst

        text = pattern.sub(repl, text)
    return text


def clean_file(p, out, apply_fixes=True):
    """清理一个文本文件。apply_fixes=False 时跳过 FIX 表，只做通用清洗。

    非密文文档必须传 False：FIX 表是个案修补，全局套用会误伤正常英文。
    """
    ls = [clean_line(l) for l in open(p, encoding='utf-8', errors='replace').read().split('\n')]
    ls = [l for l in ls if not is_junk(l)]
    s = '\n'.join(ls)
    s = join_hyphen(s)
    if apply_fixes:
        s = apply_fix(s)
        s = fix_t(s)
        s = fix_trailing_o(s)
    open(out, 'w', encoding='utf-8').write(s)
    return s

if __name__ == '__main__':
    print('本脚本是库，命令行入口请用: run.sh decrypt <pdf> ...', file=sys.stderr)
    sys.exit(1)
