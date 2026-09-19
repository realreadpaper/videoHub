#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""参考帧 v4：为 Hybrid 双端锁定准备「镜头首帧 + 镜头末帧」。

实测：只钉首帧（first_frame）挡不住推镜——wide 镜在 0.5s 内就被推成一张脸。
把**首、尾两帧都钉成原片对应帧**后，模型被夹在中间，无法推近，构图被双向锁死。

产出：
  full_first4/{nm}.jpg  镜头 start+0.05s 的帧（清洗后，768x1344）
  full_last4/{nm}.jpg   镜头 end-0.05s  的帧（清洗后，768x1344）
ref_images 继续用 v3 的「最干净候选帧」。
"""
import os, json, sys, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prep_refs_v2 import grab, score_frame, FILMS, to_canvas  # noqa
from prep_refs_v3 import scrub_v3  # noqa
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "/Users/jianglong/Desktop/videoHub/videos/douyin_refs/2026-09-18"

_ap = argparse.ArgumentParser()
_ap.add_argument("--shard", type=int, default=0)
_ap.add_argument("--nshards", type=int, default=1)
ARGS = _ap.parse_args()

OUT_F = f"{HERE}/full_first4"
OUT_L = f"{HERE}/full_last4"
TMP = "/tmp/_rl4"
INSET = 0.05


def process(img, s, hits_full):
    """hits 是在降采样图上的；这里给全尺寸坐标"""
    return scrub_v3(img, [dict(h, box=[v / s for v in h["box"]]) for h in hits_full], 1.0)


def main():
    for d in (OUT_F, OUT_L, TMP):
        os.makedirs(d, exist_ok=True)
    rows = json.load(open(f"{HERE}/shots_all.json", encoding="utf-8"))
    n = 0
    for film, lst in rows.items():
        tag, vid = FILMS[film]
        mp4 = f"{BASE}/{vid}.mp4"
        for gi, r in enumerate(lst):
            if gi % ARGS.nshards != ARGS.shard:
                continue
            nm = f"{tag}_s{r['index']:03d}"
            for lab, t in (("first", r["start"] + INSET), ("last", r["end"] - INSET)):
                t = min(max(t, r["start"] + 0.02), max(r["start"] + 0.02, r["end"] - 0.03))
                p = f"{TMP}/{nm}_{lab}.jpg"
                if not grab(mp4, t, p):
                    continue
                sc, hits, img, s = score_frame(p)
                clean, _, _ = process(img, s, hits)
                out = OUT_F if lab == "first" else OUT_L
                to_canvas(clean).save(f"{out}/{nm}.jpg", quality=95)
    for d in (OUT_F, OUT_L):
        print(f"[✓][shard {ARGS.shard}] {d}: {len(os.listdir(d))} 帧", flush=True)


if __name__ == "__main__":
    main()
