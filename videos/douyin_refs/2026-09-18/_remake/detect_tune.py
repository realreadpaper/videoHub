#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文字检测调参台：把「带描边亮字」掩码可视化，人工确认后再批量跑。"""
import os, sys
import numpy as np
from PIL import Image

BASE = "/Users/jianglong/Desktop/videoHub/videos/douyin_refs/2026-09-18"

def dilate(m, r):
    out = m.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dy == 0 and dx == 0:
                continue
            out |= np.roll(np.roll(m, dy, 0), dx, 1)
    return out

def text_mask(a):
    lum = 0.299 * a[:, :, 0] + 0.587 * a[:, :, 1] + 0.114 * a[:, :, 2]
    sat = a.max(2) - a.min(2)
    dark = lum < 95
    bright = (lum > 158) | ((sat > 72) & (lum > 118))
    stroked = bright & dilate(dark, 4)
    return stroked, lum, sat

def zones_of(H, W):
    return [
        ("sub",    0.00, 1.00, 0.60, 0.96),
        ("stamp",  0.00, 0.30, 0.00, 0.08),
        ("ltitle", 0.00, 0.14, 0.00, 0.55),
        ("rtitle", 0.86, 1.00, 0.00, 0.55),
        ("wmk",    0.55, 1.00, 0.90, 1.00),
    ]

def find_hits(a, row_th=0.10, min_rows=3):
    H, W = a.shape[:2]
    m, lum, sat = text_mask(a)
    hits = []
    for name, x0, x1, y0, y1 in zones_of(H, W):
        sx0, sx1 = int(x0 * W), int(x1 * W)
        sy0, sy1 = int(y0 * H), int(y1 * H)
        sub = m[sy0:sy1, sx0:sx1]
        if sub.size == 0: continue
        rows = sub.mean(1)
        hot = rows > row_th
        # 最长连续段
        best = (0, 0, 0)
        i = 0
        while i < len(hot):
            if hot[i]:
                j = i
                while j + 1 < len(hot) and hot[j + 1]: j += 1
                if j - i + 1 > best[0]: best = (j - i + 1, i, j)
                i = j + 1
            else: i += 1
        if best[0] >= min_rows:
            ry0, ry1 = sy0 + best[1], sy0 + best[2] + 1
            cols = sub[best[1]:best[2] + 1].mean(0)
            hotc = cols > row_th * 0.5
            xs = np.where(hotc)[0]
            if len(xs) >= 2:
                rx0, rx1 = sx0 + int(xs.min()), sx0 + int(xs.max()) + 1
            else:
                rx0, rx1 = sx0, sx1
            # sub 区若宽度cover过半 → 认为是整行字幕
            pad_x = int(0.02 * W); pad_y = int(0.015 * H)
            hits.append(dict(zone=name,
                             box=[max(0, rx0 - pad_x), min(W, rx1 + pad_x),
                                  max(0, ry0 - pad_y), min(H, ry1 + pad_y)],
                             rows=int(best[0]),
                             dens=float(sub[best[1]:best[2] + 1].mean())))
    return hits, m

def main():
    dbg = f"{os.path.dirname(os.path.abspath(__file__))}/_scrub_dbg"
    os.makedirs(dbg, exist_ok=True)
    cases = [
        ("7661613126736204025", "frame-3_710s.jpg", "dy1s003"),   # 已知有字幕
        ("7664454812574337402", sys.argv[1] if len(sys.argv) > 1 else None, "dy3s001"),
        ("7661613126736204025", "frame-0_790s.jpg", "dy1s001"),
        ("7686341460064787045", None, "dy2s007"),
    ]
    # 从 shots_all 取每片第一个关键帧名
    import json
    rows = json.load(open(f"{os.path.dirname(os.path.abspath(__file__))}/shots_all.json", encoding="utf-8"))
    pick = {"dy1s001": ("7661613126736204025", rows["01_报恩"][0]["kf"]),
            "dy1s003": ("7661613126736204025", rows["01_报恩"][2]["kf"]),
            "dy2s007": ("7686341460064787045", rows["02_继母"][6]["kf"]),
            "dy3s001": ("7664454812574337402", rows["03_挑食"][0]["kf"]),
            "dy3s100": ("7664454812574337402", rows["03_挑食"][99]["kf"])}
    outs = []
    for label, (vid, kf) in pick.items():
        p = f"{BASE}/{vid}/keyframes/{kf}"
        img = Image.open(p).convert("RGB")
        a = np.asarray(img, dtype=np.float32)
        hits, m = find_hits(a)
        # 可视化：掩码染红叠加
        vis = a.copy()
        vis[m] = [255, 0, 0]
        for h in hits:
            x0, x1, y0, y1 = h["box"]
            vis[y0:max(y0 + 3, y0), x0:x1] = [0, 255, 0]
            vis[max(0, y1 - 3):y1, x0:x1] = [0, 255, 0]
            vis[y0:y1, x0:max(x0 + 3, x0)] = [0, 255, 0]
            vis[y0:y1, max(0, x1 - 3):x1] = [0, 255, 0]
        out = Image.fromarray(np.clip(vis, 0, 255).astype(np.uint8))
        out = out.resize((out.width // 2, out.height // 2))
        out.save(f"{dbg}/DET_{label}.jpg", quality=85)
        outs.append(f"{dbg}/DET_{label}.jpg")
        print(f"{label} {kf}: hits={[(h['zone'], h['box'], h['rows'], round(h['dens'],3)) for h in hits]}")
        print(f"   mask像素占比 {m.mean()*100:.2f}%")
    # 横向拼图
    ims = [Image.open(o) for o in outs]
    W = sum(i.width for i in ims); H = max(i.height for i in ims)
    sheet = Image.new("RGB", (W, H), (20, 20, 20))
    x = 0
    for i in ims:
        sheet.paste(i, (x, 0)); x += i.width
    sheet.save(f"{dbg}/DET_sheet.jpg", quality=86)
    print("sheet:", f"{dbg}/DET_sheet.jpg")

if __name__ == "__main__":
    main()
