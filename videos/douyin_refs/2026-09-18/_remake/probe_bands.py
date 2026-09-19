#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探针：测出原片硬字幕在 768x1344 参考帧上的固定行带。

原理：字幕是「黄/白字 + 黑描边」，位置在整片里固定不动。
把多张已知带字的帧按行统计「黄白字素密度」，密度高峰即字幕行带。
"""
import os, sys, glob
import numpy as np
import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
H, W = 1344, 768


def glyph_map(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1].astype(np.int16), hsv[:, :, 2].astype(np.int16)
    yellow = (h >= 12) & (h <= 42) & (s >= 90) & (v >= 120)
    white = (s <= 55) & (v >= 185)
    dark = (v <= 115)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    dd = cv2.dilate(dark.astype(np.uint8), k, iterations=2) > 0
    core = (yellow | white) & dd
    return core


def probe(paths, tag):
    acc = np.zeros(H, np.float64)
    n = 0
    for p in paths:
        img = cv2.imread(p)
        if img is None:
            continue
        if img.shape[:2] != (H, W):
            img = cv2.resize(img, (W, H))
        acc += glyph_map(img).mean(1)
        n += 1
    prof = acc / max(n, 1)
    # 找密度峰：> 全局中位数的 3 倍 且 > 0.03
    base = np.median(prof)
    hot = prof > max(base * 3, 0.03)
    # 聚成连续区间
    bands = []
    i = 0
    while i < H:
        if hot[i]:
            j = i
            while j + 1 < H and hot[j + 1]:
                j += 1
            if j - i >= 8:
                bands.append((i, j, round(float(prof[i:j + 1].max()), 3)))
            i = j + 1
        else:
            i += 1
    print(f"[{tag}] n={n} 基线={base:.4f}")
    for b in bands:
        print(f"   行带 y={b[0]}-{b[1]} (h={b[1]-b[0]+1})  峰值密度={b[2]}")
    return bands, prof


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else "full_ref2_v3"
    # 用已知带字的镜做探针
    known = ["dy3_s059", "dy3_s119", "dy3_s138", "dy3_s145", "dy1_s093"]
    paths = [os.path.join(HERE, d, k + ".jpg") for k in known]
    paths = [p for p in paths if os.path.exists(p)]
    bands, prof = probe(paths, "known-dirty")

    # 对照：随机 20 张（大概率也带字）
    import random
    random.seed(0)
    allp = sorted(glob.glob(os.path.join(HERE, d, "*.jpg")))
    probe(random.sample(allp, min(20, len(allp))), "random20")

    # 保存行剖面图
    out = np.zeros((H, 300, 3), np.uint8)
    p = (prof / max(prof.max(), 1e-9) * 280).astype(int)
    for y in range(H):
        cv2.line(out, (0, y), (int(p[y]), y), (0, 255, 0), 1)
    cv2.line(out, (0, int(H * 0.94)), (299, int(H * 0.94)), (0, 0, 255), 1)
    cv2.imwrite(os.path.join(HERE, "_diag", "ROWBANDS.jpg"), out)
    print("-> _diag/ROWBANDS.jpg")
