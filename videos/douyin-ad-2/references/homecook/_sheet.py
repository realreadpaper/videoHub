#!/usr/bin/env python3
"""拼接触表：把抽出的帧按网格拼成一张图，带时间码标签。"""
import sys, os, glob
from PIL import Image, ImageDraw, ImageFont

FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"


def fmt(sec):
    m, s = divmod(int(sec), 60)
    return f"{m}:{s:02d}"


def sheet(files, cols, out, step, cell_w=270):
    ims = []
    for f in files:
        im = Image.open(f)
        h = int(im.height * cell_w / im.width)
        idx = int(os.path.basename(f).split("_")[1].split(".")[0])
        lab = fmt((idx - 1) * step)
        ims.append((im.resize((cell_w, h)), lab))
    if not ims:
        print("no frames")
        return
    ch = ims[0][0].height + 26
    rows = (len(ims) + cols - 1) // cols
    c = Image.new("RGB", (cell_w * cols, ch * rows), (20, 20, 20))
    d = ImageDraw.Draw(c)
    font = ImageFont.truetype(FONT, 19)
    for i, (im, lab) in enumerate(ims):
        r, cc = divmod(i, cols)
        x, y = cc * cell_w, r * ch
        c.paste(im, (x, y))
        d.text((x + 6, y + im.height + 2), lab, fill=(255, 220, 60), font=font)
    c.save(out, quality=88)
    print(f"{out}  {len(ims)} frames  {c.width}x{c.height}")


if __name__ == "__main__":
    d = sys.argv[1]
    outdir = sys.argv[2]
    step = int(sys.argv[3])
    cols = int(sys.argv[4])
    per = int(sys.argv[5]) if len(sys.argv) > 5 else 18
    files = sorted(glob.glob(os.path.join(d, "*.jpg")))
    os.makedirs(outdir, exist_ok=True)
    for i in range(0, len(files), per):
        chunk = files[i : i + per]
        tag = f"{fmt((int(os.path.basename(chunk[0]).split('_')[1].split('.')[0])-1)*step)}-{fmt((int(os.path.basename(chunk[-1]).split('_')[1].split('.')[0])-1)*step)}"
        sheet(chunk, cols, os.path.join(outdir, f"sheet_{tag}.jpg"), step)
