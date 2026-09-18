#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""产品可读性像素门槛：实际生成结果 vs 参考图在不同目标像素宽下的表现。

统一显示尺寸（模拟"在屏幕上放大看产品"），唯一变量是「源像素有多少」。
"""
import os
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"

FRAME_W = 768
DISP_W, DISP_H = 268, 376          # 统一显示尺寸（袋面比例 0.713）
PAD, GAP, HEAD = 26, 18, 112
BAG_RATIO = 973 / 694.0

# 实况：生成帧里袋面的物理位置（HSV 红色 mask 实测）
LIVE_BOX = (110, 1048, 336, 1344)   # x0,y0,x1,y1 → 226 x 296（底部被画面裁断）


def fit(img, w, h):
    return cv2.resize(img, (w, h), interpolation=cv2.INTER_LANCZOS4)


def main():
    frame = cv2.imread(os.path.join(HERE, "id_t13.0.jpg"))
    ref = cv2.imread(os.path.join(HERE, "prod_P1_front.png"))

    x0, y0, x1, y1 = LIVE_BOX
    live = fit(frame[y0:y1, x0:x1], DISP_W, DISP_H)

    levels = [
        (226, "参考图缩到 226px", "真像素也只有这么点 —— 笔画出不来", False),
        (450, "参考图缩到 450px", "改构图：产品占画面 59%", True),
        (694, "参考图缩到 694px", "产品特写满幅 · 占画面 90%", True),
    ]

    f_h1 = ImageFont.truetype(FONT, 27)
    f_h2 = ImageFont.truetype(FONT, 17)
    f_lab = ImageFont.truetype(FONT, 17)
    f_sub = ImageFont.truetype(FONT, 14)

    cells = 1 + len(levels)
    total_w = PAD * 2 + cells * DISP_W + (cells - 1) * GAP
    total_h = PAD + HEAD + DISP_H + 92 + PAD
    cv = Image.new("RGB", (total_w, total_h), "#f7f7f8")
    d = ImageDraw.Draw(cv)

    d.text((PAD, PAD), "产品可读性 —— 像素门槛", font=f_h1, fill="#141414")
    d.text((PAD, PAD + 38),
           "统一显示尺寸（模拟在屏幕上放大看产品），唯一变量是「源像素有多少」",
           font=f_h2, fill="#777777")
    d.text((PAD, PAD + 62),
           "你给的原图是 694px 真像素 —— 但产品在生成帧里只占 ~226px，这才是糊的根因",
           font=f_h2, fill="#1e6fbf")

    y = PAD + HEAD

    x = PAD
    cv.paste(Image.fromarray(cv2.cvtColor(live, cv2.COLOR_BGR2RGB)), (x, y))
    d.rectangle([x, y, x + DISP_W, y + DISP_H], outline="#c0392b", width=4)
    d.text((x, y + DISP_H + 8), "实际生成结果", font=f_lab, fill="#c0392b")
    d.text((x, y + DISP_H + 30), "袋面在帧里仅 ~226px 宽（底部被裁）", font=f_sub, fill="#666666")
    d.text((x, y + DISP_H + 48), "latent 里 ~28 格宽 → 字画不出来", font=f_sub, fill="#666666")
    d.text((x, y + DISP_H + 66), "（当前 S2 输出 768x1344）", font=f_sub, fill="#999999")

    for i, (tw, label, sub, ok) in enumerate(levels):
        x = PAD + (i + 1) * (DISP_W + GAP)
        small = cv2.resize(ref, (tw, int(ref.shape[0] * tw / ref.shape[1])),
                           interpolation=cv2.INTER_LANCZOS4)
        shown = fit(small, DISP_W, DISP_H)
        cv.paste(Image.fromarray(cv2.cvtColor(shown, cv2.COLOR_BGR2RGB)), (x, y))
        d.rectangle([x, y, x + DISP_W, y + DISP_H],
                    outline="#1e8449" if ok else "#c0392b", width=4 if ok else 3)
        d.text((x, y + DISP_H + 8), label, font=f_lab,
               fill="#1e8449" if ok else "#c0392b")
        d.text((x, y + DISP_H + 30), "占画面宽 %.0f%%" % (100.0 * tw / FRAME_W),
               font=f_sub, fill="#666666")
        barw = tw * (0.345 - 0.145)
        d.text((x, y + DISP_H + 48),
               "竖排字每字 %.0fpx → latent 宽 %.1f 格" % (barw, barw / 8),
               font=f_sub, fill="#666666")
        d.text((x, y + DISP_H + 66), sub, font=f_sub,
               fill="#1e8449" if ok else "#999999")

    out = os.path.join(HERE, "compare_pixel_gate.png")
    cv.save(out, quality=96)
    print("写出", out, cv.size)
    print("实况裁切:", LIVE_BOX, "→", live.shape)


main()
