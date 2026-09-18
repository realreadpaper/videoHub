#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S1 草稿 vs S2 精修 —— 同帧同视野对比，证明"精修"这一层做了什么。

同一时间点、同一归一化裁切框，把草稿（384x672）与精修（768x1344）输出
缩放到相同显示尺寸并排，视觉差距即"精修"带来的细节密度。
"""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"

ROWS = [
    # (时刻标签, 裁切键, 草稿文件, 精修文件, 局部标题)
    ("t = 6.0 s", "face", "base_t6.0.jpg", "id_t6.0.jpg", "女主角面部"),
    ("t = 13.0 s", "pouch", "base_t13.0.jpg", "id_t13.0.jpg", "产品袋面文字"),
]
CROPS = {
    "pouch": (0.08, 0.70, 0.56, 1.00),
    "face": (0.29, 0.12, 0.73, 0.47),
}
ROW_H = 380
PAD, GAP = 26, 22
HEAD = 96
LABEL_H = 34
ROW_GAP = 40
BG = "#f7f7f8"


def load(name):
    p = os.path.join(HERE, name)
    return Image.open(p).convert("RGB") if os.path.exists(p) else None


def crop_scaled(im, box, target_h):
    w, h = im.size
    c = im.crop((int(w * box[0]), int(h * box[1]),
                 int(w * box[2]), int(h * box[3])))
    tw = int(c.width * target_h / c.height)
    return c.resize((tw, target_h), Image.LANCZOS), tw


def main():
    f_h1 = ImageFont.truetype(FONT, 27)
    f_h2 = ImageFont.truetype(FONT, 17)
    f_row = ImageFont.truetype(FONT, 19)
    f_lab = ImageFont.truetype(FONT, 15)
    f_big = ImageFont.truetype(FONT, 16)

    # 预算每格宽度（草稿/精修 各取同高，宽度几乎一致，取最大）
    widths = []
    for _, key, dn, rn, _ in ROWS:
        box = CROPS[key]
        d = load(dn)
        r = load(rn)
        _, dw = crop_scaled(d, box, ROW_H)
        _, rw = crop_scaled(r, box, ROW_H)
        widths.append(max(dw, rw))

    cell_w = max(widths)
    total_w = PAD * 2 + cell_w * 2 + GAP
    total_h = PAD + HEAD + len(ROWS) * (LABEL_H + ROW_H + ROW_GAP) - ROW_GAP + PAD

    cv = Image.new("RGB", (total_w, total_h), BG)
    d = ImageDraw.Draw(cv)

    d.text((PAD, PAD), "S1 草稿  vs  S2 精修 —— shot13 同帧对比", font=f_h1, fill="#141414")
    d.text((PAD, PAD + 40),
           "同一时间点 · 同一归一化裁切框 · 缩放到相同显示尺寸",
           font=f_h2, fill="#777777")
    d.text((PAD, PAD + 64),
           "草稿 384x672    →    精修 768x1344（像素密度 2x，面积 4x）",
           font=f_h2, fill="#1e6fbf")

    y = PAD + HEAD
    for (tlabel, key, dn, rn, sub) in ROWS:
        box = CROPS[key]
        d.text((PAD, y + 4), "%s   %s" % (tlabel, sub), font=f_row, fill="#222222")
        y += LABEL_H

        d_im, d_w = crop_scaled(load(dn), box, ROW_H)
        r_im, r_w = crop_scaled(load(rn), box, ROW_H)

        # 草稿
        x = PAD
        cv.paste(d_im, (x, y))
        d.rectangle([x, y, x + d_w, y + ROW_H], outline="#b8b8bd", width=3)
        d.text((x + 4, y + ROW_H + 6), "草稿 384x672 · 放大后可见软化",
               font=f_lab, fill="#8a8a8a")

        # 精修
        x = PAD + cell_w + GAP
        cv.paste(r_im, (x, y))
        d.rectangle([x, y, x + r_w, y + ROW_H], outline="#1e8449", width=4)
        d.text((x + 4, y + ROW_H + 6), "精修 768x1344 · 印刷与毛发边缘成型",
               font=f_lab, fill="#1e8449")

        y += ROW_H + ROW_GAP

    out = os.path.join(HERE, "compare_draft_vs_refined.png")
    cv.save(out, quality=96)
    print("写出", out, cv.size)


main()
