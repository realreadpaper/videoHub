#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""产品清晰度四联对照：构图与分辨率各自贡献多少。"""
import os
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
DISP_H = 400
PAD, GAP, HEAD = 26, 16, 128
BAG_AR = 694 / 973.0

# (标签, 文件, 分辨率说明, 耗时, 备注, 颜色, 还原度, 固定bbox或None)
CASES = [
    ("原方案", "../ab/id_t13.0.jpg", "384x672 → 768x1344", "271 s",
     "产品仅占画面 29%", "#c0392b", "~0%", (110, 1048, 226, 296)),
    ("只改构图", "A_t7.0.jpg", "384x672（分辨率不变）", "360 s",
     "产品占画面 ~80%", "#d68910", "~70%", None),
    ("构图 + 提分辨率", "B_t7.0.jpg", "768x1344（4x 像素）", "631 s",
     "产品占画面 ~80%", "#1e8449", "~100%", None),
    ("特写草稿再走 S2", "S2_t7.0.jpg", "384x672 → 768x1344", "360+280 s",
     "S1 草稿 + S2 精修放大", "#1e8449", "~95%", None),
]


def bag_box(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    m = (((h < 12) | (h > 168)) & (s > 70) & (v > 45)).astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE,
                         cv2.getStructuringElement(cv2.MORPH_RECT, (25, 25)), iterations=3)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
    j = 1 + int(np.argmax(st[1:, 4]))
    return [int(t) for t in st[j][:4]]


def build_crop(img, fixed=None):
    x, y, w, h = fixed if fixed else bag_box(img)
    pad = int(min(w, h) * 0.03)
    x0, y0 = max(0, x - pad), max(0, y - pad)
    x1, y1 = min(img.shape[1], x + w + pad), min(img.shape[0], y + h + pad)
    c = img[y0:y1, x0:x1]
    if c.shape[1] / c.shape[0] < BAG_AR:      # 底部被画面裁断 → 上补
        need = int(c.shape[1] / BAG_AR) - c.shape[0]
        if need > 0:
            c = cv2.copyMakeBorder(c, need, 0, 0, 0, cv2.BORDER_REPLICATE)
    disp_w = int(DISP_H * c.shape[1] / c.shape[0])
    return cv2.resize(c, (disp_w, DISP_H), interpolation=cv2.INTER_LANCZOS4), (x, y, w, h)


def main():
    f_h1 = ImageFont.truetype(FONT, 28)
    f_h2 = ImageFont.truetype(FONT, 17)
    f_lab = ImageFont.truetype(FONT, 18)
    f_sub = ImageFont.truetype(FONT, 14)

    tiles = []
    for label, fn, res, cost, note, color, score, fixed in CASES:
        img = cv2.imread(os.path.join(HERE, fn))
        assert img is not None, fn
        crop, bbox = build_crop(img, fixed)
        tiles.append((crop, label, res, cost, note, color, score))
        print("%-16s bbox=%s  显示=%s" % (label, bbox, crop.shape[:2][::-1]))

    tw = max(t[0].shape[1] for t in tiles)
    total_w = PAD * 2 + len(tiles) * tw + (len(tiles) - 1) * GAP
    total_h = PAD + HEAD + DISP_H + 108 + PAD
    cv = Image.new("RGB", (total_w, total_h), "#f7f7f8")
    d = ImageDraw.Draw(cv)

    d.text((PAD, PAD), "产品清晰度四联对照 —— 构图 vs 分辨率，各贡献多少",
           font=f_h1, fill="#141414")
    d.text((PAD, PAD + 40),
           "统一显示尺寸（裁出袋面区域后等比放大）· 同一份参考图 · 同一镜位设定",
           font=f_h2, fill="#777777")
    d.text((PAD, PAD + 64),
           "结论：把产品拍成特写，比堆分辨率更划算；两者叠加则几乎复刻参考图",
           font=f_h2, fill="#1e6fbf")
    d.text((PAD, PAD + 92),
           "四组在 A100/40GB 上显存均已顶格（峰值 40.3G / 40.96G）—— 分辨率无上调空间；前三组为单步 S1，第四组为 S1+S2 两步链路",
           font=f_h2, fill="#c0392b")

    y = PAD + HEAD
    x = PAD
    for crop, label, res, cost, note, color, score in tiles:
        w = crop.shape[1]
        cv.paste(Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)), (x, y))
        d.rectangle([x, y, x + w, y + DISP_H], outline=color, width=4)
        d.text((x, y + DISP_H + 8), "%s · %s" % (label, cost), font=f_lab, fill=color)
        d.text((x, y + DISP_H + 32), res, font=f_sub, fill="#555555")
        d.text((x, y + DISP_H + 50), note, font=f_sub, fill="#555555")
        d.text((x, y + DISP_H + 70), "印刷还原度 %s" % score, font=f_sub,
               fill="#1e8449" if score.startswith("~9") or score == "~100%" else "#c0392b")
        x += tw + GAP

    out = os.path.join(HERE, "compare_pixel_ladder.png")
    cv.save(out, quality=96)
    print("写出", out, cv.size)


main()
