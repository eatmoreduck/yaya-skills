#!/usr/bin/env python3
"""PDF 文本层提取 + 水印过滤（供其他脚本 import）。"""
import re
import pymupdf

CJK = re.compile(r'[\u4e00-\u9fff]')
WM = re.compile(r'8911988343|xiaohongshu|微信|xuhuilong|老师在上海|小红|⼩红书')

_TRANS = str.maketrans({
    '⼩':'小','⻰':'龙','⻓':'长','⼤':'大','⼀':'一','⼈':'人','⻔':'门','⻄':'西',
    '⻛':'风','⻢':'马','⻋':'车','⻅':'见','⻥':'鱼','⻦':'鸟','⼴':'广','⼭':'山',
    '⼦':'子','⼥':'女','⼿':'手','⽂':'文','⽉':'月','⽇':'日','⽕':'火','⽔':'水',
    '⽣':'生','⽤':'用','⽥':'田','⽩':'白','⽬':'目','⽯':'石','⽰':'示','⽴':'立',
    '⽶':'米','⽹':'网','⽺':'羊','⽼':'老','⽽':'而','⽿':'耳','⾁':'肉','⾃':'自',
    '⾄':'至','⾆':'舌','⾏':'行','⾐':'衣','⾔':'言','⾛':'走','⾜':'足','⾝':'身',
    '⾦':'金','⾨':'门','⾳':'音','⾴':'页','⾵':'风','⾷':'食','⾸':'首','⾼':'高',
    '⿂':'鱼','⿃':'鸟','⿊':'黑','⾖':'豆','⾯':'面','⺠':'民','⻘':'青','⻝':'食',
    '⻮':'齿','⻨':'麦','⻩':'黄','⻤':'鬼','⻥':'鱼','⻦':'鸟','⻧':'卤','⻬':'齐',
})

def norm(s):
    return s.translate(_TRANS)

def cjk_ratio(s):
    return len(CJK.findall(s)) / max(1, len(s))

def lines_of(path, pages=None):
    d = pymupdf.open(path)
    out = []
    rng = range(d.page_count) if pages is None else pages
    for i in rng:
        for raw in (d[i].get_text() or '').split('\n'):
            l = norm(raw).strip()
            if not l or WM.search(l):
                continue
            if re.fullmatch(r'[\d\s\-—/年月日第页]+', l):
                continue
            out.append(l)
    return out
