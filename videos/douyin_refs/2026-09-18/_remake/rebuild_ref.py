#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从原片重抽参考帧并做一次性干净去叠加层（字幕 / 底部小字 / 红箭头）。

为什么必须重抽：
  现有 full_ref2_v3 / full_*4 已被 v3/v4/v5 多轮清洗反复处理，字幕块被 inpaint
  从黑描边取色 → 留下"黄黑斑块"。这些斑块又成为下一次清洗的边界色，越洗越脏。
  原片直抽帧只有"黑边亮字"这一种干净形态，一次到位即可。

叠加层三类（逐帧自适应检测，不依赖固定位置）：
  ① 字幕：亮字素（dy3 黄底黑边 / dy1·dy2 白底黑边）∩ 黑描边邻域，行投影 → 跨行合并成块；
  ② 底部免责小字：同上，但位于画面最下缘；
  ③ 红箭头：纯红实心块（低内部方差）——区别于红色包装袋（有印刷纹理、面积大）。
掩蔽后统一 inpaint（边界干净 → 结果平滑且无字形轮廓）。

用法：
  python rebuild_ref.py --nm dy3_s054           # 单帧，出目视对照图
  python rebuild_ref.py --all                  # 全量 373 帧 → full_ref2_v6/
  python rebuild_ref.py --all --kind first     # 首帧 → full_first6/  (时刻=镜 start)
"""
import argparse
import json
import os

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
J = os.path.join(HERE, "..")
H, W = 1344, 768
FILM_MP4 = {
    "dy1": "7661613126736204025.mp4",
    "dy2": "7686341460064787045.mp4",
    "dy3": "7664454812574337402.mp4",
}
KEY = {"dy1": "01_报恩", "dy2": "02_继母", "dy3": "03_挑食"}
K7 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))


def overlay_boxes(img, y_lo=420, y_hi=1344, gap=48):
    """返回叠加层块列表（文本 + 红箭头），每项含 y0,y1,x0,x1,kind"""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1].astype(np.int16), hsv[:, :, 2].astype(np.int16)

    # ---- ① 文本字素 ----
    yellow = (h >= 15) & (h <= 40) & (s >= 130) & (v >= 150)
    white = (s <= 60) & (v >= 195)
    dark = v <= 95
    core = (yellow | white) & (cv2.dilate(dark.astype(np.uint8), K7, iterations=2) > 0)
    m = cv2.morphologyEx(core.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 25), np.uint8))
    row = m.sum(1)
    segs, y = [], y_lo
    while y < y_hi:
        if row[y] < 12:
            y += 1
            continue
        y0 = y
        while y < y_hi and (row[y] >= 6 or y - y0 < 6):
            y += 1
        segs.append([y0, y])
    merged = []
    for sg in segs:
        if merged and sg[0] - merged[-1][1] <= gap:
            merged[-1][1] = sg[1]
        else:
            merged.append(sg)
    boxes = []
    for y0, y1 in merged:
        px = int(m[y0:y1].sum())
        hh = y1 - y0
        if hh < 30 or px < 1500:
            continue
        xs = np.where(m[y0:y1].any(0))[0]
        x0, x1 = int(xs.min()), int(xs.max())
        if x1 - x0 < 300 or px / hh < 55:
            continue
        boxes.append(dict(y0=y0, y1=y1, x0=x0, x1=x1, px=px, kind="text"))

    # ---- ② 红箭头 ----
    red = (((h <= 8) | (h >= 172)) & (s >= 150) & (v >= 110)).astype(np.uint8)
    red = cv2.morphologyEx(red, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    red = cv2.morphologyEx(red, cv2.MORPH_OPEN, K7)
    n, lab, st, _ = cv2.connectedComponentsWithStats(red, 8)
    for i in range(1, n):
        x, yy, w, hh, area = st[i]
        if not (500 <= area <= 20000):
            continue
        if hh < 30 or w < 18 or yy < y_lo:
            continue
        if not (0.25 <= w / hh <= 3.5):
            continue
        patch = img[lab == i]
        if float(patch.std(0).mean()) > 35:        # 纯色箭头 vs 有纹理的红包装
            continue
        boxes.append(dict(y0=int(yy), y1=int(yy + hh), x0=int(x), x1=int(x + w),
                          px=int(area), kind="arrow"))
    return boxes


def _rect_mask(boxes, pad):
    m = np.zeros((H, W), np.uint8)
    for b in boxes:
        m[max(0, b["y0"] - pad):min(H, b["y1"] + pad),
          max(0, b["x0"] - pad):min(W, b["x1"] + pad)] = 255
    return m


def _stroke_mask(img, boxes, pad=6):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1].astype(np.int16), hsv[:, :, 2].astype(np.int16)
    glyph = ((h >= 15) & (h <= 40) & (s >= 130) & (v >= 150)) | ((s <= 60) & (v >= 195))
    dark = (v <= 95).astype(np.uint8)
    stroke = dark & (cv2.dilate(glyph.astype(np.uint8), K7, iterations=2) > 0)
    core = glyph | (stroke > 0)
    region = _rect_mask(boxes, pad)
    m = (core.astype(np.uint8) * 255) & region
    return cv2.dilate(m, K7, iterations=1)


def _residual(img, box):
    """复检：块内是否还有"亮字素贴黑边"的成行结构（inpaint 后不该有）"""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1].astype(np.int16), hsv[:, :, 2].astype(np.int16)
    glyph = ((h >= 15) & (h <= 45) & (s >= 100) & (v >= 140)) | ((s <= 70) & (v >= 180))
    dark = v <= 110
    core = glyph & (cv2.dilate(dark.astype(np.uint8), K7, iterations=2) > 0)
    sub = core[max(0, box["y0"] - 6):box["y1"] + 6, max(0, box["x0"] - 6):box["x1"] + 6]
    if sub.size == 0:
        return 0.0
    return float(sub.mean())


def scrub(img, boxes, pad=10, radius=8, mode="rect", verify=False):
    """生成掩码并 inpaint。

    ★ 实测结论：**必须用 rect（整块矩形）**。
      'stroke'（只掩字素笔画）看起来更"省"，但对抖音这种**厚黑描边大字幕**会失败：
        描边宽 5~8 px，掩码外沿仍落在描边上 → inpaint 从描边取色 → 填成**字形深灰块**，
        字形轮廓原样保留，下游模型照样复刻成字幕。
      rect 的代价是"糊一块"，但**零字形**，这才是我们的目标（参考帧只做构图引导）。
    mode='rect'   整块矩形掩蔽（默认，推荐）；
    mode='stroke' 仅字素笔画 + 描边（留档，实测在厚描边上不可用）。
    """
    if mode == "rect":
        m = _rect_mask(boxes, pad)
        return cv2.inpaint(img, m, radius, cv2.INPAINT_TELEA), m

    text_boxes = [b for b in boxes if b["kind"] == "text"]
    arrows = [b for b in boxes if b["kind"] == "arrow"]
    m = _stroke_mask(img, text_boxes, pad=pad) | _rect_mask(arrows, pad=12)
    out = cv2.inpaint(img, m, radius, cv2.INPAINT_TELEA)
    if verify and text_boxes:
        bad = [b for b in text_boxes if _residual(out, b) > 0.004]
        if bad:
            m = m | _rect_mask(bad, pad=12)
            out = cv2.inpaint(img, m, radius, cv2.INPAINT_TELEA)
            for b in bad:
                b["fallback_rect"] = 1
    return out, m


# ---------- 抽帧 ----------
_CAPS = {}


def grab(film, t):
    if film not in _CAPS:
        _CAPS[film] = cv2.VideoCapture(os.path.join(J, FILM_MP4[film]))
    cap = _CAPS[film]
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t * fps)))
    ok, im = cap.read()
    if not ok:
        raise RuntimeError(f"抽帧失败 {film} t={t}s")
    return cv2.resize(im, (W, H))


def t_of(kf):
    """'frame-96_170s.jpg' → 96.17 秒。
    ★ 坑：Python 3.6+ 的 float() 把下划线当数字分隔符，float('96_170')=96170.0 → 远超片长。
    """
    return float(kf.split("-")[1].split("s")[0].replace("_", "."))


def shots_of(film):
    return json.load(open(os.path.join(HERE, "shots_all.json"), encoding="utf-8"))[KEY[film]]


def build_list(kind):
    """返回 [(nm, film, t), ...]"""
    out = []
    for film in ("dy1", "dy2", "dy3"):
        for r in shots_of(film):
            nm = f"{film}_s{r['index']:03d}"
            if kind == "ref":
                t = t_of(r["kf"])
            elif kind == "first":
                t = r["start"] + 0.02
            else:
                t = r["end"] - 0.05
            out.append((nm, film, round(t, 3)))
    return out


def single(nm):
    film, sid = nm.split("_")
    idx = int(sid[1:])
    r = next(x for x in shots_of(film) if x["index"] == idx)
    t = t_of(r["kf"])
    print(f"{nm}: 镜 {idx}  t={t}s  ({r['start']}~{r['end']})  \"{r['line'][:22]}\"")
    img = grab(film, t)
    boxes = overlay_boxes(img)
    kinds = [b["kind"] for b in boxes]
    print(f"  叠加层块 {len(boxes)}: {[(b['kind'], b['y0'], b['y1'], b['x0'], b['x1']) for b in boxes]}")
    out, _ = scrub(img, boxes) if boxes else (img, None)
    tiles = []
    for tag, im in (("原片直抽", img), ("去叠加层", out)):
        c = im[420:1344].copy()
        for b in boxes:
            col = (0, 255, 0) if b["kind"] == "text" else (255, 128, 0)
            cv2.rectangle(c, (b["x0"] - 16, b["y0"] - 16 - 420),
                          (b["x1"] + 16, b["y1"] + 16 - 420), col, 2)
        cv2.putText(c, tag, (6, 18), cv2.FONT_HERSHEY_SIMPLEX, .55, (0, 255, 255), 2)
        tiles.append(cv2.resize(c, (400, 482)))
    cv2.imwrite(os.path.join(HERE, "_diag", f"REBUILD_{nm}.jpg"), np.hstack(tiles),
                [cv2.IMWRITE_JPEG_QUALITY, 94])
    print(f"-> _diag/REBUILD_{nm}.jpg  (绿框=文字, 橙框=箭头)")


def build_all(kind):
    outdir = {"ref": "full_ref2_v6", "first": "full_first6", "last": "full_last6"}[kind]
    outd = os.path.join(HERE, outdir)
    os.makedirs(outd, exist_ok=True)
    lst = build_list(kind)
    print(f"重抽+清洗 {len(lst)} 帧  kind={kind} → {outdir}/")
    stats = {"text": 0, "arrow": 0, "clean": 0, "none": 0}
    rows = []
    for i, (nm, film, t) in enumerate(lst):
        img = grab(film, t)
        boxes = overlay_boxes(img)
        if boxes:
            out, _ = scrub(img, boxes)
            stats["text"] += sum(1 for b in boxes if b["kind"] == "text") > 0
            stats["arrow"] += sum(1 for b in boxes if b["kind"] == "arrow") > 0
        else:
            out = img
            stats["none"] += 1
        cv2.imwrite(os.path.join(outd, nm + ".jpg"), out, [cv2.IMWRITE_JPEG_QUALITY, 95])
        rows.append(dict(nm=nm, t=t, boxes=[{k: b[k] for k in ("kind", "y0", "y1", "x0", "x1")} for b in boxes]))
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(lst)}", flush=True)
    json.dump(rows, open(os.path.join(HERE, "_diag", f"REBUILD_{kind}.json"), "w",
                         encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[✓] {len(lst)} 帧 → {outdir}/")
    print(f"    含字幕 {stats['text']}  含箭头 {stats['arrow']}  无叠加层 {stats['none']}")
    print(f"-> _diag/REBUILD_{kind}.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nm", default="")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--kind", default="ref", choices=["ref", "first", "last"])
    a = ap.parse_args()
    if a.all:
        build_all(a.kind)
    else:
        single(a.nm)


if __name__ == "__main__":
    main()
