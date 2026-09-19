#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全量扫参考帧：找出字幕带(y 870-1010)仍有文字的帧。

判据 text_score = sub带 edge / ctrl带 edge：
  背景干净时两带能量接近 → ~1.0；带内有字幕 → 显著 >1.5。
黄字% (R>150,G>120,B<110,R-B>60) 作辅助，但会被食物/金色包装污染，**必须目视复核**。
输出：_diag/REFSCAN.json + _diag/REFSCAN.jpg（最脏的若干条字幕带，目视用）
"""
import os, json, glob
import numpy as np
import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
H, W = 1344, 768
BAND_SUB = (870, 1010)
BAND_CTRL = (1150, 1290)


def band_metrics(img, y0, y1):
    band = img[y0:y1]
    gray = cv2.cvtColor(band, cv2.COLOR_BGR2GRAY)
    lap = cv2.Laplacian(gray, cv2.CV_32F, ksize=3)
    b, g, r = band[:, :, 0].astype(np.int16), band[:, :, 1].astype(np.int16), band[:, :, 2].astype(np.int16)
    yellow = ((r > 150) & (g > 120) & (b < 110) & ((r - b) > 60)).mean() * 100
    return float(np.abs(lap).mean()), float(yellow)


def scan(d, tag):
    rows = []
    for p in sorted(glob.glob(os.path.join(HERE, d, "*.jpg"))):
        nm = os.path.basename(p)[:-4]
        img = cv2.imread(p)
        if img is None:
            continue
        if img.shape[:2] != (H, W):
            img = cv2.resize(img, (W, H))
        se, sy = band_metrics(img, *BAND_SUB)
        ce, cy = band_metrics(img, *BAND_CTRL)
        rows.append(dict(nm=nm, src=tag, sub_edge=round(se, 2), ctrl_edge=round(ce, 2),
                         score=round(se / max(ce, 1e-6), 2), yellow=round(sy, 3)))
    return rows


res = {}
for d, tag in (("full_ref2_v3", "ref"), ("full_first4", "first"), ("full_last4", "last")):
    if os.path.isdir(os.path.join(HERE, d)):
        res[tag] = scan(d, tag)

allrows = [r for v in res.values() for r in v]
allrows.sort(key=lambda r: -r["score"])
json.dump(res, open(os.path.join(HERE, "_diag", "REFSCAN.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

for tag, v in res.items():
    sc = np.array([r["score"] for r in v])
    print(f"[{tag}] n={len(v)} score: 中位 {np.median(sc):.2f} / p90 {np.percentile(sc,90):.2f} / "
          f">1.5 占 {(sc>1.5).mean()*100:.1f}% / >3 占 {(sc>3).mean()*100:.1f}%")

print("\n== 最脏 30 条 ==")
for r in allrows[:30]:
    print(f"{r['src']:5s} {r['nm']:10s} score={r['score']:6.2f} yellow={r['yellow']:7.3f}")

# 目视拼图：最脏 18 张的「字幕带」
picks = allrows[:18]
tiles = []
for i, r in enumerate(picks):
    d = {"ref": "full_ref2_v3", "first": "full_first4", "last": "full_last4"}[r["src"]]
    img = cv2.imread(os.path.join(HERE, d, r["nm"] + ".jpg"))
    if img is None:
        continue
    if img.shape[:2] != (H, W):
        img = cv2.resize(img, (W, H))
    band = img[BAND_SUB[0]:BAND_SUB[1]]
    band = cv2.resize(band, (620, 104))
    cv2.putText(band, f"#{i+1} {r['nm']} {r['score']:.1f}", (6, 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
    tiles.append(band)
if tiles:
    ncol = 1 if len(tiles) <= 6 else 2
    rows_img = []
    for i in range(0, len(tiles), ncol):
        chunk = tiles[i:i + ncol]
        while len(chunk) < ncol:
            chunk.append(np.zeros_like(tiles[0]))
        rows_img.append(np.hstack(chunk))
    cv2.imwrite(os.path.join(HERE, "_diag", "REFSCAN.jpg"), np.vstack(rows_img),
                [cv2.IMWRITE_JPEG_QUALITY, 92])
    print("\n-> _diag/REFSCAN.jpg  (最脏 18 张字幕带)")
