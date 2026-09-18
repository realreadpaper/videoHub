#!/usr/bin/env python3
"""按帧号区间拼接触表（用于重点段加密观察）。"""
import sys, os, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _sheet import sheet

d, outdir, step, cols = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
lo, hi = int(sys.argv[5]), int(sys.argv[6])
per = int(sys.argv[7]) if len(sys.argv) > 7 else 18
tag = sys.argv[8] if len(sys.argv) > 8 else "seg"

files = sorted(glob.glob(os.path.join(d, "*.jpg")))
sub = [f for f in files
       if lo <= int(os.path.basename(f).split("_")[1].split(".")[0]) <= hi]
os.makedirs(outdir, exist_ok=True)
for i in range(0, len(sub), per):
    sheet(sub[i:i + per], cols, os.path.join(outdir, f"sheet_{tag}_{i // per + 1}.jpg"), step)
