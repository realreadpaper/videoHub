#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""逐帧检测原片叠加层（硬字幕 + 红箭头标注），不依赖固定位置。

叠加层特征（与画面物体区分）：
  · 红箭头：高饱和纯红（h<8 或 h>172, s>=140），聚成面积 >400 px 的实心块，
            长宽近似（箭头≈方块），且**内部无纹理**（标准差低）。
  · 字幕：黄(h 12-42,s>=90,v>=120) 或 白(s<=55,v>=185) 字素 ∩ 黑描边(v<=115) 膨胀，
           在某一横带内横向聚集（一行 >=200 个命中像素）。
输出每帧：红块 bbox/面积、字幕候选带 (y0,y1,x0,x1)，落盘 JSON。
用法: python detect_overlay.py [--dir full_ref2_v3] [--out _diag/OVERLAY.json]
"""
import argparse
import glob
import json
import os

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
H, W = 1344, 768
K3 = np.ones((3, 3), np.uint8)
K7 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))


def red_boxes(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1].astype(np.int16), hsv[:, :, 2].astype(np.int16)
    red = (((h <= 8) | (h >= 172)) & (s >= 140) & (v >= 110)).astype(np.uint8)
    red = cv2.morphologyEx(red, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    red = cv2.morphologyEx(red, cv2.MORPH_OPEN, K7)
    n, lab, st, cen = cv2.connectedComponentsWithStats(red, 8)
    out = []
    for i in range(1, n):
        x, y, w, hh, area = st[i]
        if area < 400:
            continue
        ar = w / max(hh, 1)
        if not (0.45 <= ar <= 2.2):          # 箭头/方框近似方形
            continue
        m = lab == i
        # 内部要"平"：纯色叠加层 std 低；红衣服/红灯有渐变与纹理
        patch = img[m]
        std = float(patch.std(0).mean())
        if std > 42:
            continue
        out.append(dict(x=int(x), y=int(y), w=int(w), h=int(hh), area=int(area),
                        std=round(std, 1)))
    return out


def text_bands(img):
    """返回字幕候选横带列表 [(y0,y1,x0,x1,px)]"""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1].astype(np.int16), hsv[:, :, 2].astype(np.int16)
    yellow = (h >= 12) & (h <= 42) & (s >= 90) & (v >= 120)
    white = (s <= 55) & (v >= 185)
    dark = (v <= 115)
    dd = cv2.dilate(dark.astype(np.uint8), K7, iterations=2) > 0
    core = (yellow | white) & dd
    # 只保留"亮色核心本身"再聚形，避免零散噪点
    m = cv2.morphologyEx(core.astype(np.uint8), cv2.MORPH_CLOSE,
                         np.ones((5, 21), np.uint8))
    row = m.sum(1)
    bands, y = [], 0
    while y < H:
        if row[y] < 60:
            y += 1
            continue
        y0 = y
        while y < H and (row[y] >= 30 or (y - y0) < 8):
            y += 1
        y1 = y
        sub = m[y0:y1]
        if sub.sum() < 900:
            continue
        xs = np.where(sub.any(0))[0]
        bands.append(dict(y0=int(y0), y1=int(y1), x0=int(xs.min()), x1=int(xs.max()),
                          px=int(sub.sum())))
    return bands


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="full_ref2_v3")
    ap.add_argument("--out", default="_diag/OVERLAY.json")
    a = ap.parse_args()
    files = sorted(glob.glob(os.path.join(HERE, a.dir, "*.jpg")))
    res, nred, ntext = [], 0, 0
    for i, p in enumerate(files):
        img = cv2.imread(p)
        if img is None:
            continue
        if img.shape[:2] != (H, W):
            img = cv2.resize(img, (W, H))
        rb = red_boxes(img)
        tb = text_bands(img)
        nm = os.path.basename(p)[:-4]
        if rb:
            nred += 1
        if tb:
            ntext += 1
        res.append(dict(nm=nm, red=rb, text=tb))
        if (i + 1) % 60 == 0:
            print(f"  {i+1}/{len(files)}  (红{nred} 字{ntext})", flush=True)
    json.dump(res, open(os.path.join(HERE, a.out), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\n[✓] {len(res)} 帧：含红箭头 {nred} 帧 ({nred/len(res)*100:.0f}%)，"
          f"含字幕候选 {ntext} 帧 ({ntext/len(res)*100:.0f}%)")
    print(f"-> {a.out}")
    # 汇总
    for film in ("dy1", "dy2", "dy3"):
        sub = [r for r in res if r["nm"].startswith(film)]
        r1 = sum(1 for r in sub if r["red"])
        r2 = sum(1 for r in sub if r["text"])
        print(f"  {film}: {len(sub)} 帧  红箭头 {r1}  字幕候选 {r2}")


if __name__ == "__main__":
    main()
