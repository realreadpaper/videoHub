#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""字幕带局部处理 —— 把 H3「照抄原片烧死字幕」产生的乱码字压掉。

背景
----
prompt 里已经写死 `no subtitles / no captions / no burned-in titles / never imitate ...`
（见 p1_data.py 的 NO_TEXT_CLAUSE），build.py 还会在缺条款时拒绝出片。但**已经生成好的**片子
里仍然有乱码字（H3 是临摹型生成器，训练数据里带烧死字幕的短视频太多）。
重跑是根治（已加铁律），但重跑要 GPU；本脚本是**零 GPU 的兜底**。

实测字幕带位置：**画面 y ≈ 72%–82%**（片1 全片扫描，见 _review/片1_字幕带扫描.jpg）。

★ 方法选择（实测教训）
----------------------
`delogo` 在**大面积平坦渐变**区域（人物黑西装、墙面）会产生明显的**垂直拖拽伪影** ——
比原来的乱码字更难看。片1 首轮用 delogo 处理 6 镜，校验接触表一眼就否掉了。

改为 **clone（克隆字幕带正上方的同高度画面 → 覆盖到字幕带上）**：
因为取的是**紧邻上方**的像素，纹理与光照天然连续，对墙面/桌面/衣料这类静态背景几乎无痕；
代价是画面里有运动物体时会有轻微错位（比拖拽伪影可接受得多）。再叠一层轻微模糊抹掉接缝。

三种方法
--------
  clone   克隆上方行覆盖（默认，实测最自然）
  blur    带内高斯模糊（最保守，会留一条糊带）
  darken  带内压对比度（几乎不动画面，只让字读不出来）

只对**确认有字**的镜处理 —— 对干净镜做处理是白损伤画面。
镜清单来自 scan_text_band.py 的人工判读结果（机器不替人做这个判断）。

用法
----
  python3 mask_text_band.py --shots _post/film1/s2_aligned --shots-list 2,3,7,8,11,12 \
      --out _post/film1/s3_masked --method clone --band 0.72,0.82
"""
import argparse
import os
import subprocess
import sys


def probe_dur(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", p], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def build(video_filter, method, W, H, band):
    """返回 ffmpeg 参数列表（filter 部分）。

    yuv420p 要求 x/y/宽/高都是偶数，否则 ffmpeg 直接报错。
    """
    y0 = int(H * band[0]) // 2 * 2
    bh = max(16, int(H * (band[1] - band[0])) // 2 * 2)
    y0 = min(y0, H - bh)
    y0 = y0 // 2 * 2
    if method == "clone":
        sy = max(0, y0 - bh) // 2 * 2
        fc = ("[0:v]split=2[bg][fg];"
              "[fg]crop=%d:%d:0:%d,boxblur=3:1[src];"
              "[bg][src]overlay=0:%d:format=auto[v]" % (W, bh, sy, y0))
        return video_filter + ["-filter_complex", fc, "-map", "[v]", "-map", "0:a?"]
    if method == "blur":
        return video_filter + ["-vf", "boxblur=6:2:0:0:0:0", "-map", "0:v", "-map", "0:a?"]
    if method == "darken":
        return video_filter + ["-vf",
                               "lutyuv=y='if(between(Y,%d,%d),Y*0.5+50,Y)'" % (int(band[0] * 255),
                                                                                 int(band[1] * 255)),
                               "-map", "0:v", "-map", "0:a?"]
    sys.exit("未知方法 %s" % method)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", required=True)
    ap.add_argument("--shots-list", required=True, help="要处理的镜号，如 2,3,7,8")
    ap.add_argument("--out", required=True)
    ap.add_argument("--method", choices=["clone", "blur", "darken"], default="clone")
    ap.add_argument("--band", default="0.72,0.82", help="字幕带 y 比例区间 a,b")
    ap.add_argument("--crf", type=int, default=16)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    band = tuple(float(x) for x in a.band.split(","))
    want = set(int(x) for x in a.shots_list.replace(" ", "").split(",") if x)
    files = sorted(f for f in os.listdir(a.shots) if f.endswith(".mp4"))
    if not files:
        sys.exit("分镜目录为空")

    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                            "-show_entries", "stream=width,height", "-of", "csv=p=0",
                            os.path.join(a.shots, files[0])], capture_output=True, text=True)
    try:
        W, H = (int(v) for v in probe.stdout.strip().split(",")[:2])
    except Exception:
        sys.exit("读不到分辨率：%s" % probe.stdout)

    y0 = int(H * band[0]) // 2 * 2
    bh = int(H * (band[1] - band[0])) // 2 * 2
    print("方法=%s  分辨率=%dx%d  处理带 y=%d–%d（高 %dpx，约 %.0f%%–%.0f%%）"
          % (a.method, W, H, y0, y0 + bh, bh, band[0] * 100, band[1] * 100))
    print()
    if not a.dry_run:
        os.makedirs(a.out, exist_ok=True)

    n_hit = 0
    for f in files:
        n = int(f[4:6])
        src = os.path.join(a.shots, f)
        dst = os.path.join(a.out, f)
        if n in want:
            n_hit += 1
            if a.dry_run:
                print("  [dry] 处理 %s" % f)
                continue
            cmd = ["ffmpeg", "-v", "error", "-i", src] + build([], a.method, W, H, band) + [
                "-c:v", "libx264", "-preset", "medium", "-crf", str(a.crf),
                "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", dst, "-y"]
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode != 0:
                sys.exit("处理失败 %s\n%s\n%s" % (f, " ".join(cmd), r.stderr[-600:]))
            print("  ✔ %s  %.3fs（字幕带已覆盖）" % (f, probe_dur(dst)))
        else:
            if a.dry_run:
                print("  [dry] 原样保留 %s" % f)
                continue
            subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-c", "copy", dst, "-y"],
                           check=True)
            print("  ·  %s  原样保留" % f)
    print("\n共处理 %d 镜（清单 %d 镜）" % (n_hit, len(want)))
    if n_hit != len(want):
        got = set(int(f[4:6]) for f in files)
        print("⚠ 清单里这些镜不存在：%s" % sorted(want - got))
    print("✔ 输出目录 %s" % a.out)
    print("★ 交付前必须跑 scan_text_band.py 出接触表逐格目视 —— 机器不替人判字")


if __name__ == "__main__":
    main()
