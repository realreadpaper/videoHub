#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""定位参考帧里原片「叠加层」（黄字字幕 + 红箭头标注）的真实行带。

为什么之前会打偏：旧行带 (866,986) 是从少量帧目视估的，没做全量剖面，
  结果字幕实际在画面更低的位置，清洗 100% 落空。

本脚本对全量参考帧做跨帧分位数剖面：
  字幕/箭头是**固定位置的叠加层** → 在同一 y 上跨帧一致出现 → p75/p90 剖面会出现尖峰；
  画面物体（食物、灯光、黄衣服）各帧位置不同 → 只抬高均值，不抬高 p90 尖峰。
用法: python probe_sub_band.py [--dir full_ref2_v3]
"""
import argparse
import glob
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
H, W = 1344, 768


def masks(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1].astype(np.int16), hsv[:, :, 2].astype(np.int16)
    yellow = (h >= 12) & (h <= 42) & (s >= 90) & (v >= 120)
    white = (s <= 55) & (v >= 185)
    dark = (v <= 115)
    dd = cv2.dilate(dark.astype(np.uint8), np.ones((7, 7), np.uint8), iterations=2) > 0
    text = (yellow | white) & dd                     # 黄/白字 + 黑描边邻域
    red = ((h <= 8) | (h >= 172)) & (s >= 140) & (v >= 120)   # 纯红：箭头/标注
    return text.astype(np.float32), red.astype(np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="full_ref2_v3")
    ap.add_argument("--out", default="_diag/SUBSCAN.json")
    a = ap.parse_args()
    files = sorted(glob.glob(os.path.join(HERE, a.dir, "*.jpg")))
    print(f"扫描 {len(files)} 帧  {a.dir}")
    T = np.zeros((len(files), H), np.float32)
    R = np.zeros((len(files), H), np.float32)
    for i, p in enumerate(files):
        img = cv2.imread(p)
        if img is None:
            continue
        if img.shape[:2] != (H, W):
            img = cv2.resize(img, (W, H))
        t, r = masks(img)
        T[i] = t.mean(1)
        R[i] = r.mean(1)
        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(files)}", flush=True)

    for tag, M in (("黄/白字素", T), ("纯红(箭头)", R)):
        p50 = np.percentile(M, 50, 0)
        p90 = np.percentile(M, 90, 0)
        p99 = np.percentile(M, 99, 0)
        print(f"\n===== {tag}：跨帧剖面（每 16 行）=====")
        peak_y = int(np.argmax(p90))
        for y in range(608, H, 16):
            bar = "#" * int(p90[y] * 260)
            mark = "  <== p90 峰值" if abs(y - peak_y) < 16 else ""
            print(f"  {y:4d} p50={p50[y]:.4f} p90={p90[y]:.4f} p99={p99[y]:.4f} {bar}{mark}")
        print(f"  → p90 峰值行 y={peak_y}  值={p90[peak_y]:.4f}")

    # 每帧在底部可疑区(y>=1000)的黄字素总量：挑出真带字的帧
    print("\n===== 每帧底部 y>=1000 黄字素均值 top20 =====")
    low = T[:, 1000:].mean(1)
    order = np.argsort(-low)[:20]
    for i in order:
        print(f"  {os.path.basename(files[i])[:-4]:12s} {low[i]:.4f}")
    np.save(os.path.join(HERE, "_diag/_T.npy"), T)
    np.save(os.path.join(HERE, "_diag/_R.npy"), R)
    print(f"\n-> 剖面矩阵存到 _diag/_T.npy / _diag/_R.npy  (files={len(files)})")


if __name__ == "__main__":
    main()
