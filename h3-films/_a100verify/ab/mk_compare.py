#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""拼「同一镜 · 三种精修强度」对照图，用于判定主体保真度。"""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"

W, H = 300, 525
PAD, GAP = 18, 12
TITLE_H, HEAD_H, ROW_H = 64, 46, 34

COLS = [
    ("S1 草稿 384x672", "base", None, "基准（S1 Ref2VA 输出）"),
    ("S2 official 满强度", "off", "#c0392b", "sigma 0.909 起 · 近乎重画"),
    ("S2 identity 低sigma", "id", "#1e8449", "sigma 0.5 起 · 保留原 latent"),
    ("S2 identity + 参考图", "gd", "#1e8449", "低sigma 且注入产品图引导"),
]
ROWS = [
    ("女主角（t=6.0s）", "t6.0"),
    ("产品包装袋面（t=13.0s）", "t13.0"),
]

total_w = PAD * 2 + len(COLS) * W + (len(COLS) - 1) * GAP
total_h = PAD * 2 + TITLE_H + HEAD_H + len(ROWS) * (ROW_H + H + GAP)

canvas = Image.new("RGB", (total_w, total_h), "#f7f7f8")
d = ImageDraw.Draw(canvas)
f_title = ImageFont.truetype(FONT, 30)
f_head = ImageFont.truetype(FONT, 19)
f_row = ImageFont.truetype(FONT, 20)
f_note = ImageFont.truetype(FONT, 15)

d.text((PAD, PAD + 6), "同一镜 shot13 · 三种精修强度对照（A100 实测）",
       font=f_title, fill="#1a1a1a")

y = PAD + TITLE_H
for i, (head, _key, color, note) in enumerate(COLS):
    x = PAD + i * (W + GAP)
    d.text((x + 4, y), head, font=f_head, fill=color or "#333333")
    d.text((x + 4, y + 22), note, font=f_note, fill="#888888")
y += HEAD_H

for rowi, (rowlabel, tag) in enumerate(ROWS):
    d.text((PAD, y + 6), rowlabel, font=f_row, fill="#1a1a1a")
    y += ROW_H
    for ci, (_head, key, color, _note) in enumerate(COLS):
        p = os.path.join(HERE, "%s_%s.jpg" % (key, tag))
        x = PAD + ci * (W + GAP)
        if not os.path.exists(p):
            d.rectangle([x, y, x + W, y + H], fill="#e8e8ea")
            d.text((x + 50, y + H // 2), "缺图", font=f_head, fill="#999999")
            continue
        im = Image.open(p).convert("RGB").resize((W, H), Image.LANCZOS)
        canvas.paste(im, (x, y))
        d.rectangle([x, y, x + W, y + H],
                    outline=color or "#cccccc", width=4 if color else 2)
    y += H + GAP

out = os.path.join(HERE, "compare_3way_shot13.png")
canvas.save(out, quality=95)
print("写出", out, canvas.size)
