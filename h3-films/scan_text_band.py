#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""字幕带扫描器 —— 把「有没有乱码字幕」变成一张可以 30 秒扫完的接触表。

为什么需要这个（以及为什么不用纯 OCR）
--------------------------------------
H3 复刻源片时会**照抄烧死的字幕**，画出「汉字 + 数字」的乱码条，位置固定在画面下方
约 72–80%。实测 tesseract 对这类**伪汉字**几乎没有识别能力（真字幕帧常常 OCR 出 0 个
汉字），且对轮椅辐条 / 肉块纹理 / 金属划痕产生大量误报 —— 6 项 OCR 几何特征（token 数、
字符数、跨度、字高离散、间距离散、置信度）在正负样本上**完全重叠**，无法分离。
所以：**判字靠人眼，机器只负责把候选帧裁好、拼齐、摆到一张图上。**

用法
----
  python3 scan_text_band.py --video _deliver/xx_全片.mp4 --every 5
  python3 scan_text_band.py --shots _deliver/shots_film1 --per-shot 3
  python3 scan_text_band.py --video xx.mp4 --every 4 --band 0.66,0.90 --col 6

产物：<out>.jpg 接触表 —— 每格一个字幕带，格下标时间码。**有字的一格肉眼立刻能认出。**
"""
import argparse
import os
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont

FONT = "/System/Library/Fonts/Supplemental/Songti.ttc"


def probe_dur(video):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", video], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def grab(video, t):
    p = tempfile.mktemp(suffix=".jpg")
    subprocess.run(["ffmpeg", "-v", "error", "-ss", "%.3f" % t, "-i", video,
                    "-frames:v", "1", "-q:v", "2", p, "-y"], capture_output=True)
    return p if os.path.exists(p) and os.path.getsize(p) > 0 else None


def band_of(path, band):
    im = Image.open(path)
    w, h = im.size
    return im.crop((0, int(h * band[0]), w, int(h * band[1]))), (w, h)


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--video")
    g.add_argument("--shots")
    ap.add_argument("--every", type=float, default=5.0, help="整片：每 N 秒一帧")
    ap.add_argument("--per-shot", type=int, default=3, help="分镜：每镜抽几帧")
    ap.add_argument("--band", default="0.66,0.90", help="字幕带（画面高度比例）a,b")
    ap.add_argument("--col", type=int, default=5)
    ap.add_argument("--tile-w", type=int, default=272)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    band = tuple(float(x) for x in a.band.split(","))

    jobs = []           # (label, video, t)
    if a.video:
        dur = probe_dur(a.video)
        t = a.every / 2
        while t < dur:
            jobs.append(("%.0fs" % t, a.video, t))
            t += a.every
        out = a.out or (os.path.splitext(a.video)[0] + "_字幕带扫描.jpg")
    else:
        files = sorted(f for f in os.listdir(a.shots) if f.endswith(".mp4"))
        for fn in files:
            v = os.path.join(a.shots, fn)
            d = probe_dur(v) or 15.0
            for k in range(a.per_shot):
                t = d * (k + 1) / (a.per_shot + 1)
                jobs.append(("%s@%.1f" % (fn.replace(".mp4", ""), t), v, t))
        out = a.out or (a.shots.rstrip("/") + "_字幕带扫描.jpg")

    tiles = []
    for label, v, t in jobs:
        p = grab(v, t)
        if not p:
            continue
        crop, (W, H) = band_of(p, band)
        os.unlink(p)
        tiles.append((label, crop))

    if not tiles:
        print("没抽到帧"); return

    tw = a.tile_w
    th = int(tiles[0][1].size[1] * tw / tiles[0][1].size[0])
    cols = a.col
    rows = (len(tiles) + cols - 1) // cols
    cap = 20
    canvas = Image.new("RGB", (cols * (tw + 8) + 8, rows * (th + cap + 8) + 8), (247, 246, 243))
    d = ImageDraw.Draw(canvas)
    try:
        f = ImageFont.truetype(FONT, 14)
    except Exception:
        f = ImageFont.load_default()
    for i, (label, crop) in enumerate(tiles):
        x = 8 + (i % cols) * (tw + 8)
        y = 8 + (i // cols) * (th + cap + 8)
        canvas.paste(crop.resize((tw, th), Image.LANCZOS), (x, y))
        d.text((x + 2, y + th + 3), label, font=f, fill=(70, 70, 68))

    canvas.save(out, quality=90)
    print("✔ %s" % out)
    print("  格数 %d ｜ 字幕带 y %.0f%%–%.0f%% ｜ %d 列" % (
        len(tiles), band[0] * 100, band[1] * 100, cols))
    print("  ★ 逐格目视：出现的「成行汉字/数字乱码」即为违规，记下格子标签=时间码/镜号")


if __name__ == "__main__":
    main()
