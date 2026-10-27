#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""取 docx 全文 + 定位中文小标题（本地文档 MCP 没有全文导出时的 fallback）。

用法:
  python3 dump_docx.py /abs/in.docx            # 打印 [idx]<style> text
  python3 dump_docx.py /abs/in.docx --headings # 只列中文小标题 index
"""
import re, sys, zipfile
import xml.etree.ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
CJK = r'\u3000-\u303f\u3400-\u9fff\uff00-\uffef'   # 中文字符 + 全角标点范围


def load_paragraphs(docx):
    """返回 [(style, text)]；已过滤空段（保留空段会打乱 index）。"""
    root = ET.fromstring(zipfile.ZipFile(docx).read("word/document.xml"))
    out = []
    for p in root.iter(W + "p"):
        text = "".join(t.text or "" for t in p.iter(W + "t")).strip()
        if not text:
            continue
        pPr = p.find(W + "pPr")
        style = ""
        if pPr is not None:
            st = pPr.find(W + "pStyle")
            if st is not None:
                style = st.get(W + "val") or ""
        out.append((style, text))
    return out


def is_heading(style, text):
    """中文章节小标题：样式 3/5，或无样式且不含拉丁字母。"""
    if style in ("3", "5"):
        return True
    stripped = re.sub(f"[{CJK}]", "", text)
    return not re.search(r"[A-Za-z]", stripped)


def _fix_digit_letter(m):
    """数字与字母粘连补空格，但年代/序数词不拆（1930s、18th 必须保持完整）。"""
    digits, letters = m.group(1), m.group(2)
    if letters in ("s", "st", "nd", "rd", "th"):
        return digits + letters
    return digits + " " + letters


def clean_en(s):
    """英文语料清洗：全角标点转半角、剔除中文、修粘连与缺空格、引号归一化。"""
    for a, b in [('，', ', '), ('。', '. '), ('！', '! '), ('？', '? '), ('；', '; '), ('：', ': '), ('、', ', ')]:
        s = s.replace(a, b)
    s = re.sub(f"[{CJK}]+", " ", s)
    s = s.replace('“', '"').replace('”', '"').replace('‘', "'").replace('’', "'")
    s = re.sub(r"(?<=[a-zA-Z])(?=\d)", " ", s)          # mid18th -> mid 18th
    s = re.sub(r"(\d+)([a-zA-Z]+)", _fix_digit_letter, s)  # 700yearold -> 700 yearold
    s = re.sub(r"([a-z]\.)(?=[A-Z])", r"\1 ", s)        # years.The -> years. The
    s = re.sub(r"([a-z],)(?=[A-Za-z])", r"\1 ", s)      # baby,but -> baby, but
    for a, b in [("fortuneteller", "fortune teller"), ("highrises", "high rises"),
                 ("Mingdynasty", "Ming dynasty"), ("wellknown", "well known")]:
        s = s.replace(a, b)
    return re.sub(r"\s{2,}", " ", s).strip()


if __name__ == "__main__":
    path = sys.argv[1]
    paras = load_paragraphs(path)
    if "--headings" in sys.argv:
        for i, (st, t) in enumerate(paras):
            if is_heading(st, t):
                print(f"{i}\t{st}\t{t}")
    else:
        print(f"TOTAL {len(paras)} paragraphs")
        for i, (st, t) in enumerate(paras):
            print(f"[{i}]{'<' + st + '>' if st else ''} {t}")
