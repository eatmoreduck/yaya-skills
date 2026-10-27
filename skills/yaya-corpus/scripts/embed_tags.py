#!/usr/bin/env python3
"""把 LRC 歌词 + 封面 + 标签写入 MP3（USLT + SYLT + APIC，v2.3）。

用法：
  python3 embed_tags.py <目录> [--cover 封面.jpg] [--album 专辑名] [--artist 歌手]

- 目录下每个 mp3 找同名 .lrc；USLT 存整份 LRC 文本，SYLT 存逐行毫秒时间戳
- --album 省略时用目录名；--artist 省略时用 eatmoreduck
- --cover 省略时依次找 <目录>/cover.jpg、<目录>/封面.jpg 等；都没有则跳过 APIC
- 已有同名帧先删除，可重复执行
"""
import argparse, glob, os, re, sys
from mutagen.id3 import ID3, ID3NoHeaderError, USLT, SYLT, APIC, TIT2, TPE1, TALB, TCON

TS = re.compile(r'^\[(\d+):(\d+(?:\.\d+)?)\]')
COVER_NAMES = ('cover.jpg', 'cover.jpeg', 'cover.png', '封面.jpg', '封面.png')


def parse_lrc(text):
    out = []
    for line in text.split('\n'):
        m = TS.match(line)
        if m:
            ms = int(m.group(1)) * 60000 + round(float(m.group(2)) * 1000)
            out.append((line, ms))
    return out


def find_cover(directory, explicit):
    """按优先级找封面：显式指定 > 目录内约定文件名 > 无（不内嵌 APIC）。"""
    if explicit:
        return explicit if os.path.exists(explicit) else None
    for name in COVER_NAMES:
        p = os.path.join(directory, name)
        if os.path.exists(p):
            return p
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('directory')
    ap.add_argument('--cover', default=None)
    ap.add_argument('--album', default=None, help='专辑名，默认用目录名')
    ap.add_argument('--artist', default='eatmoreduck')
    args = ap.parse_args()

    album = args.album or os.path.basename(os.path.abspath(args.directory))

    cover_data = None
    cover_path = find_cover(args.directory, args.cover)
    if cover_path:
        cover_data = open(cover_path, 'rb').read()
        print(f'封面: {cover_path}')

    n = 0
    for mp3 in sorted(glob.glob(os.path.join(args.directory, '*.mp3'))):
        lrc = mp3[:-4] + '.lrc'
        if not os.path.exists(lrc):
            continue
        text = open(lrc).read()
        name = os.path.splitext(os.path.basename(mp3))[0]
        try:
            tags = ID3(mp3)
        except ID3NoHeaderError:
            tags = ID3()
        tags.delall('USLT'); tags.delall('SYLT'); tags.delall('APIC')
        tags.add(USLT(encoding=3, lang='chi', desc='', text=text))
        tags.add(SYLT(encoding=3, lang='chi', format=2, type=1, text=parse_lrc(text)))
        if cover_data:
            tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=cover_data))
        tags.add(TIT2(encoding=3, text=name))
        tags.add(TPE1(encoding=3, text=args.artist))
        tags.add(TALB(encoding=3, text=album))
        tags.add(TCON(encoding=3, text='Speech'))
        tags.update_to_v24()
        tags.save(mp3, v2_version=3)
        n += 1
        print(f'OK {name}')
    print(f'共 {n} 段（歌词+封面+标签）')


if __name__ == '__main__':
    main()
