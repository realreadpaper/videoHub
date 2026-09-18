#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
贴图前后左右对比预览生成器
左＝H3 原版分镜，右＝产品贴图后分镜，中间 1px 分隔线，左上角中文标签。

用法:
  python3 make_overlay_compare.py \
      --orig-dir _deliver/shots_film1 \
      --over-dir _post/film1/s1_overlay \
      --shots 13,15,18 \
      --out _post/film1/贴图前后对比_三镜.mp4
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = [
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/PingFang.ttc",
]


def pick_font(size):
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def make_label(text, width, height_pad=18, fs=52, accent=(235, 60, 60)):
    """生成一块带半透明黑底 + 左侧强调色条的中文标签 PNG。"""
    font = pick_font(fs)
    tmp = Image.new("RGBA", (10, 10))
    d = ImageDraw.Draw(tmp)
    bbox = d.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    W, H = tw + fs * 2 + 24, th + height_pad * 2
    img = Image.new("RGBA", (W, H), (0, 0, 0, 165))
    dr = ImageDraw.Draw(img)
    dr.rectangle([0, 0, 10, H], fill=accent + (255,))
    dr.text((fs + 18, (H - th) // 2 - bbox[1]), text, font=font, fill=(255, 255, 255, 255))
    return img


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stdout[-2000:] + "\n" + r.stderr[-2000:] + "\n")
        raise SystemExit(f"命令失败: {' '.join(cmd[:6])} ...")
    return r


def has_audio(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
         "stream=index", "-of", "csv=p=0", path],
        capture_output=True, text=True)
    return bool(r.stdout.strip())


def probe_wh(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height", "-of", "csv=p=0", path],
        capture_output=True, text=True)
    w, h = r.stdout.strip().split(",")
    return int(w), int(h)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--orig-dir", required=True, help="原版分镜目录")
    ap.add_argument("--over-dir", required=True, help="贴图后分镜目录")
    ap.add_argument("--shots", required=True, help="镜号，逗号分隔，如 13,15,18")
    ap.add_argument("--out", required=True)
    ap.add_argument("--left-label", default="原版")
    ap.add_argument("--right-label", default="产品贴图后")
    ap.add_argument("--crf", default="20")
    ap.add_argument("--speed", type=float, default=1.0,
                    help="可选提速，音画同步（atempo）")
    args = ap.parse_args()

    shots = [s.strip() for s in args.shots.split(",") if s.strip()]
    tmpd = tempfile.mkdtemp(prefix="ovcmp_")
    parts = []

    for s in shots:
        tag = f"shot{s.zfill(2)}"
        o = os.path.join(args.orig_dir, tag + ".mp4")
        v = os.path.join(args.over_dir, tag + ".mp4")
        for p in (o, v):
            if not os.path.exists(p):
                raise SystemExit(f"缺文件: {p}")
        ow, oh = probe_wh(o)
        vw, vh = probe_wh(v)
        if (ow, oh) != (vw, vh):
            raise SystemExit(f"{tag} 尺寸不一致: 原 {ow}x{oh} vs 贴图 {vw}x{vh}")

        lab_l = make_label(f"镜{s.lstrip('0')} {args.left_label}", ow, accent=(120, 120, 120))
        lab_r = make_label(f"镜{s.lstrip('0')} {args.right_label}", vw, accent=(235, 60, 60))
        pl = os.path.join(tmpd, f"{tag}_L.png")
        pr = os.path.join(tmpd, f"{tag}_R.png")
        lab_l.save(pl)
        lab_r.save(pr)

        out = os.path.join(tmpd, f"{tag}_cmp.mp4")
        fc = (f"[0:v][2:v]overlay=24:24[a];"
              f"[1:v][3:v]overlay=24:24[b];"
              f"[a][b]hstack=inputs=2[ab];"
              f"[ab]drawbox=x={ow - 1}:y=0:w=2:h={oh}:color=white@0.85:t=fill[v]")
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
               "-i", o, "-i", v, "-i", pl, "-i", pr,
               "-filter_complex", fc, "-map", "[v]"]
        if has_audio(o):
            cmd += ["-map", "0:a:0", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2"]
        cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", args.crf,
                "-pix_fmt", "yuv420p", "-r", "24", "-movflags", "+faststart", out]
        run(cmd)
        parts.append(out)
        print(f"  ✔ {tag} 对比片段")

    # concat
    lst = os.path.join(tmpd, "list.txt")
    with open(lst, "w") as f:
        for p in parts:
            f.write(f"file '{p}'\n")
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat",
         "-safe", "0", "-i", lst, "-c", "copy", "-movflags", "+faststart", args.out])
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", args.out], capture_output=True, text=True)
    print(f"\n✔ 输出 {args.out}  时长 {float(r.stdout.strip()):.2f}s")
    shutil.rmtree(tmpd, ignore_errors=True)


if __name__ == "__main__":
    main()
