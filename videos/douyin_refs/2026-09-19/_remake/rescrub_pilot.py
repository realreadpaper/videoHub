#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""参考帧去字（双带版 · 本批重标定）—— 补 v5 的两处不适配。

为什么不能用 `rescrub_sub.py` v5 直接跑这批
------------------------------------------
两处都是**硬编码参数与这批片子不对齐**，表现为「明明有字却判为干净」：
  ① v5 只清台词带（MASK_BAND 850–1010），够不着**底部免责声明**
     「剧情演绎 无不良引导 请勿模仿」（本批实测 y≈1278–1329，常为两行）→ 声明条原样进成片。
  ② v5 的判带 STRIP=(866,986) 与本批字幕位置**没对齐**：本批台词字实际落在
     y≈919–1040，只占 v5 行带的下半段 → 列密度被行带高度稀释，
     实测最大列密度 0.39–1.00，**多数帧达不到 v5 的 COL_TH=0.60**
     → 11 张里只有 1 张被判命中（其余 10 张明明带字却放行）。

本版做法
--------
带 1（台词）：STRIP (915,1045)，阈值按本批 11 张实测重标 ——
              COL_TH=0.20 时「干净帧」最多 10 列、「带字帧」最少 115 列，
              分离度极大，取 **MIN_HOT_COLS=60**（两侧各留 6×/2× 余量）。
带 2（声明）：STRIP (1272,1334)，阈值 COL_TH=0.30 / MIN_HOT_COLS=12。
掩蔽：**只掩热列的水平范围**（左右各放 15 px），不再整幅宽 ——
      本批画面下沿常有肉块/桌面等实体，整幅宽会把不该动的地方一并糊掉。
填充：掩蔽区下方还有邻带 → 竖向线性渐变（v5 原法）；
      掩蔽区贴到画面下沿（下方无邻带可取色）→ 把上方同宽条带**拉伸**盖下来。

用法
----
  python3 rescrub_pilot.py --indir /abs/in --outdir /abs/out [--report x.json]
"""
import argparse
import glob
import json
import os

import cv2
import numpy as np

H, W = 1344, 768

# ── 带 1：台词字幕 ────────────────────────────────────────────────
STRIP1 = (915, 1045)
MASK1 = (905, 1055)
COL_TH1 = 0.20
MIN_HOT1 = 60
# ── 带 2：底部免责声明 ────────────────────────────────────────────
STRIP2 = (1272, 1334)
MASK2 = (1266, 1344)
COL_TH2 = 0.30
MIN_HOT2 = 12

FILL_PAD = 6      # 竖向渐变取的上下邻带高度
SRC_H = 80        # 贴底时从上方取多高的源带做拉伸
X_PAD = 15        # 热列水平范围左右各放多少像素
FULL_W_RATIO = 0.80   # 热列范围宽于整幅这个比例时，直接按整幅宽处理
REDROW = (970, 1100)  # 红色引导箭头的**检测**行范围（本批实测 y≈962–1100）
REDMASK = (950, 1120)  # 红色引导箭头的**掩蔽**行范围 —— 必须比检测带更低
#   ★ 踩过：只把箭头并进台词带（掩蔽到 1055）→ 箭头下沿 1055–1099 那一截留了下来，
#     在成片里仍能看到半截红 ▼。箭头比台词带更靠下，必须单独给一条掩蔽带。
RED_MIN = 10          # 红列单凭自己也能触发清理（有些帧没字幕但有箭头）

K = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))


def glyph_core(img):
    """黄/白字素 ∩ 黑描边邻域（沿用 v5 判据，仅阈值重标）。"""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1].astype(np.int16), hsv[:, :, 2].astype(np.int16)
    yellow = (h >= 12) & (h <= 42) & (s >= 90) & (v >= 120)
    white = (s <= 55) & (v >= 185)
    dark = (v <= 115)
    dd = cv2.dilate(dark.astype(np.uint8), K, iterations=2) > 0
    return (yellow | white) & dd


def red_cols(img, y0, y1, frac=0.12):
    """左下的**红色引导箭头**（抖音那种 ▼）检测 —— 它不在黄/白字素判据里。

    实测 4 条成片里 3 条把它原样画了出来（纯红形状最容易漏网）。
    红是强饱和色，按列统计红色像素占比即可稳定抓到；风险是酱汁/肉块本身偏红
    （u042 排骨镜整幅都是）会一并命中，但那几张本来就要整幅宽处理，无额外损失。
    """
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h = hsv[:, :, 0].astype(np.int16)
    s = hsv[:, :, 1].astype(np.int16)
    v = hsv[:, :, 2].astype(np.int16)
    red = ((h <= 10) | (h >= 170)) & (s >= 120) & (v >= 90)
    return red[y0:y1].mean(0) > frac


def x_span(mask_cols):
    """把一个「列为 True/False」的掩码转成需要掩蔽的 x 范围（左右各放 X_PAD）。"""
    idx = np.flatnonzero(mask_cols)
    x0 = max(0, int(idx.min()) - X_PAD)
    x1 = min(W, int(idx.max()) + 1 + X_PAD)
    if (x1 - x0) > FULL_W_RATIO * W:
        x0, x1 = 0, W
    return x0, x1


def hot_range(core, strip, col_th, min_hot):
    """在检测带内按列密度找字，返回 (命中列数, x0, x1)；不命中则 x 范围为 None。"""
    y0, y1 = strip
    col = core[y0:y1].mean(0)
    hot = col > col_th
    n = int(hot.sum())
    if n < min_hot:
        return n, None, None
    x0, x1 = x_span(hot)
    return n, x0, x1


def fill(img, y0, y1, x0, x1):
    """掩蔽区的填充：下方有邻带用竖向渐变，贴底则拉伸上方内容。"""
    out = img.copy()
    if y1 < H - 2:
        a = img[max(0, y0 - FILL_PAD):y0, x0:x1].mean(0)      # (w,3)
        b = img[y1:min(H, y1 + FILL_PAD), x0:x1].mean(0)
        h = y1 - y0
        t = ((np.arange(h) + 1) / (h + 1))[:, None, None]
        out[y0:y1, x0:x1] = np.clip(
            a[None] * (1 - t) + b[None] * t, 0, 255).astype(np.uint8)
    else:
        sy0 = max(0, y0 - SRC_H)
        src = img[sy0:y0, x0:x1]
        if src.size:
            out[y0:y1, x0:x1] = cv2.resize(
                src, (x1 - x0, y1 - y0), interpolation=cv2.INTER_LINEAR)
    return out


def process(path, outpath):
    img = cv2.imread(path)
    if img is None:
        return None
    if img.shape[:2] != (H, W):
        img = cv2.resize(img, (W, H))
    core = glyph_core(img)
    out = img.copy()
    hits = []

    # ① 台词带（只认黄白字素列）
    n, x0, x1 = hot_range(core, STRIP1, COL_TH1, MIN_HOT1)
    if x0 is not None:
        out = fill(out, MASK1[0], MASK1[1], x0, x1)
        hits.append("sub:%d[x%d-%d]" % (n, x0, x1))

    # ② 红色引导箭头（独立掩蔽带，比台词带更低）
    rc = red_cols(img, *REDROW)
    n_red = int(rc.sum())
    if n_red >= RED_MIN:
        ax0, ax1 = x_span(rc)
        out = fill(out, REDMASK[0], REDMASK[1], ax0, ax1)
        hits.append("arrow:%d[x%d-%d]" % (n_red, ax0, ax1))

    # ③ 底部免责声明带
    n, x0, x1 = hot_range(core, STRIP2, COL_TH2, MIN_HOT2)
    if x0 is not None:
        out = fill(out, MASK2[0], MASK2[1], x0, x1)
        hits.append("disc:%d[x%d-%d]" % (n, x0, x1))

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
        print("  %-30s %s  %s" % (nm, "清" if h else "干净", " ".join(h)))
    clean = sum(1 for r in rows if not r["hits"])
    print("[✓] %d 张：清理 %d，本就干净 %d" % (len(rows), len(rows) - clean, clean))
    if args.report:
        os.makedirs(os.path.dirname(args.report), exist_ok=True)
        json.dump(rows, open(args.report, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
