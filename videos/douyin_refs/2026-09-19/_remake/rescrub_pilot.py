#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""参考帧去字（双带版）—— 补 v5 只清台词带、够不着底部免责声明的问题。

为什么要有这个脚本
------------------
2026-09-19 试跑 4 镜，成片**全部**带两种烧死文字：
  ① 台词字幕条（y≈919–992）—— v5 的 MASK_BAND(850,1010) 能覆盖 ✓
  ② 底部免责声明「剧情演绎 无不良引导 请勿模仿」（实测 y≈1278–1329，常为两行）
     —— **在 v5 覆盖范围之外** ❌ 于是原样进了成片。
实测 8 张 first/last 参考帧，两条带**无一例外**都存在，所以必须两条一起清。

做法
----
带 1：完全沿用 `rescrub_sub.py` v5 的实测参数（STRIP 866–986 判、掩 850–1010、整幅宽），
      阈值 COL_TH=0.60 / MIN_HOT_COLS=15 是 373 帧实测标定出来的，**不要动**。
带 2：判带 1272–1338，命中则**只掩热列的水平范围**（左右各放 12 px），
      避免整幅宽把画面下沿不该动的地方也糊掉。
填充：带 1 用 v5 的竖向线性渐变（上下邻带取色插值）；
      带 2 底部贴到画面下沿、下方无邻带可取，改用**把上方同宽的一条竖带拉伸下来**
      （地板/桌面多为竖向结构，拉伸比渐变更自然，也不会出现凭空色块）。

用法
----
  python3 rescrub_pilot.py --indir /abs/in --outdir /abs/out
"""
import argparse
import glob
import json
import os

import cv2
import numpy as np

H, W = 1344, 768

# ── 带 1：台词字幕（v5 实测值，勿改）────────────────────────────────
STRIP1 = (866, 986)
MASK1 = (850, 1010)
# ── 带 2：底部免责声明（本批实测 y≈1278–1329 / 单行时 1278–1304）───
STRIP2 = (1272, 1338)
MASK2 = (1264, 1344)

COL_TH = 0.60        # 列命中率阈值（v5 标定）
MIN_HOT_COLS = 15    # 至少这么多列才算命中（v5 标定）
FILL_PAD = 6         # 带 1 竖向渐变取的上下邻带高度
SRC_H = 72           # 带 2 拉伸填充取的上方源带高度
X_PAD = 12           # 带 2 水平方向额外让出的像素

K = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))


def glyph_core(img):
    """黄/白字素 ∩ 黑描边邻域 —— 与 v5 完全一致，勿改。"""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1].astype(np.int16), hsv[:, :, 2].astype(np.int16)
    yellow = (h >= 12) & (h <= 42) & (s >= 90) & (v >= 120)
    white = (s <= 55) & (v >= 185)
    dark = (v <= 115)
    dd = cv2.dilate(dark.astype(np.uint8), K, iterations=2) > 0
    return (yellow | white) & dd


def vgrad_fill(img, y0, y1, pad=FILL_PAD):
    """带 1 填充：竖向线性渐变（v5 原函数）。"""
    out = img.copy().astype(np.float32)
    a = img[max(0, y0 - pad):y0].mean(0)
    b = img[y1:min(H, y1 + pad)].mean(0)
    h = y1 - y0
    t = ((np.arange(h) + 1) / (h + 1))[:, None, None]
    out[y0:y1] = a[None] * (1 - t) + b[None] * t
    return np.clip(out, 0, 255).astype(np.uint8)


def stretch_fill(img, y0, y1, x0, x1):
    """带 2 填充：把上方 [y0-SRC_H, y0) 的同宽条带拉伸下来盖住 [y0,y1)。

    底部贴边时下方没有邻带可取色，渐变会退化成一条纯色带（像糊了一块）。
    拉伸上方内容能保住地板/桌面的竖向纹理，接缝也不明显。
    """
    out = img.copy()
    sy0 = max(0, y0 - SRC_H)
    src = img[sy0:y0, x0:x1]
    if src.size == 0:
        return out
    th, tw = y1 - y0, x1 - x0
    out[y0:y1, x0:x1] = cv2.resize(src, (tw, th), interpolation=cv2.INTER_LINEAR)
    return out


def band_hit(core, strip):
    y0, y1 = strip
    col = core[y0:y1].mean(0)
    hot = col > COL_TH
    n = int(hot.sum())
    return n, hot


def process(path, outpath):
    img = cv2.imread(path)
    if img is None:
        return None
    if img.shape[:2] != (H, W):
        img = cv2.resize(img, (W, H))
    core = glyph_core(img)
    out = img.copy()
    hits = []

    # ── 带 1：整幅宽掩蔽（v5 策略）────────────────────────────────
    n1, _ = band_hit(core, STRIP1)
    if n1 >= MIN_HOT_COLS:
        out = vgrad_fill(out, *MASK1)
        hits.append("sub:%d" % n1)

    # ── 带 2：只掩热列的水平范围 ──────────────────────────────────
    n2, hot2 = band_hit(core, STRIP2)
    if n2 >= MIN_HOT_COLS:
        idx = np.flatnonzero(hot2)
        x0 = max(0, int(idx.min()) - X_PAD)
        x1 = min(W, int(idx.max()) + 1 + X_PAD)
        out = stretch_fill(out, MASK2[0], MASK2[1], x0, x1)
        hits.append("disc:%d[x%d-%d]" % (n2, x0, x1))

    os.makedirs(os.path.dirname(outpath), exist_ok=True)
    cv2.imwrite(outpath, out, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--indir", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--report", default="")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.indir, "*.jpg")))
    rows = []
    for p in files:
        nm = os.path.basename(p)
        h = process(p, os.path.join(args.outdir, nm))
        if h is None:
            print("  [!] 读不了 %s" % nm)
            continue
        rows.append({"nm": nm[:-4], "hits": h})
        mark = "清" if h else "干净"
        print("  %-30s %s  %s" % (nm, mark, " ".join(h)))
    clean = sum(1 for r in rows if not r["hits"])
    print("[✓] %d 张：清理 %d，本就干净 %d" % (len(rows), len(rows) - clean, clean))
    if args.report:
        os.makedirs(os.path.dirname(args.report), exist_ok=True)
        json.dump(rows, open(args.report, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
