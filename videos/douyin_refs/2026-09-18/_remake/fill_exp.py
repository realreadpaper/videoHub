#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""字幕块填充方案对比（针对 dy3_s054 这类"大字幕横跨画面中部"的情形）。

结论导向：目标不是"恢复细节"，而是**彻底消灭字形轮廓**——
  下游视频模型只要看到残存笔形，就会把它复刻成字幕。
"""
import sys

import cv2
import numpy as np

H, W = 1344, 768


def vgrad(im, y0, y1, pad=10):
    o = im.copy()
    a = im[y0 - pad:y0].mean(0).astype(np.float32)
    b = im[y1:y1 + pad].mean(0).astype(np.float32)
    h = y1 - y0
    for i in range(h):
        t = (i + 1) / (h + 1)
        o[y0 + i] = (a * (1 - t) + b * t).astype(np.uint8)
    return o


def mirror(im, y0, y1):
    """上下邻域镜像 + 线性权重混合"""
    h = y1 - y0
    ti = np.clip(np.arange(y0 - 1, y0 - 1 - h, -1), 0, H - 1)
    bi = np.clip(np.arange(y1 + h - 1, y1 - 1, -1), 0, H - 1)
    top = im[ti].astype(np.float32)
    bot = im[bi].astype(np.float32)
    w = np.linspace(0, 1, h).reshape(-1, 1, 1)
    o = im.copy()
    o[y0:y1] = (top * (1 - w) + bot * w).astype(np.uint8)
    return o


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "full_ref2_v3/dy3_s054.jpg"
    Y0, Y1 = 802, 1000
    img = cv2.imread(src)
    m = np.zeros((H, W), np.uint8)
    m[Y0:Y1, :] = 255

    outs = {
        "orig": img,
        "TELEA8": cv2.inpaint(img, m, 8, cv2.INPAINT_TELEA),
        "TELEA20": cv2.inpaint(img, m, 20, cv2.INPAINT_TELEA),
        "NS8": cv2.inpaint(img, m, 8, cv2.INPAINT_NS),
        "VGRAD": vgrad(img, Y0, Y1),
        "MIRROR": mirror(img, Y0, Y1),
    }
    t = cv2.inpaint(img, m, 8, cv2.INPAINT_TELEA)
    t[Y0:Y1] = cv2.GaussianBlur(t[Y0:Y1], (0, 0), 8)
    outs["TELEA+BLUR"] = t

    keys = list(outs)
    tiles = []
    for k in keys:
        c = outs[k][780:1020]
        t2 = cv2.resize(c, (300, 94))
        cv2.putText(t2, k, (6, 16), cv2.FONT_HERSHEY_SIMPLEX, .5, (0, 255, 255), 1)
        tiles.append(t2)
    blank = np.zeros_like(tiles[0])
    while len(tiles) % 3:
        tiles.append(blank)
    rows = [np.hstack(tiles[i:i + 3]) for i in range(0, len(tiles), 3)]
    cv2.imwrite("_diag/FILL_EXP3.jpg", np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 92])

    print(f"{'方案':<12s} 带内黄素   带内暗块   高频能量")
    for k in keys:
        o = outs[k][Y0:Y1]
        hsv = cv2.cvtColor(o, cv2.COLOR_BGR2HSV)
        h, s, v = hsv[:, :, 0], hsv[:, :, 1].astype(np.int16), hsv[:, :, 2].astype(np.int16)
        yel = ((h >= 12) & (h <= 42) & (s >= 90) & (v >= 120)).mean()
        drk = (v <= 115).mean()
        lap = cv2.Laplacian(cv2.cvtColor(o, cv2.COLOR_BGR2GRAY), cv2.CV_32F).var()
        print(f"{k:<12s} {yel:8.4f}  {drk:8.4f}  {lap:9.0f}")
    print("-> _diag/FILL_EXP3.jpg")


if __name__ == "__main__":
    main()
