#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""拼「参考图库」：产品原图 + 两位主角定妆照候选。"""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"

ITEMS = [
    ("prod_P1_front.png", "产品 SP（你提供）", "prod_P1_front.png · 694x973", "#c0392b"),
    ("cand_girl.jpg", "女主角 S2（自动提取）", "取自 identity 精修版 shot13 · 768x1344", "#1e8449"),
    ("cand_old.jpg", "老爷爷 S1（自动提取）", "取自 identity 精修版 shot13 · 侧脸笑", "#b7791f"),
]

TH = 430
PAD, GAP, HEAD = 22, 18, 78

imgs = []
for fn, title, note, color in ITEMS:
    p = os.path.join(HERE, fn)
    if not os.path.exists(p):
        imgs.append(None)
        continue
    im = Image.open(p).convert("RGB")
    w = int(im.width * TH / im.height)
    imgs.append((im.resize((w, TH), Image.LANCZOS), title, note, color))

total_w = PAD * 2 + sum(i[0].width for i in imgs if i) + GAP * (len(imgs) - 1)
total_h = PAD * 2 + HEAD + TH + 34

cv = Image.new("RGB", (total_w, total_h), "#f7f7f8")
d = ImageDraw.Draw(cv)
f_t = ImageFont.truetype(FONT, 26)
f_s = ImageFont.truetype(FONT, 16)

d.text((PAD, PAD + 2), "角色 / 主体参考图库（用于跨镜一致性锚定）",
       font=f_t, fill="#1a1a1a")

x = PAD
y = PAD + HEAD
for item in imgs:
    if not item:
        continue
    im, title, note, color = item
    cv.paste(im, (x, y))
    d.rectangle([x, y, x + im.width, y + TH], outline=color, width=4)
    d.text((x + 2, y + TH + 6), title, font=f_s, fill=color)
    x += im.width + GAP

out = os.path.join(HERE, "ref_library.png")
cv.save(out, quality=95)
print("写出", out, cv.size)
