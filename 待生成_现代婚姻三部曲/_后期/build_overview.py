#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从最终成片按每镜中点抽帧，拼 12 格总览（标注镜号 / 景别 / 时长）"""
import json, os, subprocess, tempfile
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
M = json.load(open(os.path.join(ROOT, "manifest.json"), encoding="utf-8"))
SRC = os.path.join(ROOT, "不可剥夺_全片_硬字幕版.mp4")
OUT = os.path.join(ROOT, "抽帧总览.png")
SPS = float(M["length_frames"]) / float(M["fps"])     # 每镜秒数

FONTS = ["/System/Library/Fonts/PingFang.ttc",
         "/System/Library/Fonts/Hiragino Sans GB.ttc",
         "/System/Library/Fonts/STHeiti Medium.ttc",
         "/Library/Fonts/Arial Unicode.ttf"]


def font(sz):
    for p in FONTS:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, sz)
            except Exception:
                pass
    return ImageFont.load_default()


def grab(at, w, h):
    tmp = tempfile.mktemp(suffix=".jpg")
    subprocess.run(["ffmpeg", "-v", "error", "-ss", "%.3f" % at, "-i", SRC,
                    "-frames:v", "1", "-vf", "scale=%d:%d" % (w, h), tmp, "-y"],
                   capture_output=True)
    return tmp if os.path.exists(tmp) else None


def main():
    shots = M["shots"]
    cols, W, H, PAD, LBL = 4, 470, 269, 9, 34
    rows = (len(shots) + cols - 1) // cols
    cw, ch = W + PAD * 2, H + PAD * 2 + LBL
    canvas = Image.new("RGB", (cols * cw, rows * ch), (244, 242, 238))
    d = ImageDraw.Draw(canvas)
    f1, f2 = font(20), font(15)

    for i, sh in enumerate(shots):
        r, c = divmod(i, cols)
        x0, y0 = c * cw, r * ch
        at = (sh["no"] - 0.5) * SPS
        jp = grab(at, W, H)
        if not jp:
            continue
        canvas.paste(Image.open(jp).convert("RGB"), (x0 + PAD, y0 + PAD + LBL))
        d.text((x0 + PAD + 2, y0 + 4), "镜 %02d" % sh["no"], font=f1, fill=(168, 50, 42))
        d.text((x0 + PAD + 74, y0 + 8), sh.get("framing", ""), font=f2, fill=(90, 84, 74))
        try:
            os.remove(jp)
        except Exception:
            pass

    d.text((PAD + 2, canvas.height - 24),
           "《不可剥夺》12 镜总览 · 1344×768 · 24fps · 60.5s · 每镜 %.2fs" % SPS,
           font=f2, fill=(120, 114, 104))
    canvas.save(OUT)
    print("已生成 %s  %dx%d  %.2f MB" %
          (os.path.basename(OUT), canvas.width, canvas.height,
           os.path.getsize(OUT) / 1048576))


if __name__ == "__main__":
    main()
