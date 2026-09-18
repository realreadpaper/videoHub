#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_burnin.py —— 画面烧字 / 硬字幕巡检

用途：确认成片里有没有模型自己烙进去的文字（乱码字幕、招牌字、纸条字）。
本项目铁律是「成片一律不烧字幕，字幕走外挂 srt/vtt」，所以每次出片都要过这一关。

两种视图：
  1) 底带条  —— 只取画面底部 N%，按时间顺序纵向拼接，专盯字幕位
  2) 全帧网格 —— 全画面缩略图，专盯招牌/纸条/字幕外的文字

用法：
  python3 check_burnin.py 片子.mp4 --out 巡检图.png
  python3 check_burnin.py 片子.mp4 --out 巡检图.png --band 0.22 --cols 3
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile

from PIL import Image

FFMPEG = "ffmpeg"


def grab(src: str, n: int, dst: str) -> bool:
    r = subprocess.run(
        [FFMPEG, "-v", "error", "-y", "-i", src,
         "-vf", "select=eq(n\\,%d)" % n, "-frames:v", "1", dst],
        capture_output=True)
    return os.path.exists(dst) and os.path.getsize(dst) > 0


def frame_count(src: str) -> int:
    out = subprocess.run(
        [FFMPEG, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=nb_frames", "-of", "csv=p=0", src],
        capture_output=True, text=True).stdout.strip()
    try:
        return int(out)
    except ValueError:
        return 362


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--out", default=None)
    ap.add_argument("--band", type=float, default=0.22,
                    help="底带高度占比，默认 0.22")
    ap.add_argument("--samples", type=int, default=12, help="抽帧数")
    ap.add_argument("--cols", type=int, default=3, help="全帧网格列数")
    ap.add_argument("--thumb", type=int, default=448, help="全帧网格单格宽")
    a = ap.parse_args()

    out = a.out or (os.path.splitext(a.video)[0] + "_烧字巡检.png")
    total = frame_count(a.video)
    idx = [int(i * (total - 1) / max(1, a.samples - 1)) for i in range(a.samples)]

    tmp = tempfile.mkdtemp(prefix="burnin_")
    bands, fulls = [], []
    for n in idx:
        p = os.path.join(tmp, "f%05d.png" % n)
        if not grab(a.video, n, p):
            continue
        im = Image.open(p).convert("RGB")
        W, H = im.size
        bands.append((n, im.crop((0, int(H * (1 - a.band)), W, H))))
        tw = a.thumb
        th = int(H * tw / W)
        fulls.append((n, im.resize((tw, th), Image.LANCZOS)))

    if not bands:
        print("✘ 抽帧失败，检查视频路径")
        return 1

    bw, bh = bands[0][1].size
    bsheet = Image.new("RGB", (bw, bh * len(bands)), (10, 10, 10))
    for i, (_, b) in enumerate(bands):
        bsheet.paste(b, (0, i * bh))

    cols = max(1, a.cols)
    rows = (len(fulls) + cols - 1) // cols
    fw, fh = fulls[0][1].size
    fsheet = Image.new("RGB", (fw * cols, fh * rows), (10, 10, 10))
    for i, (_, f) in enumerate(fulls):
        fsheet.paste(f, ((i % cols) * fw, (i // cols) * fh))

    gap = 14
    canvas = Image.new("RGB", (max(bsheet.width, fsheet.width),
                               bsheet.height + fsheet.height + gap), (255, 255, 255))
    canvas.paste(fsheet, (0, 0))
    canvas.paste(bsheet, (0, fsheet.height + gap))
    canvas.save(out)
    print("帧号: %s" % idx)
    print("全帧网格 %dx%d + 底带条(底部 %d%%)" % (cols, rows, int(a.band * 100)))
    print("✔ 已写出: %s  %s" % (out, canvas.size))
    return 0


if __name__ == "__main__":
    sys.exit(main())
