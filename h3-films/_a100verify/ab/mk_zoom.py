#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""局部放大对照：包装袋面文字 + 女主角面部。"""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"

# (图源前缀, 标题, 边框色)
SRC = [
    ("base", "S1 草稿", None),
    ("off", "S2 official 满强度", "#c0392b"),
    ("id", "S2 identity 低sigma", "#1e8449"),
    ("gd", "S2 identity+参考图", "#1e8449"),
]
# 归一化裁剪框 (左, 上, 右, 下)——相对帧尺寸
CROPS = {
    "pouch": ((0.08, 0.70, 0.56, 1.0), "包装袋面 放大对照"),
    "face": ((0.29, 0.12, 0.73, 0.47), "女主角面部 放大对照"),
}


def load(prefix, tag):
    p = os.path.join(HERE, "%s_%s.jpg" % (prefix, tag))
    return Image.open(p).convert("RGB") if os.path.exists(p) else None


def build(crop_key, tag, outname):
    box, label = CROPS[crop_key]
    f_h = ImageFont.truetype(FONT, 21)
    f_s = ImageFont.truetype(FONT, 16)

    cw = int(768 * (box[2] - box[0])) * 1
    ch = int(1344 * (box[3] - box[1])) * 1
    scale = 1.55
    tw, th = int(cw * scale * 0.42), int(ch * scale * 0.42)

    pad, gap, head = 20, 14, 66
    total_w = pad * 2 + len(SRC) * tw + (len(SRC) - 1) * gap
    total_h = pad * 2 + head + th
    cv = Image.new("RGB", (total_w, total_h), "#f7f7f8")
    d = ImageDraw.Draw(cv)
    d.text((pad, pad + 4), label, font=f_h, fill="#1a1a1a")
    d.text((pad, pad + 36), "同一时间点裁切 · 放大约 1.6x", font=f_s, fill="#888888")

    for i, (key, title, color) in enumerate(SRC):
        im = load(key, tag)
        x = pad + i * (tw + gap)
        y = pad + head
        if im is None:
            d.rectangle([x, y, x + tw, y + th], fill="#e8e8ea")
            continue
        w, h = im.size
        c = im.crop((int(w * box[0]), int(h * box[1]),
                     int(w * box[2]), int(h * box[3])))
        c = c.resize((tw, th), Image.LANCZOS)
        cv.paste(c, (x, y))
        d.rectangle([x, y, x + tw, y + th],
                    outline=color or "#cccccc", width=4 if color else 2)
        d.text((x + 4, y + th + 6), title, font=f_s,
               fill=color or "#333333")
    out = os.path.join(HERE, outname)
    cv.save(out, quality=96)
    print("写出", out, cv.size)


build("pouch", "t13.0", "compare_zoom_pouch_3way.png")
build("face", "t6.0", "compare_zoom_face_3way.png")
