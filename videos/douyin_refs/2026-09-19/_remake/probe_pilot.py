#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
试拍客观体检：不靠肉眼，用指标回答四个问题。

  Q1 首帧/末帧有没有被 first_frame / last_frame 锁住？
  Q2 产品镜里到底有没有出现"产品包装"（深红 #A82128 族）？占多大？
  Q3 复刻音轨与原片是否同源（响度/时长）？
  Q4 4.458 秒里画面到底动了没有（相邻静帧差），会不会"演完就僵住"？

用法: <带 PIL+numpy 的 python> probe_pilot.py
"""
import json
import os
import subprocess
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
PILOT = os.path.join(HERE, "pilot")
OUT = os.path.join(PILOT, "out")
TMP = os.path.join(OUT, "_probe")
BASE = os.path.dirname(HERE)
KEY = "kehu"

SZ = (96, 168)          # 统一比较尺寸（宽, 高）


def run(cmd, check=True):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError("FAILED: %s\n%s" % (" ".join(cmd), r.stderr[-500:]))
    return r


def frame_at(src, t, dst):
    run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "%.4f" % t, "-i", src,
         "-frames:v", "1", "-vf", "scale=%d:%d" % SZ, "-q:v", "2", dst])
    return np.asarray(Image.open(dst).convert("RGB"), dtype=np.float32)


def gray(a):
    return a @ np.array([0.299, 0.587, 0.114], dtype=np.float32)


def hist_corr(a, b):
    ha, _ = np.histogram(gray(a).ravel(), bins=32, range=(0, 255), density=True)
    hb, _ = np.histogram(gray(b).ravel(), bins=32, range=(0, 255), density=True)
    if ha.std() < 1e-9 or hb.std() < 1e-9:
        return 1.0
    return float(np.corrcoef(ha, hb)[0, 1])


def red_ratio(a):
    """深红族像素占比 —— 产品包装主色 #A82128=(168,33,40)。"""
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    m = (r > 85) & (r < 215) & (g < 95) & (b < 95) & (r > g * 1.75) & (r > b * 1.6)
    return float(m.mean())


def loudness(path):
    r = run(["ffmpeg", "-hide_banner", "-i", path, "-af", "volumedetect", "-f", "null", "-"],
            check=False)
    mean = peak = None
    for ln in r.stderr.splitlines():
        if "mean_volume:" in ln:
            mean = ln.split("mean_volume:")[1].strip()
        if "max_volume:" in ln:
            peak = ln.split("max_volume:")[1].strip()
    return mean, peak


def main():
    man = json.load(open(os.path.join(PILOT, "pilot.json")))
    DUR = man["duration"]
    os.makedirs(TMP, exist_ok=True)
    print("=" * 96)
    print("Q1/Q2/Q4 · 逐镜指标")
    print("=" * 96)
    print("%-22s %-5s | 首帧锁定 | 末帧锁定 | 产品红占比 | 运动量 | 末尾僵住?" % ("镜", "类型"))
    print("-" * 96)
    rows = []
    for s in man["shots"]:
        k = s["key"]
        mp4 = os.path.join(OUT, "preview", "prev_%s.mp4" % k)
        if not os.path.exists(mp4):
            print("  %-22s 预览缺失" % k)
            continue
        # 复刻：首帧 / 末帧 / 中间取样
        rc_first = frame_at(mp4, 0.0, os.path.join(TMP, k + "_r0.jpg"))
        rc_last = frame_at(mp4, DUR - 0.06, os.path.join(TMP, k + "_rE.jpg"))
        # 我们喂进去的 first/last
        gf_first = np.asarray(Image.open(os.path.join(PILOT, "first", k + ".jpg"))
                              .convert("RGB").resize(SZ), dtype=np.float32)
        gf_last = np.asarray(Image.open(os.path.join(PILOT, "last", k + ".jpg"))
                             .convert("RGB").resize(SZ), dtype=np.float32)
        lock_f = float(np.abs(gray(rc_first) - gray(gf_first)).mean())
        lock_l = float(np.abs(gray(rc_last) - gray(gf_last)).mean())
        # 产品红
        mid = frame_at(mp4, DUR * 0.5, os.path.join(TMP, k + "_rM.jpg"))
        red = max(red_ratio(rc_first), red_ratio(mid), red_ratio(rc_last))
        # 运动量：0.3/1.5/2.7/3.9s 四点相邻差
        fs = [frame_at(mp4, t, os.path.join(TMP, k + "_m%.1f.jpg" % t))
              for t in (0.3, 1.5, 2.7, 3.9)]
        diffs = [float(np.abs(gray(fs[i]) - gray(fs[i - 1])).mean()) for i in range(1, 4)]
        # 末尾是否僵住：3.9s → 4.4s
        f44 = frame_at(mp4, DUR - 0.18, os.path.join(TMP, k + "_m44.jpg"))
        tail = float(np.abs(gray(f44) - gray(fs[-1])).mean())
        rows.append((k, s["kind"], lock_f, lock_l, red, diffs, tail))
        print("%-22s %-5s |  %6.1f  |  %6.1f  |   %5.1f%%    | %s | %5.1f"
              % (k, s["kind"], lock_f, lock_l, red * 100,
                 " ".join("%4.1f" % d for d in diffs), tail))

    print()
    print("=" * 96)
    print("Q3 · 音轨同源性（复刻 vs 原片）")
    print("=" * 96)
    for s in man["shots"]:
        k = s["key"]
        rc = os.path.join(OUT, "preview", "prev_%s.mp4" % k)
        og = os.path.join(OUT, "orig", k + ".mp4")
        m1, p1 = loudness(rc)
        # 原片段无音轨（切的时候 -an），改测原片整片同窗口
        src = os.path.join(BASE, s["video"] + ".mp4")
        seg = os.path.join(TMP, k + "_oseg.wav")
        run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "%.3f" % s["t_start"],
             "-t", "%.3f" % DUR, "-i", src, "-vn", "-ar", "16000", "-ac", "1", seg])
        m2, p2 = loudness(seg)
        print("  %-22s 复刻 mean=%-9s peak=%-9s | 原片同窗 mean=%-9s peak=%s"
              % (k, m1, p1, m2, p2))

    print()
    print("判读参考：首/末帧锁定 MAE <15 视为被钉住，>35 视为基本没锁；")
    print("          相邻帧 MAE >3 视为在动；末尾 MAE <2 说明最后 0.5s 画面僵住。")


if __name__ == "__main__":
    main()
