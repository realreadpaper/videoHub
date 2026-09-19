#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""参考帧 v2：多帧候选 + 文字清洗。

原片关键帧里带三类文字，实测都会被 H3 抄进新片：
  1. 底部大字幕（y≈66–73%，旧脚本只裁底部 10% 根本裁不到）
  2. 左上时间戳
  3. 左缘竖排角色标题（挑食片「顾婉宁女儿」）
做法：
  · 每镜取 3 个候选时刻（镜头起始 / 中段 / 末尾前）→ 检测文字量 → 选最干净的一帧
  · 若最干净帧仍有文字 → 只对检出块做重度模糊 + 去饱和
  · 输出 768x1344 两份：full_ref2（ref_images）、full_first（first_frame）
"""
import os, json, subprocess, sys, argparse
import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "/Users/jianglong/Desktop/videoHub/videos/douyin_refs/2026-09-18"
FF = "/usr/local/bin/ffmpeg"
sys.path.insert(0, HERE)
from detect_tune import find_hits  # noqa: E402

_ap = argparse.ArgumentParser()
_ap.add_argument("--shard", type=int, default=0)
_ap.add_argument("--nshards", type=int, default=1)
_ap.add_argument("--suffix", default="")
ARGS = _ap.parse_args()

FILMS = {"01_报恩": ("dy1", "7661613126736204025"),
         "02_继母": ("dy2", "7686341460064787045"),
         "03_挑食": ("dy3", "7664454812574337402")}

SFX = ARGS.suffix
OUT_SRC = f"{HERE}/scrub_src{SFX}"
OUT_REF = f"{HERE}/full_ref2{SFX}"
OUT_FIRST = f"{HERE}/full_first{SFX}"
TMP = f"/tmp/_refcand{SFX}"

CROP_BOTTOM = 0.90          # 保留上方 90%（切掉底部互动条/水印行）
CANDS = ((0.04, "head"), (0.5, "mid"), (0.92, "tail"))


def grab(mp4, t, out):
    os.makedirs(os.path.dirname(out), exist_ok=True)
    r = subprocess.run([FF, "-v", "error", "-y", "-ss", f"{max(0.0, t):.3f}",
                        "-i", mp4, "-frames:v", "1", "-q:v", "2", out],
                       capture_output=True)
    return r.returncode == 0 and os.path.exists(out)


def score_frame(path, small_w=540):
    """返回 (总分, 检出块列表)。分越高文字越多。"""
    img = Image.open(path).convert("RGB")
    s = small_w / img.width
    small = img.resize((small_w, max(1, round(img.height * s))), Image.BILINEAR)
    hits, _ = find_hits(np.asarray(small, dtype=np.float32))
    W = { "sub": 1.0, "ltitle": 0.8, "rtitle": 0.8, "stamp": 0.5, "wmk": 0.5 }
    total = sum(h["dens"] * W.get(h["zone"], 0.5) for h in hits)
    return total, hits, img, s


def scrub(img, hits):
    if not hits:
        return img, 0
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    H, W = a.shape[:2]
    out = a.copy()
    for h in hits:
        x0, x1, y0, y1 = [int(round(v)) for v in h["box"]]
        ex = int((x1 - x0) * 0.6); ey = int((y1 - y0) * 2.0)
        cx0, cx1 = max(0, x0 - ex), min(W, x1 + ex)
        cy0, cy1 = max(0, y0 - ey), min(H, y1 + ey)
        reg = Image.fromarray(a[cy0:cy1, cx0:cx1].astype(np.uint8))
        r = max(10, int((y1 - y0) * 0.75))
        # 降采样→小半径模糊→升采样：等效大半径高斯，但快两个数量级
        k = max(4, r // 4)
        rw, rh = max(1, reg.width // k), max(1, reg.height // k)
        b = np.asarray(reg.resize((rw, rh), Image.BILINEAR)
                       .filter(ImageFilter.GaussianBlur(max(2, r // k)))
                       .resize((reg.width, reg.height), Image.BICUBIC), dtype=np.float32)
        m = b.mean(2, keepdims=True)
        out[cy0:cy1, cx0:cx1] = 0.30 * b + 0.70 * m
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)), len(hits)


def to_canvas(img):
    H, W = img.height, img.width
    img = img.crop((0, 0, W, int(H * CROP_BOTTOM)))
    tw, th = 768, 1344
    s = max(tw / img.width, th / img.height)
    img = img.resize((max(1, round(img.width * s)), max(1, round(img.height * s))), Image.LANCZOS)
    l, t = (img.width - tw) // 2, (img.height - th) // 2
    return img.crop((l, t, l + tw, t + th))


def main():
    for d in (OUT_SRC, OUT_REF, OUT_FIRST, TMP):
        os.makedirs(d, exist_ok=True)
    rows = json.load(open(f"{HERE}/shots_all.json", encoding="utf-8"))
    report = {}
    tot = clean_first = scrubbed = 0
    for film, lst in rows.items():
        tag, vid = FILMS[film]
        mp4 = f"{BASE}/{vid}.mp4"
        rep = []
        for gi, r in enumerate(lst):
            if gi % ARGS.nshards != ARGS.shard:
                continue
            nm = f"{tag}_s{r['index']:03d}"
            best = None
            for frac, label in CANDS:
                t = r["start"] + r["dur"] * frac
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
                print(f"  ✗ 取帧失败 {nm}"); continue
            sc, hits_small, img, s, label, t = best
            tot += 1
            # 把小图坐标放大回原图
            hits = [dict(h, box=[v / s for v in h["box"]]) for h in hits_small]
            clean, n = scrub(img, hits)
            clean.save(f"{OUT_SRC}/{nm}.jpg", quality=95)
            c = to_canvas(clean)
            c.save(f"{OUT_REF}/{nm}.jpg", quality=95)
            c.save(f"{OUT_FIRST}/{nm}.jpg", quality=95)
            if sc == 0:
                clean_first += 1
            else:
                scrubbed += 1
            rep.append(dict(nm=nm, t=round(t, 3), pick=label, score=round(sc, 4),
                            zones=[h["zone"] for h in hits_small]))
        report[film] = rep
        n0 = sum(1 for x in rep if x["score"] == 0)
        print(f"[{film}] {len(rep)} 镜：{n0} 镜选到无文字帧，{len(rep)-n0} 镜需掩蔽"
              f"（平均文字分 {np.mean([x['score'] for x in rep]):.4f}）")
    json.dump(report, open(f"{HERE}/_ref_report{SFX}_{ARGS.shard}.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\n[✓][shard {ARGS.shard}/{ARGS.nshards}] {tot} 镜：{clean_first} 镜原生干净"
          f"（{clean_first/max(1,tot)*100:.0f}%），{scrubbed} 镜掩蔽后干净")


if __name__ == "__main__":
    main()
