#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把回拉到本机的全分辨率成片，加工成审查页需要的压缩预览与抽帧。

为什么不复用 collect_pilot.py：那个脚本是**在服务器上**压缩完再回传（省跨境带宽）。
本轮成片已经整条拉回本机了，再上传/下载一趟纯属浪费 —— 而且机器随时可能被回收，
本地加工不占服务器时间、也不会因为回收而中断。

只做三件事（审查页 build_pilot_review.py 消费的格式）：
  out/preview/prev_<key>.mp4   384 宽 / crf 30 / 带音轨
  out/stills/hi_<key>_NN.jpg   ≥3 帧，宽 560
  （out/orig/<key>.mp4 是原片段，之前已生成，不动）

用法：python3 post_pilot.py [--src out/full2]
"""
import argparse
import glob
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
PILOT = os.path.join(HERE, "pilot")
OUT = os.path.join(PILOT, "out")
STILL_T = [0.30, 1.30, 2.30, 3.30, 4.20]   # 5 个抽帧时刻（镜长 4.458s）


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0, (r.stderr or "").strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(OUT, "full2"))
    args = ap.parse_args()
    src_dir = args.src if os.path.isabs(args.src) else os.path.join(HERE, args.src)

    os.makedirs(os.path.join(OUT, "preview"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "stills"), exist_ok=True)

    files = sorted(glob.glob(os.path.join(src_dir, "*.mp4")))
    if not files:
        print("[!] %s 里没有 mp4" % src_dir)
        return
    for p in files:
        k = os.path.basename(p)[:-4]
        prev = os.path.join(OUT, "preview", "prev_%s.mp4" % k)
        ok, err = run(["ffmpeg", "-v", "error", "-i", p, "-vf", "scale=384:-2",
                       "-c:v", "libx264", "-crf", "30", "-preset", "veryfast",
                       "-c:a", "aac", "-b:a", "64k", prev, "-y"])
        sz = os.path.getsize(prev) // 1024 if os.path.exists(prev) else 0
        print("  %-26s 预览 %s %d KB" % (k, "✔" if ok else "✘ " + err[:80], sz))

        n = 0
        for i, t in enumerate(STILL_T, 1):
            dst = os.path.join(OUT, "stills", "hi_%s_%02d.jpg" % (k, i))
            ok2, _ = run(["ffmpeg", "-v", "error", "-ss", "%.2f" % t, "-i", p,
                          "-frames:v", "1", "-vf", "scale=560:-2", "-q:v", "3",
                          dst, "-y"])
            n += 1 if (ok2 and os.path.exists(dst)) else 0
        print("  %-26s 抽帧 %d/%d" % (k, n, len(STILL_T)))
    print("✔ 本地加工完成，可直接跑 build_pilot_review.py")


if __name__ == "__main__":
    main()
