#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""判定「生成片底部烧字幕」的根因：参考帧残留 vs 模型幻觉。

对每个镜：
  A) 清洗后参考帧 full_ref2_v3/<nm>.jpg  → 量字幕带(y 870-1010)文字能量
  B) 生成片 _six/gen/<nm>.mp4 的多帧     → 同带同指标
  C) 若 A 干净而 B 有字 → 模型幻觉；A 也有字 → 参考帧泄漏（清洗不净）

指标：
  edge   = mean|Laplacian|（文字必然抬高局部梯度）
  yellow = 黄字像素占比（R>150,G>120,B<110,R-B>60；抖音字幕常见黄字黑边）
  ctrl   = 对照带（y 1150-1280，通常纯背景）作基线
"""
import os, sys, json, glob
import numpy as np
import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
SHOTS = ["dy1_s093", "dy1_s088", "dy2_s118", "dy2_s075", "dy3_s145", "dy3_s119"]
H, W = 1344, 768
BAND_SUB = (870, 1010)      # 字幕带
BAND_CTRL = (1150, 1290)    # 对照带


def metrics(img):
    out = {}
    for tag, (y0, y1) in (("sub", BAND_SUB), ("ctrl", BAND_CTRL)):
        band = img[y0:y1]
        gray = cv2.cvtColor(band, cv2.COLOR_BGR2GRAY)
        lap = cv2.Laplacian(gray, cv2.CV_32F, ksize=3)
        b, g, r = band[:, :, 0].astype(np.int16), band[:, :, 1].astype(np.int16), band[:, :, 2].astype(np.int16)
        yellow = ((r > 150) & (g > 120) & (b < 110) & ((r - b) > 60)).mean() * 100
        out[tag] = dict(edge=round(float(np.abs(lap).mean()), 2),
                        yellow=round(float(yellow), 3))
    out["text_score"] = round(out["sub"]["edge"] / max(out["ctrl"]["edge"], 1e-6), 2)
    return out


def frames_from_mp4(path, n=7):
    cap = cv2.VideoCapture(path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    idxs = np.linspace(0, total - 1, n).astype(int)
    got = []
    for i in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ok, fr = cap.read()
        if ok:
            if fr.shape[:2] != (H, W):
                fr = cv2.resize(fr, (W, H))
            got.append(fr)
    cap.release()
    return got


rows = []
for nm in SHOTS:
    ref_p = os.path.join(HERE, "full_ref2_v3", nm + ".jpg")
    ref = cv2.imread(ref_p)
    if ref is None:
        rows.append(dict(nm=nm, err="no ref")); continue
    if ref.shape[:2] != (H, W):
        ref = cv2.resize(ref, (W, H))
    ref_m = metrics(ref)

    gen_p = os.path.join(HERE, "_six", "gen", nm + ".mp4")
    gf = frames_from_mp4(gen_p)
    gm = [metrics(f) for f in gf]
    # 取「字幕能量最强」的那一帧（若整个片子无字，各帧应一致低）
    worst = max(gm, key=lambda m: m["sub"]["edge"]) if gm else {}
    avg_yellow = round(float(np.mean([m["sub"]["yellow"] for m in gm])), 3) if gm else 0

    rows.append(dict(
        nm=nm,
        ref_sub_edge=ref_m["sub"]["edge"], ref_sub_yellow=ref_m["sub"]["yellow"],
        ref_ctrl_edge=ref_m["ctrl"]["edge"], ref_score=ref_m["text_score"],
        gen_sub_edge=worst.get("sub", {}).get("edge"), gen_sub_yellow=worst.get("sub", {}).get("yellow"),
        gen_ctrl_edge=worst.get("ctrl", {}).get("edge"), gen_score=worst.get("text_score"),
        gen_yellow_avg=avg_yellow,
    ))

hdr = f"{'shot':10s} | {'ref edge':>8s} {'ref yel%':>8s} {'ref r':>6s} | {'gen edge':>8s} {'gen yel%':>8s} {'gen r':>6s} | {'yelavg':>7s}"
print(hdr); print("-" * len(hdr))
for r in rows:
    if r.get("err"):
        print(f"{r['nm']:10s} | {r['err']}"); continue
    print(f"{r['nm']:10s} | {r['ref_sub_edge']:8.2f} {r['ref_sub_yellow']:8.3f} {r['ref_score']:6.2f} | "
          f"{r['gen_sub_edge']:8.2f} {r['gen_sub_yellow']:8.3f} {r['gen_score']:6.2f} | {r['gen_yellow_avg']:7.3f}")

json.dump(rows, open(os.path.join(HERE, "_diag", "BANDCHECK.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("\n-> _diag/BANDCHECK.json")

# 拼一条目视带：左=参考帧字幕带，右=生成片字幕带（各镜一行）
tiles = []
for nm in SHOTS:
    ref = cv2.imread(os.path.join(HERE, "full_ref2_v3", nm + ".jpg"))
    gf = frames_from_mp4(os.path.join(HERE, "_six", "gen", nm + ".mp4"), 3)
    if ref is None or not gf:
        continue
    if ref.shape[:2] != (H, W):
        ref = cv2.resize(ref, (W, H))
    row = [ref[BAND_SUB[0]:BAND_SUB[1]], cv2.resize(gf[len(gf) // 2], (W, H))[BAND_SUB[0]:BAND_SUB[1]]]
    row = [cv2.resize(x, (560, 100)) for x in row]
    tiles.append(np.hstack(row))
if tiles:
    strip = np.vstack(tiles)
    cv2.imwrite(os.path.join(HERE, "_diag", "BANDSTRIP.jpg"), strip, [cv2.IMWRITE_JPEG_QUALITY, 92])
    print("-> _diag/BANDSTRIP.jpg")
