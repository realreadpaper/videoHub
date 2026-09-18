#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compare_quality.py —— A/B 画质对照探针（旧版 TAEHV 解码 vs 新版完整 VAE 解码）

原理：把某一帧下采样到 W 像素宽再放大回原尺寸，与原帧算 PSNR。
      PSNR 越低 = 缩小再放大损失越大 = 说明原帧确实含有更多高频细节。
      实拍 1080p 一般在 30~35 dB；AI 生成的"软"画面会高到 45~55 dB。

用法：
  python3 compare_quality.py OLD.mp4 NEW.mp4 [--frames 60,180,300]
"""
import os, re, subprocess, sys, tempfile

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"


def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True).stdout


def probe(path):
    o = sh([FFPROBE, "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate,nb_frames,bit_rate,codec_name",
            "-of", "default=nw=1", path])
    d = dict(l.split("=", 1) for l in o.strip().splitlines() if "=" in l)
    return d


def psnr_roundtrip(frame_png, W, tmpdir, tag):
    """把 frame_png 下采样到 W 宽再放大回原尺寸，返回 PSNR(dB)。"""
    h = int(sh([FFPROBE, "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=height", "-of", "csv=p=0", frame_png]).strip() or 768)
    w = int(sh([FFPROBE, "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width", "-of", "csv=p=0", frame_png]).strip() or 1344)
    H = max(2, round(W * h / w / 2) * 2)
    down = os.path.join(tmpdir, "d_%s_%d.png" % (tag, W))
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", frame_png,
                    "-vf", "scale=%d:%d:flags=bicubic,scale=%d:%d:flags=bicubic" % (W, H, w, h),
                    down], capture_output=True)
    # 注意：这里不能加 -v error —— psnr 的报告走 info 级，加 -v error 会被吞掉，
    # 结果是永远匹配不到 average，全部误报成"算不出来"。
    out = subprocess.run([FFMPEG, "-hide_banner", "-i", down, "-i", frame_png,
                          "-lavfi", "psnr", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    m = re.search(r"average:([\d.]+|inf)", out)
    if not m:
        return None
    return 999.0 if m.group(1) == "inf" else float(m.group(1))


def grab_frame(video, n, out_png):
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", video,
                    "-vf", "select=eq(n\\,%d)" % n, "-frames:v", "1", out_png],
                   capture_output=True)
    return os.path.exists(out_png)


def main():
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(2)
    old, new = sys.argv[1], sys.argv[2]
    frames = [60, 180, 300]
    if "--frames" in sys.argv:
        frames = [int(x) for x in sys.argv[sys.argv.index("--frames") + 1].split(",")]

    widths = [448, 560, 672, 784, 896, 1008]

    print("=" * 92)
    print("  A/B 画质对照 · 有效分辨率探针")
    print("=" * 92)
    for label, p in [("旧版 TAEHV", old), ("新版完整VAE", new)]:
        if not os.path.exists(p):
            print("  [跳过] 文件不存在：%s" % p); continue
        d = probe(p)
        br = int(d.get("bit_rate", 0) or 0) // 1000
        print("  %-14s %sx%s  %s  %s  %d kbps" % (
            label, d.get("width"), d.get("height"),
            d.get("codec_name"), d.get("r_frame_rate"), br))
    print()

    tmp = tempfile.mkdtemp(prefix="qcmp_")
    results = {}
    for label, p in [("旧版 TAEHV", old), ("新版完整VAE", new)]:
        if not os.path.exists(p):
            continue
        rows = []
        for n in frames:
            fp = os.path.join(tmp, "f_%s_%d.png" % (label.replace(" ", ""), n))
            if not grab_frame(p, n, fp):
                continue
            row = {}
            for W in widths:
                row[W] = psnr_roundtrip(fp, W, tmp, label.replace(" ", ""))
            rows.append((n, row))
        results[label] = rows

    hdr = "  帧   " + "".join("%10d px" % W for W in widths)
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for label in ["旧版 TAEHV", "新版完整VAE"]:
        if label not in results:
            continue
        print("  [%s]" % label)
        for n, row in results[label]:
            cells = ""
            for W in widths:
                v = row.get(W)
                cells += "%12s" % ("%.2f" % v if v is not None and v < 900
                                   else ("inf" if v is not None else "算失败"))
            print("  %5d%s" % (n, cells))
        print()

    print("  判读：同一列 PSNR 越低 = 该分辨率下的细节损失越明显（信息量更大）。")
    print("        新版若在某列明显低于旧版，说明解码器换对了。")
    print("  绝对参考：实拍 1080p ≈ 30~35 dB；>50 dB 基本等于「放大即可还原」。")
    print()
    print("  临时文件：%s" % tmp)


if __name__ == "__main__":
    main()
