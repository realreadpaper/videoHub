#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抽帧总览图生成器（contact sheet）
用法: contact_sheet.py <shots目录或mp4列表...> -o 输出.png [--cols 4] [--at 2.5]
每个 mp4 抽一帧（默认第 2.5 秒），拼成网格，并标注镜号与时长。
"""
import os, subprocess, sys, tempfile, glob
from PIL import Image, ImageDraw, ImageFont

FONTS = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
]

def font(sz):
    for p in FONTS:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, sz)
            except Exception:
                pass
    return ImageFont.load_default()

def grab(mp4, at, w, h):
    tmp = tempfile.mktemp(suffix=".jpg")
    subprocess.run(["ffmpeg", "-v", "error", "-ss", str(at), "-i", mp4,
                    "-frames:v", "1", "-vf", "scale=%d:%d" % (w, h), tmp, "-y"],
                   capture_output=True)
    return tmp if os.path.exists(tmp) else None

def main():
    args = sys.argv[1:]
    out = "contact_sheet.png"
    cols, at = 4, 2.5
    if "-o" in args:
        out = args[args.index("-o") + 1]; args = args[:args.index("-o")] + args[args.index("-o") + 2:]
    if "--cols" in args:
        cols = int(args[args.index("--cols") + 1]); args = args[:args.index("--cols")] + args[args.index("--cols") + 2:]
    if "--at" in args:
        at = float(args[args.index("--at") + 1]); args = args[:args.index("--at")] + args[args.index("--at") + 2:]

    files = []
    for a in args:
        if os.path.isdir(a):
            files += sorted(glob.glob(os.path.join(a, "shot*.mp4")))
        else:
            files.append(a)
    files = [f for f in files if os.path.exists(f)]
    if not files:
        print("没有找到输入 mp4"); return

    W, H, PAD, LBL = 480, 274, 10, 30
    rows = (len(files) + cols - 1) // cols
    cw, ch = W + PAD * 2, H + PAD * 2 + LBL
    canvas = Image.new("RGB", (cols * cw, rows * ch), (244, 242, 238))
    d = ImageDraw.Draw(canvas)
    f_lbl = font(21)

    for i, mp4 in enumerate(files):
        r, c = divmod(i, cols)
        x0, y0 = c * cw, r * ch
        jp = grab(mp4, at, W, H)
        if not jp:
            continue
        im = Image.open(jp).convert("RGB")
        canvas.paste(im, (x0 + PAD, y0 + PAD + LBL))
        name = os.path.basename(mp4).replace(".mp4", "")
        d.text((x0 + PAD + 2, y0 + 6), name, font=f_lbl, fill=(40, 36, 32))
        try:
            os.remove(jp)
        except Exception:
            pass

    canvas.save(out, quality=94)
    print("已生成", out, "%.1f MB  (%d 帧, %dx%d)" %
          (os.path.getsize(out) / 1048576, len(files), canvas.width, canvas.height))

if __name__ == "__main__":
    main()
