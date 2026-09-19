#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验收：把某一批参考帧拼成网格图，供**目视**确认叠加层是否清干净。

★ 教训：本项目所有"只靠数值指标验收"的环节都翻过车（黄黑涂抹被判为"已清洗"），
  验收标准必须是「目视整批网格 + 逐帧放大抽查」。
用法: python verify_grid.py --dir full_ref2_v6 [--cols 10]
"""
import argparse
import glob
import json
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TW, TH = 96, 168          # 单格尺寸


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="full_ref2_v6")
    ap.add_argument("--cols", type=int, default=10)
    ap.add_argument("--per", type=int, default=93, help="每张网格放多少帧")
    a = ap.parse_args()
    files = sorted(glob.glob(os.path.join(HERE, a.dir, "*.jpg")))
    print(f"{len(files)} 帧  {a.dir}")
    pages = [files[i:i + a.per] for i in range(0, len(files), a.per)]
    for pi, page in enumerate(pages):
        tiles = []
        for p in page:
            im = cv2.imread(p)
            if im is None:
                continue
            t = cv2.resize(im, (TW, TH))
            nm = os.path.basename(p)[:-4]
            cv2.putText(t, nm, (2, 11), cv2.FONT_HERSHEY_SIMPLEX, .3, (0, 255, 255), 1)
            tiles.append(t)
        while len(tiles) % a.cols:
            tiles.append(np.zeros((TH, TW, 3), np.uint8))
        rows = [np.hstack(tiles[i:i + a.cols]) for i in range(0, len(tiles), a.cols)]
        g = np.vstack(rows)
        out = os.path.join(HERE, "_diag", f"GRID_{a.dir}_{pi+1}.jpg")
        cv2.imwrite(out, g, [cv2.IMWRITE_JPEG_QUALITY, 90])
        print(f"  -> {out}  {g.shape}  ({len(page)} 帧)")
    # 叠加层统计
    jf = os.path.join(HERE, "_diag", "REBUILD_ref.json")
    if os.path.exists(jf):
        rows = json.load(open(jf, encoding="utf-8"))
        n = len(rows)
        nt = sum(1 for r in rows if any(b["kind"] == "text" for b in r["boxes"]))
        na = sum(1 for r in rows if any(b["kind"] == "arrow" for b in r["boxes"]))
        n0 = sum(1 for r in rows if not r["boxes"])
        print(f"\n统计: {n} 帧  含文字块 {nt}  含箭头 {na}  未见叠加层 {n0}")


if __name__ == "__main__":
    main()
