#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""核验生成片是否被模型烧了字幕（幻觉 or 参考帧泄漏）。

判据复用 rescrub_sub 的窄行带 + 列密度计数：
  真字幕行在带内「列密度 > COL_TH 的列数」远大于背景。
对每片抽 5 帧（0.15/0.35/0.55/0.75/0.90），打印列数与该帧带内平均密度。
用法: python check_burn_in.py <dir1> [dir2 ...]
"""
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rescrub_sub import COL_TH, MIN_HOT_COLS, STRIP, glyph_core  # noqa: E402

NAMES = ["dy1_s093", "dy1_s088", "dy2_s118", "dy2_s075", "dy3_s145", "dy3_s119"]
TS = [0.15, 0.35, 0.55, 0.75, 0.90]


def scan(path):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return None
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    out = []
    for t in TS:
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(n * t) - 1))
        ok, im = cap.read()
        if not ok:
            continue
        if im.shape[:2] != (1344, 768):
            im = cv2.resize(im, (768, 1344))
        c = glyph_core(im)[STRIP[0]:STRIP[1]]
        out.append((int((c.mean(0) > COL_TH).sum()), float(c.mean())))
    cap.release()
    return out


def main():
    dirs = sys.argv[1:] or ["_six/gen", "_six/gen3"]
    print(f"判据: 行带 y∈{STRIP}  列密度阈 {COL_TH}  认定字幕需 ≥{MIN_HOT_COLS} 列\n")
    for d in dirs:
        print(f"=== {d} ===")
        for nm in NAMES:
            p = os.path.join(d, nm + ".mp4")
            if not os.path.exists(p):
                print(f"  {nm:10s} 缺")
                continue
            r = scan(p)
            if not r:
                print(f"  {nm:10s} 读失败")
                continue
            cols = [x[0] for x in r]
            dens = [x[1] for x in r]
            hit = sum(1 for c in cols if c >= MIN_HOT_COLS)
            flag = "★烧字" if hit else ("灰区" if max(cols) >= 8 else "干净")
            print(f"  {nm:10s} 列数={cols}  带内密度均={[round(x,3) for x in dens]}  {flag}")
        print()


if __name__ == "__main__":
    main()
