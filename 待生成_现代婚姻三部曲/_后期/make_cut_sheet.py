#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把镜内硬切点前后的连续帧排出来，直观展示「跳变」。
用法: python3 make_cut_sheet.py 视频.mp4 --cuts 211,291 [--out 输出.png]
"""
import argparse, os, subprocess, tempfile
import numpy as np
from PIL import Image, ImageDraw

FFMPEG = "ffmpeg"


def grab(src, n, tmp):
    p = os.path.join(tmp, "g_%04d.png" % n)
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", src,
                    "-vf", "select=eq(n\\,%d)" % n, "-frames:v", "1", p],
                   capture_output=True)
    return Image.open(p).convert("RGB") if os.path.exists(p) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--cuts", default="211,291")
    ap.add_argument("--span", type=int, default=6, help="切点前后各取几帧")
    ap.add_argument("--step", type=int, default=3, help="每几帧取一帧")
    ap.add_argument("--thumb", type=int, default=300)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    cuts = [int(x) for x in a.cuts.split(",")]
    tmp = tempfile.mkdtemp()
    th = a.thumb
    thh = int(th * 9 / 16)

    rows = []
    for c in cuts:
        ns = list(range(max(0, c - a.span), c + a.span + 1, a.step))
        imgs = []
        for n in ns:
            im = grab(a.video, n, tmp)
            if im is None:
                continue
            t = im.resize((th, thh), Image.LANCZOS)
            imgs.append((n, t))
        rows.append((c, imgs))

    cols = max(len(r[1]) for r in rows)
    pad, head = 6, 30
    W = cols * (th + pad) + pad
    H = head + len(rows) * (thh + pad + head) + pad
    sheet = Image.new("RGB", (W, H), (250, 250, 252))
    dr = ImageDraw.Draw(sheet)

    y = head // 2
    dr.text((pad, y - 10), "%s  —  镜内硬切点前后连续帧（逐帧）"
            % os.path.basename(a.video), fill=(30, 30, 30))
    y = head
    for c, imgs in rows:
        dr.text((pad, y - 18), "★ 切点：帧 %d（%.2f 秒）" % (c, c / 24.0), fill=(200, 30, 30))
        x = pad
        for n, im in imgs:
            sheet.paste(im, (x, y))
            mark = "★" if n == c else str(n)
            col = (220, 20, 20) if n == c else (90, 90, 90)
            dr.text((x + 4, y + thh - 16), mark, fill=col)
            if n == c - 1:
                dr.rectangle([x - 2, y - 2, x + th + 1, y + thh + 1], outline=(220, 20, 20), width=2)
            x += th + pad
        y += thh + pad + head

    out = a.out or (os.path.splitext(os.path.basename(a.video))[0] + "_cuts.png")
    sheet.save(out)
    print("✔ 已输出 %s  (%dx%d)" % (out, sheet.size[0], sheet.size[1]))


if __name__ == "__main__":
    main()
