#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""参考帧 v3：逐像素文字掩码 + OpenCV 修复（替代 v2 的整块模糊）。

v2 的问题：检出框内整块模糊 → 画面底部出现一大块灰糊，构图被毁。
v3 只补「文字笔画 + 它的深色描边」这些像素，背景纹理原样保留。
"""
import os, json, subprocess, sys, argparse
import numpy as np, cv2
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "/Users/jianglong/Desktop/videoHub/videos/douyin_refs/2026-09-18"
FF = "/usr/local/bin/ffmpeg"
sys.path.insert(0, HERE)
from detect_tune import find_hits  # noqa: E402
from prep_refs_v2 import grab, score_frame, CANDS, CROP_BOTTOM, to_canvas, FILMS  # noqa

_ap = argparse.ArgumentParser()
_ap.add_argument("--shard", type=int, default=0)
_ap.add_argument("--nshards", type=int, default=1)
_ap.add_argument("--suffix", default="_v3")
ARGS = _ap.parse_args()
SFX = ARGS.suffix
OUT_SRC = f"{HERE}/scrub_src{SFX}"
OUT_REF = f"{HERE}/full_ref2{SFX}"
OUT_FIRST = f"{HERE}/full_first{SFX}"
TMP = f"/tmp/_refcand3"
K5 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))


def stroke_mask(a, boxes):
    """在给定框内取「亮字/彩字 + 其深描边」的像素掩码"""
    lum = 0.299 * a[:, :, 0] + 0.587 * a[:, :, 1] + 0.114 * a[:, :, 2]
    sat = a.max(2) - a.min(2)
    dark = (lum < 105).astype(np.uint8)
    bright = ((lum > 152) | ((sat > 68) & (lum > 112))).astype(np.uint8)
    dark_d = cv2.dilate(dark, K5, iterations=2)
    bright_d = cv2.dilate(bright, K5, iterations=2)
    m = (((bright & dark_d) | (dark & bright_d)) * 255).astype(np.uint8)
    # 只在检出框附近生效，避免误伤
    keep = np.zeros_like(m)
    H, W = m.shape
    for x0, x1, y0, y1 in boxes:
        x0, x1 = max(0, int(x0) - 8), min(W, int(x1) + 8)
        y0, y1 = max(0, int(y0) - 8), min(H, int(y1) + 8)
        keep[y0:y1, x0:x1] = 255
    return cv2.bitwise_and(m, keep)


def scrub_v3(img, hits, s):
    if not hits:
        return img, 0, 0.0
    a = np.asarray(img.convert("RGB"))
    boxes = [[v / s for v in h["box"]] for h in hits]
    m = stroke_mask(a.astype(np.float32), boxes)
    m = cv2.dilate(m, K5, iterations=2)
    frac = float((m > 0).mean())
    if frac < 1e-5:
        return img, 0, 0.0
    bgr = cv2.cvtColor(a, cv2.COLOR_RGB2BGR)
    out = cv2.inpaint(bgr, m, 3, cv2.INPAINT_NS)
    out = cv2.cvtColor(out, cv2.COLOR_BGR2RGB)
    return Image.fromarray(out), len(hits), frac


def main():
    for d in (OUT_SRC, OUT_REF, OUT_FIRST, TMP):
        os.makedirs(d, exist_ok=True)
    rows = json.load(open(f"{HERE}/shots_all.json", encoding="utf-8"))
    report = {}
    tot = clean_first = fixed = 0
    for film, lst in rows.items():
        tag, vid = FILMS[film]
        mp4 = f"{BASE}/{vid}.mp4"
        rep = []
        for gi, r in enumerate(lst):
            if gi % ARGS.nshards != ARGS.shard:
                continue
            nm = f"{tag}_s{r['index']:03d}"
            best = None
            for frac_c, label in CANDS:
                t = r["start"] + r["dur"] * frac_c
                t = min(max(t, r["start"] + 0.02), r["end"] - 0.03)
                cpath = f"{TMP}/{nm}_{label}.jpg"
                if not grab(mp4, t, cpath):
                    continue
                sc, hits, img, s = score_frame(cpath)
                if best is None or sc < best[0]:
                    best = (sc, hits, img, s, label, t)
                if sc == 0:
                    break
            if best is None:
                continue
            sc, hits, img, s, label, t = best
            tot += 1
            clean, n, frac = scrub_v3(img, hits, s)
            clean.save(f"{OUT_SRC}/{nm}.jpg", quality=95)
            c = to_canvas(clean)
            c.save(f"{OUT_REF}/{nm}.jpg", quality=95)
            c.save(f"{OUT_FIRST}/{nm}.jpg", quality=95)
            if sc == 0:
                clean_first += 1
            else:
                fixed += 1
            rep.append(dict(nm=nm, t=round(t, 3), pick=label, score=round(sc, 4),
                            zones=[h["zone"] for h in hits], mask_pct=round(frac * 100, 3)))
        report[film] = rep
        print(f"[{film}] {len(rep)} 镜（{sum(1 for x in rep if x['score']==0)} 镜原生干净）", flush=True)
    json.dump(report, open(f"{HERE}/_ref_report{SFX}_{ARGS.shard}.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"[✓][shard {ARGS.shard}] {tot} 镜：原生干净 {clean_first}，修复 {fixed}", flush=True)


if __name__ == "__main__":
    main()
