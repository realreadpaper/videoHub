#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""参考帧去字 v2 —— 只掩「笔画」并做真 inpaint（修 v1 的大面积涂抹被学进成片）。

v1（rescrub_pilot.py）为什么不行
--------------------------------
v1 掩「整条带 + 热列范围」（台词带 150 px 高），填充用竖向渐变 / 拉伸。
结果：字是没了，但**参考图上留下整片竖向涂抹**，而 H3 会把这种纹理**原样学进成片** ——
4 条新片里 u060 / u042 出现明显竖条纹，比原来的字幕还难看。
（铁律：参考图上的一切纹理都会被复刻，包括你去字时留下的疤。）

v2 做法
-------
mask 收紧到「笔画本身」：黄/白字素 **∩ 黑描边邻域**，再 dilate 3 px 吃掉抗锯齿边缘；
红箭头用红掩码，且**只在左边缘 x<230 找**（否则 u042 那种整幅酱色的镜会把酱汁全掩掉）。
然后 `cv2.inpaint(INPAINT_TELEA)` —— 它是**结构感知**的，会用周围真实的墙/地/桌面纹理补洞，
而不是涂一片渐变，所以不会留下可被复刻的「疤」。

带位置（768×1344，本批实测）：
  台词   y≈919–1040   → 搜索区 900–1060
  红箭头 y≈962–1100   → 搜索区 945–1125，且 x<230
  免责   y≈1278–1329  → 搜索区 1266–1344

用法：python3 rescrub_pilot2.py --indir /abs/in --outdir /abs/out [--report x.json]
"""
import argparse
import glob
import json
import os

import cv2
import numpy as np

H, W = 1344, 768

BAND_SUB = (900, 1060)      # 台词带搜索区
BAND_ARROW = (945, 1125)    # 红箭头搜索区
ARROW_XMAX = 230            # 红箭头只在左侧找
BAND_DISC = (1266, 1344)    # 免责声明带

COL_TH = 0.20               # 列密度阈值（本批标定：干净帧 ≤10 列，带字帧 ≥115 列）
MIN_HOT = 60
DILATE = 1                  # ★ 只放 1 px：v2 放 3 px 会让笔画连成整片，
                            #   而 INPAINT 会把黑描边往里传播 → 填出整条黑带（实测踩到）
INPAINT_R = 6

K7 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
K3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))


def parts(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h = hsv[:, :, 0].astype(np.int16)
    s = hsv[:, :, 1].astype(np.int16)
    v = hsv[:, :, 2].astype(np.int16)
    yellow = (h >= 12) & (h <= 42) & (s >= 90) & (v >= 120)
    white = (s <= 55) & (v >= 185)
    dark = v <= 115
    red = ((h <= 10) | (h >= 170)) & (s >= 120) & (v >= 90)
    return yellow, white, dark, red


def glyph_core(img):
    """黄/白字素 ∩ 黑描边邻域 —— 描边约束能滤掉「酱汁高光 / 肉块纹理」这类误报。"""
    yellow, white, dark, _ = parts(img)
    dd = cv2.dilate(dark.astype(np.uint8), K7, iterations=2) > 0
    return (yellow | white) & dd


def stroke_mask(img):
    """实际要铲掉的像素 = 黄白笔画 **∪ 贴着笔画的黑描边**。

    ★ 只圈黄白笔画是不够的：字是「黄字 + 黑描边」，描边本身是暗色、不在黄白判据里，
      只铲亮的部分就会留下**镂空的字影**（v3 实测踩到，灰字形状清清楚楚）。
      描边用「暗色 ∩ 笔画邻域」取，既能包住描边，又不会误伤画面里别处的暗部。
    """
    yellow, white, dark, _ = parts(img)
    dd = cv2.dilate(dark.astype(np.uint8), K7, iterations=2) > 0
    core = (yellow | white) & dd
    near = cv2.dilate(core.astype(np.uint8),
                      cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13)),
                      iterations=1) > 0
    return (core | (dark & near))


def band_hit(img, y0, y1, x0=0, x1=W):
    core = glyph_core(img)[y0:y1, x0:x1]
    return int((core.mean(0) > COL_TH).sum())


def clean(img, verbose=False):
    H_, W_ = img.shape[:2]
    core = glyph_core(img)
    stroke = stroke_mask(img)
    _, _, _, red = parts(img)
    m = np.zeros((H_, W_), np.uint8)
    notes = []

    # ① 台词（判定用核心笔画，掩蔽用笔画+描边）
    if band_hit(img, *BAND_SUB) >= MIN_HOT:
        y0, y1 = BAND_SUB
        m[y0:y1] |= stroke[y0:y1].astype(np.uint8) * 255
        notes.append("sub")

    # ② 红箭头（只在左边缘找）
    y0, y1 = BAND_ARROW
    sub = red[y0:y1, :ARROW_XMAX]
    if int((sub.mean(0) > 0.12).sum()) >= 8:
        m[y0:y1, :ARROW_XMAX] |= sub.astype(np.uint8) * 255
        notes.append("arrow")

    # ③ 免责声明
    if band_hit(img, *BAND_DISC) >= 12:
        y0, y1 = BAND_DISC
        m[y0:y1] |= stroke[y0:y1].astype(np.uint8) * 255
        notes.append("disc")

    if not m.any():
        return img, notes
    m = cv2.dilate(m, K3, iterations=DILATE)
    out = span_fill(img, m)
    if verbose:
        print("     掩码占画面 %.2f%%" % (100.0 * (m > 0).mean()))
    return out, notes


def span_fill(img, mask):
    """逐列跨洞线性插值 —— 去掉「细横线」最稳的经典手法。

    为什么不用 cv2.inpaint：掩码是横贯整幅的细笔画，INPAINT 会沿着掩码边界
    把**黑描边的颜色往里传播**，掩码一粗就填出整条黑带（v2 实测踩到）。
    插值只用洞**上下紧邻的真实像素**，天然不会引入黑色，也不会像 v1 那样涂出大片渐变。
    """
    out = img.copy().astype(np.float32)
    m = mask > 0
    h, w = m.shape
    for x in range(w):
        col = m[:, x]
        if not col.any():
            continue
        ys = np.flatnonzero(col)
        brk = np.flatnonzero(np.diff(ys) > 1)
        for s, e in zip(np.concatenate(([0], brk + 1)), np.concatenate((brk, [len(ys) - 1]))):
            a, b = int(ys[s]), int(ys[e])
            ta, tb = a - 1, b + 1
            if ta < 0 and tb >= h:
                continue
            if ta < 0:
                out[a:b + 1, x] = img[tb, x]
            elif tb >= h:
                out[a:b + 1, x] = img[ta, x]
            else:
                A = img[ta, x].astype(np.float32)
                B = img[tb, x].astype(np.float32)
                n = b - a + 1
                t = ((np.arange(n) + 1) / (n + 1))[:, None]
                out[a:b + 1, x] = A[None] * (1 - t) + B[None] * t
    return np.clip(out, 0, 255).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--indir", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--report", default="")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.indir, "*.jpg")))
    rows = []
    for p in files:
        nm = os.path.basename(p)
        img = cv2.imread(p)
        if img is None:
            print("  [!] 读不了 %s" % nm)
            continue
        if img.shape[:2] != (H, W):
            img = cv2.resize(img, (W, H))
        out, notes = clean(img, args.verbose)
        os.makedirs(args.outdir, exist_ok=True)
        cv2.imwrite(os.path.join(args.outdir, nm), out,
                    [cv2.IMWRITE_JPEG_QUALITY, 95])
        rows.append({"nm": nm[:-4], "notes": notes})
        print("  %-30s %s  %s" % (nm, "清" if notes else "干净", " ".join(notes)))
    clean_n = sum(1 for r in rows if not r["notes"])
    print("[OK] %d 张：清理 %d，本就干净 %d" % (len(rows), len(rows) - clean_n, clean_n))
    if args.report:
        os.makedirs(os.path.dirname(args.report), exist_ok=True)
        json.dump(rows, open(args.report, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
