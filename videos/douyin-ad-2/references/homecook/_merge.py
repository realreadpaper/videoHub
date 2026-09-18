#!/usr/bin/env python3
"""把 whisper 的逐字 srt 合并成带时间码的句子列表。

合并规则：字符间隙 > GAP 秒，或累积字数 >= MAXCHARS，则断句。
输出: [mm:ss.s] 该句文本
"""
import re, sys

GAP = 0.45
MAXCHARS = 16


def parse_srt(path):
    txt = open(path, encoding="utf-8").read()
    blocks = re.split(r"\n\s*\n", txt.strip())
    out = []
    for b in blocks:
        lines = [l for l in b.split("\n") if l.strip()]
        if len(lines) < 3:
            continue
        m = re.match(r"(\d+):(\d+):([\d,]+)\s*-->\s*(\d+):(\d+):([\d,]+)", lines[1])
        if not m:
            continue
        start = (int(m.group(1)) * 3600 + int(m.group(2)) * 60
                 + float(m.group(3).replace(",", ".")))
        end = (int(m.group(4)) * 3600 + int(m.group(5)) * 60
               + float(m.group(6).replace(",", ".")))
        text = "".join(lines[2:]).strip()
        if text:
            out.append((start, end, text))
    return out


def fmt(t):
    m, s = divmod(t, 60)
    return f"{int(m):02d}:{s:04.1f}"


def merge(items):
    segs = []
    cur = None
    for st, en, tx in items:
        if cur is None:
            cur = [st, en, tx]
        elif st - cur[1] > GAP or len(cur[2]) + len(tx) > MAXCHARS:
            segs.append(cur)
            cur = [st, en, tx]
        else:
            cur[1] = en
            cur[2] += tx
    if cur:
        segs.append(cur)
    return segs


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "transcript.srt"
    dst = sys.argv[2] if len(sys.argv) > 2 else "transcript_lines.txt"
    segs = merge(parse_srt(src))
    with open(dst, "w", encoding="utf-8") as f:
        for st, en, tx in segs:
            line = f"[{fmt(st)} → {fmt(en)}]  {tx}"
            f.write(line + "\n")
            print(line)
    print(f"\n共 {len(segs)} 句 → {dst}")
