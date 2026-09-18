#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
detect_hardcut.py —— 镜内硬切（跳帧）检测器 · v4 判据

为什么改判据
------------
旧判据 `帧差 > max(5.0, 中位 + 4σ)` 在运动强度低的片子上够用，但在
「连续运镜」prompt 生成的片子上**必然误报**：整片帧差中位被抬高（6.4 vs 5.1），
σ 也随之变大，正常的速度起伏就会越线。

实测反例（01《三十八万八》镜01）：

    v2 三段式 prompt   峰值 54.2 / 邻域 4.4   = 13.4 倍   ← 真硬切
    v2 三段式 prompt   峰值 72.2 / 邻域 1.5   = 36.2 倍   ← 真硬切
    v3 单镜连续 prompt 峰值 14.9 / 邻域 10.3  =  1.6 倍   ← 只是运镜快了
    v3 单镜连续 prompt 峰值 13.4 / 邻域  8.8  =  1.6 倍   ← 只是运镜快了

硬切的物理特征是**孤立单帧突变**：相邻帧只差 1~2 的「静」与跳变前后
无连续性；连续运镜则是**渐变**——峰值前后邻域本身就处于高位。
所以判据取「峰值 ÷ 邻域中位」，而不是绝对阈值。

判据
----
    ratio = peak / median(邻域帧差)         邻域 = 峰值前后各 5 帧（不含峰值）
    ratio >= 3.0  →  硬切（孤立突变，画面被整帧替换）
    1.8 <= ratio < 3.0  →  存疑（快速甩镜/遮挡切换，需人眼确认）
    ratio < 1.8   →  正常运镜

参考基准：实拍 24fps 正常运镜 ratio 通常 1.0~1.8；真硬切 ratio ≥ 8。

用法
----
  python3 detect_hardcut.py shots/*.mp4
  python3 detect_hardcut.py film.mp4 --json report.json
  python3 detect_hardcut.py dir/ --quiet
"""

import argparse
import glob
import json
import os
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

FFMPEG = "ffmpeg"
NEIGH = 5          # 峰值前后各取多少帧作为邻域
RATIO_CUT = 3.0    # ≥ 此倍数判为硬切
RATIO_SUS = 1.8    # ≥ 此倍数判为存疑


def frames_of(path, width=336, height=192, fps=24):
    """抽帧为灰度小图（够算位移，又够快）。"""
    d = tempfile.mkdtemp(prefix="hc_")
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", path,
                    "-vf", "fps=%d,scale=%d:%d" % (fps, width, height),
                    os.path.join(d, "%04d.png")], capture_output=True)
    fs = sorted(glob.glob(os.path.join(d, "*.png")))
    out = [np.asarray(Image.open(f).convert("L"), dtype=np.float32) for f in fs]
    for f in fs:
        os.remove(f)
    os.rmdir(d)
    return out, fps


def analyze(path, fps=24):
    F, fps = frames_of(path, fps=fps)
    if len(F) < 4:
        return None
    d = np.array([np.abs(F[i] - F[i - 1]).mean() for i in range(1, len(F))])
    med = float(np.median(d))

    events = []
    for i in range(1, len(d) - 1):
        v = d[i]
        if v < 3.0:                       # 绝对量太小，不可能是硬切
            continue
        lo = max(0, i - NEIGH)
        hi = min(len(d), i + NEIGH + 1)
        nb = np.concatenate([d[lo:i], d[i + 1:hi]])
        if len(nb) == 0:
            continue
        base = float(np.median(nb))
        # 邻域为「静」时（base 很小）用绝对量兜底，避免除零放大噪声
        ratio = v / base if base > 0.5 else v / 0.5
        if ratio >= RATIO_CUT:
            events.append({"frame": i + 1, "sec": round((i + 1) / fps, 2),
                           "peak": round(float(v), 2), "base": round(base, 2),
                           "ratio": round(float(ratio), 2), "kind": "cut"})
        elif ratio >= RATIO_SUS:
            events.append({"frame": i + 1, "sec": round((i + 1) / fps, 2),
                           "peak": round(float(v), 2), "base": round(base, 2),
                           "ratio": round(float(ratio), 2), "kind": "suspect"})

    # 合并相邻帧的同一事件
    merged = []
    for e in events:
        if merged and e["frame"] - merged[-1]["frame"] <= 2:
            if e["peak"] > merged[-1]["peak"]:
                merged[-1] = e
            continue
        merged.append(e)

    return {"file": os.path.basename(path), "frames": len(F),
            "median": round(med, 2), "max": round(float(d.max()), 2),
            "events": merged,
            "cuts": sum(1 for e in merged if e["kind"] == "cut"),
            "suspects": sum(1 for e in merged if e["kind"] == "suspect")}


def collect(targets):
    files = []
    for t in targets:
        if os.path.isdir(t):
            files += sorted(glob.glob(os.path.join(t, "*.mp4")))
        else:
            files += sorted(glob.glob(t)) or ([t] if os.path.exists(t) else [])
    return files


def main():
    ap = argparse.ArgumentParser(description="镜内硬切检测 · 峰值/邻域比判据 v4")
    ap.add_argument("targets", nargs="+", help="mp4 文件、通配符或目录")
    ap.add_argument("--json", default=None, help="把结果写到 json")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    files = collect(a.targets)
    if not files:
        print("✘ 没有匹配的文件"); return 1

    print("硬切检测 v4 | 判据: 峰值÷邻域中位 ≥ %.1f 判硬切, ≥ %.1f 判存疑 (邻域±%d帧)"
          % (RATIO_CUT, RATIO_SUS, NEIGH))
    print("=" * 96)
    if not a.quiet:
        print("%-30s %6s %8s %8s %6s %6s  %s" % ("文件", "帧数", "中位MAE", "最大MAE", "硬切", "存疑", "位置(秒 | 峰值 | 比)"))
        print("-" * 96)

    results = []
    tc = ts = 0
    for f in files:
        r = analyze(f)
        if not r:
            print("  ⚠ %s 帧数不足，跳过" % f); continue
        results.append(r)
        tc += r["cuts"]; ts += r["suspects"]
        if not a.quiet:
            pos = ", ".join("%.2fs|%.0f|%.1fx%s" % (e["sec"], e["peak"], e["ratio"],
                                                    "" if e["kind"] == "cut" else "?")
                            for e in r["events"][:6])
            mark = "✘" if r["cuts"] else ("?" if r["suspects"] else "✔")
            print("%-30s %6d %8.2f %8.2f %6d %6d  %s %s" % (
                r["file"], r["frames"], r["median"], r["max"],
                r["cuts"], r["suspects"], mark, pos or "—"))
    print("-" * 96)
    print("合计: 硬切 %d 处, 存疑 %d 处, 共 %d 个文件" % (tc, ts, len(results)))

    if a.json:
        json.dump(results, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("✔ 已写出 %s" % a.json)
    return 1 if tc else 0


if __name__ == "__main__":
    sys.exit(main())
