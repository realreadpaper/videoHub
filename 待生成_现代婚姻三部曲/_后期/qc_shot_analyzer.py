#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
单镜质检器 —— 一次给出三类量化指标，用于判断「画面为什么不好」。

指标
  1. 帧差 MAE 序列   -> 检出孤立尖峰 = 镜内硬切/跳变（正常 2~6，硬切 >20）
  2. 有效分辨率探针  -> 下采样到 W 再放大回原尺寸算 PSNR，越高说明真实高频越少
  3. 拉普拉斯方差    -> 锐度（越高越锐，受内容影响，仅同内容间可比）

用法
  python3 qc_shot_analyzer.py 视频1.mp4 [视频2.mp4 ...] [--frames 60,180,300] [--quiet]

  （注意：多文件只做并排打印，没有 --label 选项 —— 想区分请直接看文件名列。）

判据（来自 2026-09-14 实测基线）
  · 帧差 MAE 正常区间 0.9~3.5（静镜）~ 6（运镜）；>20 的孤立尖峰 = 跳变
  · 硬切会让 MAE 飙到 40 以上，且前后帧各自连续
"""
import argparse, os, re, subprocess, sys, tempfile

import numpy as np
from PIL import Image

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"


def probe(path):
    """取视频基础参数"""
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,nb_frames,r_frame_rate,bit_rate",
         "-of", "default=nw=1", path],
        capture_output=True, text=True).stdout
    d = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            d[k] = v
    return d


def decode_gray(path, w, h, tmp):
    """整段解码为灰度小图序列（用于帧差）"""
    d = os.path.join(tmp, "seq_" + re.sub(r"\W", "_", os.path.basename(path)))
    os.makedirs(d, exist_ok=True)
    for f in os.listdir(d):
        os.remove(os.path.join(d, f))
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", path,
                    "-vf", "fps=24,scale=%d:%d" % (w, h),
                    os.path.join(d, "%04d.png")], capture_output=True)
    return d


def frame_diff(d, w, h):
    """帧差 MAE 序列"""
    files = sorted(os.listdir(d))
    arr = []
    prev = None
    for f in files:
        g = np.asarray(Image.open(os.path.join(d, f)).convert("L"), dtype=np.float32)
        if prev is not None:
            arr.append(float(np.abs(g - prev).mean()))
        prev = g
    return np.array(arr)


def lap_var(g):
    """拉普拉斯方差（锐度代理）"""
    k = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
    from numpy.lib.stride_tricks import sliding_window_view
    if g.shape[0] < 3 or g.shape[1] < 3:
        return 0.0
    win = sliding_window_view(g, (3, 3))
    lap = (win * k).sum(axis=(-2, -1))
    return float(lap.var())


def eff_res(path, width, height, frames, tmp):
    """有效分辨率探针：下采样到 W 再放大回原尺寸，PSNR 越低说明真实高频越多"""
    res = {}
    for n in frames:
        raw = os.path.join(tmp, "o_%d.png" % n)
        subprocess.run([FFMPEG, "-v", "error", "-y", "-i", path,
                        "-vf", "select=eq(n\\,%d)" % n, "-frames:v", "1", raw],
                       capture_output=True)
        if not os.path.exists(raw):
            continue
        row = {}
        for W in (448, 560, 672, 896, 1008):
            H = int(round(W * height / float(width)))
            dn = os.path.join(tmp, "d_%d_%d.png" % (n, W))
            subprocess.run([FFMPEG, "-v", "error", "-y", "-i", raw,
                            "-vf", "scale=%d:%d:flags=bicubic,scale=%d:%d:flags=bicubic"
                                   % (W, H, width, height), dn], capture_output=True)
            out = subprocess.run([FFMPEG, "-i", dn, "-i", raw, "-lavfi", "psnr",
                                  "-f", "null", "-"],
                                 capture_output=True, text=True).stderr
            m = re.search(r"average:([\d.]+|inf)", out)
            row[W] = float(m.group(1)) if m and m.group(1) != "inf" else None
        res[n] = row
    return res


def sharpness(path, width, height, frames, tmp):
    """抽帧算拉普拉斯方差（在原始分辨率上算）"""
    vals = {}
    for n in frames:
        raw = os.path.join(tmp, "s_%d.png" % n)
        subprocess.run([FFMPEG, "-v", "error", "-y", "-i", path,
                        "-vf", "select=eq(n\\,%d)" % n, "-frames:v", "1", raw],
                       capture_output=True)
        if os.path.exists(raw):
            g = np.asarray(Image.open(raw).convert("L"), dtype=np.float32)
            vals[n] = lap_var(g)
    return vals


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("videos", nargs="+")
    ap.add_argument("--frames", default="60,180,300")
    ap.add_argument("--quiet", action="store_true", help="只输出汇总")
    a = ap.parse_args()
    frames = [int(x) for x in a.frames.split(",")]
    tmp = tempfile.mkdtemp()

    results = {}
    for path in a.videos:
        if not os.path.exists(path):
            print("跳过（不存在）: %s" % path)
            continue
        p = probe(path)
        W = int(p.get("width", 0)); H = int(p.get("height", 0))
        nb = p.get("nb_frames", "?")
        br = p.get("bit_rate", "?")

        # 1) 帧差
        d = decode_gray(path, 336, int(round(336 * H / float(W))) if W else 192, tmp)
        diff = frame_diff(d, 336, 192)
        med = float(np.median(diff)) if len(diff) else 0
        mx = float(diff.max()) if len(diff) else 0
        thr = max(5.0, med + 4 * diff.std()) if len(diff) else 5.0
        spikes = [(i + 1, float(v)) for i, v in enumerate(diff) if v > thr]

        # 2) 有效分辨率
        er = eff_res(path, W, H, frames, tmp)

        # 3) 锐度
        sh = sharpness(path, W, H, frames, tmp)

        results[path] = dict(W=W, H=H, nb=nb, br=br, med=med, mx=mx,
                             nspike=len(spikes), spikes=spikes,
                             er=er, sh=sh)

    # ---- 输出 ----
    print()
    print("=" * 88)
    print("【1】基础参数与帧差（硬切检测）")
    print("=" * 88)
    print("%-34s %11s %9s %8s %8s %7s" % ("文件", "分辨率", "帧数", "中位MAE", "最大MAE", "尖峰数"))
    for path, r in results.items():
        print("%-34s %11s %9s %8.2f %8.2f %7d" % (
            os.path.basename(path)[:33], "%dx%d" % (r["W"], r["H"]),
            r["nb"], r["med"], r["mx"], r["nspike"]))
    print()
    for path, r in results.items():
        if r["spikes"]:
            pos = ", ".join("%.2fs(MAE %.0f)" % (i / 24.0, v) for i, v in r["spikes"][:8])
            print("  ⚠ %s 检出硬切: %s" % (os.path.basename(path), pos))
        else:
            print("  ✔ %s 无硬切（最大 MAE %.1f，阈值 %.1f）" % (
                os.path.basename(path), r["mx"], max(5.0, r["med"] + 4 * 5)))

    print()
    print("=" * 88)
    print("【2】有效分辨率探针（PSNR dB，越低 = 真实高频越多 = 越清晰）")
    print("=" * 88)
    ws = [448, 560, 672, 896, 1008]
    print("%-34s %10s %10s %10s %10s %10s" % (tuple(["文件"] + ["%dpx" % w for w in ws])))
    avg = {}
    for path, r in results.items():
        cells = []
        vals = []
        for w in ws:
            vv = [r["er"][f][w] for f in r["er"] if r["er"][f].get(w) is not None]
            if vv:
                m = sum(vv) / len(vv); vals.append(m); cells.append("%10.2f" % m)
            else:
                cells.append("%10s" % "—")
        avg[path] = vals
        print("%-34s %s" % (os.path.basename(path)[:33], " ".join(cells)))

    print()
    print("=" * 88)
    print("【3】锐度（拉普拉斯方差，同内容下越高越锐）")
    print("=" * 88)
    print("%-34s %10s %10s %10s" % tuple(["文件"] + ["帧%d" % f for f in frames]))
    for path, r in results.items():
        print("%-34s %s" % (os.path.basename(path)[:33],
              " ".join("%10.1f" % r["sh"].get(f, 0) for f in frames)))

    # 两两对照
    paths = [p for p in a.videos if p in results]
    if len(paths) == 2:
        A, B = results[paths[0]], results[paths[1]]
        print()
        print("=" * 88)
        print("【对照】%s  ->  %s" % (os.path.basename(paths[0]), os.path.basename(paths[1])))
        print("=" * 88)
        print("  有效分辨率（负数 = 后者更清晰，即真实高频更多）:")
        la, lb = avg[paths[0]], avg[paths[1]]
        for w, x, y in zip(ws, la, lb):
            print("     %5dpx : %.2f -> %.2f  (%+.2f dB)" % (w, x, y, y - x))
        print("  帧差尖峰 : %d -> %d" % (A["nspike"], B["nspike"]))
        print("  锐度(均值): %.1f -> %.1f" % (
            np.mean(list(A["sh"].values())) if A["sh"] else 0,
            np.mean(list(B["sh"].values())) if B["sh"] else 0))


if __name__ == "__main__":
    main()
