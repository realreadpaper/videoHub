#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_ab_sheet.py —— 生成 A/B 视觉对比图（左=旧解码器，右=新解码器）

排布：
  第一行：两版全帧（原尺寸）
  第二行：中心区域 2 倍放大（用来看细节差异）
  底部  ：PSNR / 文件大小等参数条

用法：
  python3 make_ab_sheet.py LEFT.mp4 RIGHT.mp4 OUT.png [--frame 180] \
      [--label-left "TAEHV (old)"] [--label-right "Full VAE (A1)"] [--zoom 2]
"""
import os, subprocess, sys, tempfile

from PIL import Image, ImageDraw, ImageFont

FFMPEG = "ffmpeg"
BG = (250, 250, 250)
FG = (28, 28, 30)
ACCENT_L = (200, 70, 70)
ACCENT_R = (30, 130, 80)


def grab(video, n, out_png):
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", video,
                    "-vf", "select=eq(n\\,%d)" % n, "-frames:v", "1", out_png],
                   capture_output=True)
    return os.path.exists(out_png) and os.path.getsize(out_png) > 0


def font(size, bold=False):
    cands = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
    ]
    for c in cands:
        if os.path.exists(c):
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                pass
    return ImageFont.load_default()


def main():
    if len(sys.argv) < 4:
        print(__doc__); sys.exit(2)
    left, right, out = sys.argv[1], sys.argv[2], sys.argv[3]
    n = int(sys.argv[sys.argv.index("--frame") + 1]) if "--frame" in sys.argv else 180
    lab_l = sys.argv[sys.argv.index("--label-left") + 1] if "--label-left" in sys.argv else "TAEHV decode (old)"
    lab_r = sys.argv[sys.argv.index("--label-right") + 1] if "--label-right" in sys.argv else "Full VAE decode (A1)"
    zoom = int(sys.argv[sys.argv.index("--zoom") + 1]) if "--zoom" in sys.argv else 2

    tmp = tempfile.mkdtemp(prefix="absheet_")
    fl, fr = os.path.join(tmp, "l.png"), os.path.join(tmp, "r.png")
    ok1, ok2 = grab(left, n, fl), grab(right, n, fr)
    if not (ok1 and ok2):
        print("抽帧失败: left=%s right=%s" % (ok1, ok2)); sys.exit(1)

    il, ir = Image.open(fl).convert("RGB"), Image.open(fr).convert("RGB")
    W, H = il.size

    # 中心裁剪区域；--crop x,y,w,h 可指定任意区域
    if "--crop" in sys.argv:
        cx, cy, cw, ch = [int(v) for v in sys.argv[sys.argv.index("--crop") + 1].split(",")]
        cx = max(0, min(cx, W - cw)); cy = max(0, min(cy, H - ch))
    else:
        cw, ch = W // 4, H // 4
        cx, cy = W // 2 - cw // 2, H // 2 - ch // 2
    box = (cx, cy, cx + cw, cy + ch)
    zl = il.crop(box).resize((cw * zoom, ch * zoom), Image.LANCZOS)
    zr = ir.crop(box).resize((cw * zoom, ch * zoom), Image.LANCZOS)

    pad, gap, bar = 24, 20, 46
    row_w = W * 2 + gap
    zoom_w = cw * zoom * 2 + gap
    canvas_w = max(row_w, zoom_w) + pad * 2

    title_h = 62
    zoom_row_h = ch * zoom
    canvas_h = title_h + bar + H + gap + bar + zoom_row_h + bar + pad

    im = Image.new("RGB", (canvas_w, canvas_h), BG)
    d = ImageDraw.Draw(im)
    f_title = font(30, True)
    f_lab = font(24, True)
    f_small = font(19)

    d.text((pad, 16), "A/B frame comparison  ·  frame %d  ·  %dx%d" % (n, W, H),
           font=f_title, fill=FG)

    y = title_h + 8
    # ---- 第一行：全帧 ----
    x0 = pad
    d.rectangle([x0, y, x0 + W, y + bar - 6], fill=(242, 242, 245))
    d.text((x0 + 10, y + 8), lab_l, font=f_lab, fill=ACCENT_L)
    x1 = x0 + W + gap
    d.rectangle([x1, y, x1 + W, y + bar - 6], fill=(242, 242, 245))
    d.text((x1 + 10, y + 8), lab_r, font=f_lab, fill=ACCENT_R)
    y += bar
    im.paste(il, (x0, y)); im.paste(ir, (x1, y))
    d.rectangle([x0, y, x0 + W - 1, y + H - 1], outline=ACCENT_L, width=2)
    d.rectangle([x1, y, x1 + W - 1, y + H - 1], outline=ACCENT_R, width=2)

    y += H + gap
    zw = cw * zoom
    d.text((pad, y), "Centre crop, %dx zoom (%dx%d source region)" % (zoom, cw, ch),
           font=f_small, fill=(110, 110, 118))
    y += bar
    im.paste(zl, (pad, y)); im.paste(zr, (pad + zw + gap, y))
    d.rectangle([pad, y, pad + zw - 1, y + zoom_row_h - 1], outline=ACCENT_L, width=2)
    d.rectangle([pad + zw + gap, y, pad + zw + gap + zw - 1, y + zoom_row_h - 1],
                outline=ACCENT_R, width=2)

    im.save(out)
    print("✔ 已输出 %s  (%dx%d)" % (out, canvas_w, canvas_h))


if __name__ == "__main__":
    main()
