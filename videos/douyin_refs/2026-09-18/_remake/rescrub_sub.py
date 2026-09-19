#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""参考帧硬字幕去除 v5（补 v3/v4 的漏检）。

为什么 v3/v4 漏了：
  v3/v4 靠 detect_tune.find_hits 出框 → stroke_mask 只在框内取笔画。
  实测 dy3 有 7 帧字幕**原样留着**（_diag/REFSCAN.jpg #2/#3/#4/#7/#8/#17/#18），
  框要么没出、要么出歪 → 掩码没覆盖到字。
  而 first_frame 一旦钉这种帧，字幕 100% 进成片首帧。

本版换思路，不依赖检测框：
  ① 字幕行带**固定**（实测 y=882-983，102 px，峰值密度 0.29）→ 只在这条带里干活；
  ② 带内取「黄/白字素 ∩ 黑描边邻域」→ 按**列投影**找字的横向范围；
  ③ 对每个横向连通段，掩掉整条带高（连描边一起），再 cv2.inpaint。
  这样：该列有字才动（干净帧零改动），有字则连描边一起铲掉，不会留黄边残影。

用法：
  python rescrub_sub.py --indir full_ref2_v3            # 原地清洗
  python rescrub_sub.py --indir full_first4 --outdir full_first4b
"""
import os, sys, json, glob, argparse
import numpy as np
import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
H, W = 1344, 768
STRIP = (866, 986)          # ★ 检测带：只用来算列密度，越准越窄越好
MASK_BAND = (850, 1010)     # ★ 掩蔽带：比检测带放宽，保证连描边/上下沿一起铲掉
# 行带两个坑，都实测踩过：
#   ① 只取 880-986 → 切掉字幕头部 14 px → 残字被 inpaint 边界带成**黄条**；
#   ② 取 856-1005（150 px）→ 字幕只占带高 2/3，列密度被稀释到 0.4，
#      与背景列（0.38/0.32…）混在一起 → 掩码碎成条状、字缝留黄残渣。
# 横向同理：按热列取 x 范围会漏掉末尾字（实测残留「我」「鱼还」）
#   → 字幕是本片**固定位置的整行叠字**，直接**整幅宽掩蔽**最稳，填充用竖向渐变。
COL_TH = 0.60               # 列命中率阈值
MIN_HOT_COLS = 15           # 至少这么多列才认定有字幕
FILL_PAD = 6                # 竖向渐变填充取的上下邻带高度
K = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))

# 判据怎么来的（全 373 帧实测）：
#   检测带内「列密度 > 0.60 的列数」——真字幕 16~53，其余全部 ≤ 13 → 阈值取 15。
#   反例：阈值 0.04 会把 93.8% 的帧误判成有字（整条带糊掉）；0.40 会误判 9 帧。
#   余量偏薄，故**命中集必须目视复核**（`_diag/REFSCAN.jpg` / `V5_VERIFY*.jpg`）。


def glyph_core(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1].astype(np.int16), hsv[:, :, 2].astype(np.int16)
    yellow = (h >= 12) & (h <= 42) & (s >= 90) & (v >= 120)
    white = (s <= 55) & (v >= 185)
    dark = (v <= 115)
    dd = cv2.dilate(dark.astype(np.uint8), K, iterations=2) > 0
    return (yellow | white) & dd


def strip_mask(img):
    """返回该帧需要铲除的掩码（整图大小）+ 是否命中"""
    core = glyph_core(img)
    y0, y1 = STRIP
    col = core[y0:y1].mean(0)
    if int((col > COL_TH).sum()) < MIN_HOT_COLS:
        return np.zeros((H, W), np.uint8), 0
    # 命中：整个掩蔽带 + 整幅宽（字幕是固定位置的整行叠字，按热列取范围必漏末尾字）
    a0, a1 = MASK_BAND
    m = np.zeros((H, W), np.uint8)
    m[a0:a1, :] = 255
    return m, 1


def vgrad_fill(img, y0, y1, pad=FILL_PAD):
    """竖向线性渐变填充：[y0,y1) 用上下邻带的颜色沿 y 插值。

    比 cv2.inpaint 更适合「横向长条洞」：inpaint 会在洞内续边缘 → 出竖向条纹与黄丝；
    竖向渐变天然平滑，且人物/背景多为竖向结构，观感更自然。
    """
    out = img.copy().astype(np.float32)
    a = img[max(0, y0 - pad):y0].mean(0)
    b = img[y1:min(H, y1 + pad)].mean(0)
    h = y1 - y0
    t = ((np.arange(h) + 1) / (h + 1))[:, None, None]
    out[y0:y1] = a[None] * (1 - t) + b[None] * t
    return np.clip(out, 0, 255).astype(np.uint8)


def process(path, outpath):
    img = cv2.imread(path)
    if img is None:
        return None
    if img.shape[:2] != (H, W):
        img = cv2.resize(img, (W, H))
    m, hit = strip_mask(img)
    if not hit:
        out = img
        pct = 0.0
    else:
        out = vgrad_fill(img, *MASK_BAND)
        pct = float((m > 0).mean() * 100)
    os.makedirs(os.path.dirname(outpath), exist_ok=True)
    cv2.imwrite(outpath, out, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return pct, hit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--indir", required=True)
    ap.add_argument("--outdir", default="")
    args = ap.parse_args()
    ind = os.path.join(HERE, args.indir) if not os.path.isabs(args.indir) else args.indir
    outd = os.path.join(HERE, args.outdir) if args.outdir else ind

    files = sorted(glob.glob(os.path.join(ind, "*.jpg")))
    touched, rows = 0, []
    for i, p in enumerate(files):
        nm = os.path.basename(p)
        r = process(p, os.path.join(outd, nm))
        if r:
            pct, hit = r
            if hit:
                touched += 1
                rows.append(dict(nm=nm[:-4], mask_pct=round(pct, 2)))
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(files)} …", flush=True)
    print(f"[✓] {args.indir} → {outd}：{len(files)} 帧，清洗 {touched} 帧 "
          f"({touched/max(len(files),1)*100:.1f}%)  {[r['nm'] for r in rows]}")
    json.dump(rows, open(os.path.join(HERE, "_diag", f"RESCRUB_{os.path.basename(ind)}.json"),
                         "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
