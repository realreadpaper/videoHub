#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""补漏：清掉参考帧里残留的左上角时间戳 / 角标。

第一轮分区检测用的是较高的行密度阈值（给大字幕调的），小字号时间戳常被漏掉。
这里对左上角单独用低阈值复检 + inpaint，然后重出 768x1344 的 ref/first 两套图。
"""
import os, json, sys, argparse
import numpy as np, cv2
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prep_refs_v2 import to_canvas, FILMS  # noqa
from prep_refs_v3 import K5, stroke_mask  # noqa

HERE = os.path.dirname(os.path.abspath(__file__))
_ap = argparse.ArgumentParser()
_ap.add_argument("--shard", type=int, default=0)
_ap.add_argument("--nshards", type=int, default=1)
ARGS = _ap.parse_args()

SRC = f"{HERE}/scrub_src_v3"
OUT_REF = f"{HERE}/full_ref2_v3"
OUT_FIRST = f"{HERE}/full_first_v3"

# 窄条形角标区（时间戳/平台标）：低阈值
STRIPS = [(0.00, 0.34, 0.000, 0.080),   # 左上
          (0.62, 1.00, 0.000, 0.075),   # 右上
          (0.00, 0.30, 0.920, 1.000),   # 左下
          (0.60, 1.00, 0.920, 1.000)]   # 右下


def find_strips(lum, sat, H, W):
    dark = (lum < 105).astype(np.uint8)
    bright = ((lum > 150) | ((sat > 62) & (lum > 108))).astype(np.uint8)
    m = ((bright & cv2.dilate(dark, K5, 2)) | (dark & cv2.dilate(bright, K5, 2))).astype(np.uint8)
    keep = np.zeros_like(m)
    hit = []
    for x0, x1, y0, y1 in STRIPS:
        a, b = int(x0 * W), int(x1 * W)
        c, d = int(y0 * H), int(y1 * H)
        sub = m[c:d, a:b]
        if sub.size == 0:
            continue
        rows = sub.mean(1) / 255.0
        hot = rows > 0.010           # 低阈值：小字也抓
        idx = np.where(hot)[0]
        if len(idx) >= 2:
            keep[c + idx.min():c + idx.max() + 1, a:b] = m[c + idx.min():c + idx.max() + 1, a:b]
            hit.append((x0, x1, y0, y1))
    return cv2.bitwise_and(m, keep), hit


def main():
    os.makedirs(OUT_REF, exist_ok=True); os.makedirs(OUT_FIRST, exist_ok=True)
    files = sorted(f for f in os.listdir(SRC) if f.endswith(".jpg"))
    n_fix = 0; n = 0
    for i, f in enumerate(files):
        if i % ARGS.nshards != ARGS.shard:
            continue
        nm = f[:-4]
        img = Image.open(f"{SRC}/{f}").convert("RGB")
        a = np.asarray(img)
        H, W = a.shape[:2]
        af = a.astype(np.float32)
        lum = 0.299 * af[:, :, 0] + 0.587 * af[:, :, 1] + 0.114 * af[:, :, 2]
        sat = af.max(2) - af.min(2)
        m, hit = find_strips(lum, sat, H, W)
        if hit:
            m = cv2.dilate(m, K5, 2)
            if (m > 0).sum() > 20:
                bgr = cv2.cvtColor(a, cv2.COLOR_RGB2BGR)
                a = cv2.cvtColor(cv2.inpaint(bgr, m, 3, cv2.INPAINT_NS), cv2.COLOR_BGR2RGB)
                n_fix += 1
        im2 = Image.fromarray(a)
        c = to_canvas(im2)
        c.save(f"{OUT_REF}/{nm}.jpg", quality=95)
        c.save(f"{OUT_FIRST}/{nm}.jpg", quality=95)
        n += 1
    print(f"[✓][shard {ARGS.shard}] {n} 帧，补清角标 {n_fix} 帧", flush=True)


if __name__ == "__main__":
    main()
