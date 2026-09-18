#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""禁字检测判据标定：用已人工核实的正/负样本，找能分开「真字幕条」与「纹理假行」的特征。

正样本 = _review/calib/pos/*.jpg   （成片里确实有乱码字幕条的帧）
负样本 = _review/calib/neg/*.jpg   （已人工确认为干净的帧，曾被旧判据误报）
"""
import csv, glob, io, os, subprocess, sys, tempfile
from PIL import Image, ImageOps
import numpy as np

UPSCALE = 1.6
# 字幕带候选区（画面纵向比例）。实测字幕条固定在约 72–80%。
BAND = (0.62, 0.92)


def load_band(path, band=BAND):
    im = Image.open(path).convert("L")
    w, h = im.size
    im = im.resize((int(w * UPSCALE), int(h * UPSCALE)), Image.LANCZOS)
    im = ImageOps.autocontrast(im, cutoff=1)
    W, H = im.size
    return im.crop((0, int(H * band[0]), W, int(H * band[1]))), im


def tokens(im, conf_thr=20):
    tmp = tempfile.mktemp(suffix=".png"); im.save(tmp)
    r = subprocess.run(["tesseract", tmp, "stdout", "-l", "eng+chi_sim", "--psm", "11", "tsv"],
                       capture_output=True, text=True)
    os.unlink(tmp)
    out = []
    for d in csv.DictReader(io.StringIO(r.stdout), delimiter="\t"):
        try: c = float(d.get("conf") or -1)
        except Exception: continue
        t = (d.get("text") or "").strip()
        if c < conf_thr or not t: continue
        try: L,T,Wd,Hd = int(d["left"]),int(d["top"]),int(d["width"]),int(d["height"])
        except Exception: continue
        if Hd < 6: continue
        out.append({"t": t, "conf": c, "left": L, "top": T, "w": Wd, "h": Hd})
    return out


def feats(path):
    band, full = load_band(path)
    bw, bh = band.size
    toks = tokens(band)
    # 只看足够"像字"的 token
    big = [x for x in toks if len(x["t"]) >= 1]
    if not big:
        return dict(name=os.path.basename(path), n=0, chars=0, xspan=0, hcv=0, gapcv=0,
                    conf=0, dens=0, region="")
    big.sort(key=lambda x: x["left"])
    hs = np.array([x["h"] for x in big], float)
    gaps = np.diff([x["left"] for x in big]) if len(big) > 1 else np.array([0.0])
    x0 = big[0]["left"]; x1 = big[-1]["left"] + big[-1]["w"]
    # 纵向位置（换算回全图比例）
    ytop = band.crop((0,0,1,1))  # placeholder
    Hh = full.size[1]
    y_at = BAND[0] + (np.mean([x["top"] for x in big]) / bh) * (BAND[1] - BAND[0])
    return dict(
        name=os.path.basename(path),
        n=len(big),
        chars=sum(len(x["t"]) for x in big),
        xspan=round((x1 - x0) / bw, 3),
        hcv=round(float(hs.std() / max(hs.mean(), 1)), 3),
        gapcv=round(float(gaps.std() / max(gaps.mean(), 1)) if len(gaps) > 1 else 9.9, 3),
        conf=round(float(np.mean([x["conf"] for x in big])), 1),
        y=round(float(y_at), 3),
    )


def main():
    for tag, pat in (("POS", "_review/calib/pos/*.jpg"), ("NEG", "_review/calib/neg/*.jpg")):
        print("\n===== %s =====" % tag)
        print("%-22s %3s %5s %6s %6s %6s %6s" % ("file", "n", "chars", "xspan", "hCV", "gapCV", "conf"))
        rows = []
        for p in sorted(glob.glob(pat)):
            f = feats(p); rows.append(f)
            print("%-22s %3d %5d %6.3f %6.3f %6.3f %6.1f" % (
                f["name"][:21], f["n"], f["chars"], f["xspan"], f["hcv"], f["gapcv"], f["conf"]))
        if rows:
            import statistics as st
            for k in ("n", "chars", "xspan", "hcv", "gapcv", "conf"):
                v = [r[k] for r in rows]
                print("  %s: min %.2f med %.2f max %.2f" % (k, min(v), st.median(v), max(v)))


if __name__ == "__main__":
    main()
