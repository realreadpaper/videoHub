#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""袋面四角标定器 —— 出一张「带网格 + 坐标标尺 + 可选 quad」的图，供人读/校坐标。

为什么需要人工标一次
--------------------
自动检测（detect_pack.py）能找到**高饱和红区**，但 H3 画的袋面 = 红区 + 底部菜品图，
而且不同镜里袋型比例不一样（有的矮胖、有的竖长），纯靠颜色推不出整袋四角。
所以定位这一步走「人标一次 → 写入 tracks.json → 之后逐帧追踪复用」，
既保证准确，又只付一次人工成本。

用法
----
  # 出标定图（无 quad）
  python3 mark_quad.py --video _deliver/shots_film1/shot18.mp4 --t 8 --out _review/mq18.jpg
  # 校核：把已有 quad 画上去看贴合不贴合
  python3 mark_quad.py --video ...ths/shot18.mp4 --t 8 --quad "20,160 768,150 768,890 25,890" \
      --product _product/mine/product_鲍汁红烧酱料_原图.jpg --crop 62,78,752,1022 --preview
--preview 会直接把产品图按 quad 透视贴出来，**所见即交付效果**。
"""
import argparse
import os
import subprocess
import sys
import tempfile

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def grab(video, t):
    p = tempfile.mktemp(suffix=".png")
    subprocess.run(["ffmpeg", "-v", "error", "-ss", "%.3f" % t, "-i", video,
                    "-frames:v", "1", p, "-y"], capture_output=True)
    if not (os.path.exists(p) and os.path.getsize(p) > 0):
        sys.exit("抽帧失败 %s @%.2fs" % (video, t))
    return p


def perspective_coeffs(src, dst):
    A, B = [], []
    for (u, v), (x, y) in zip(src, dst):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); B.append(u)
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y]); B.append(v)
    return tuple(np.linalg.solve(np.array(A, float), np.array(B, float)).tolist())


def warp_product(frame, product, crop, quad, keep_highlight=True, thr=200):
    """把产品图按透视贴到 frame 上（与 make_product_overlay.py 同一套算法）。"""
    W, H = frame.size
    prod = product.crop(tuple(crop))
    pw, ph = prod.size
    coeffs = perspective_coeffs([(0, 0), (pw, 0), (pw, ph), (0, ph)], quad)
    warped = prod.transform((W, H), Image.PERSPECTIVE, coeffs, Image.BICUBIC)

    mask = Image.new("L", (W, H), 0)
    pts = np.array(quad, float)
    c = pts.mean(axis=0)
    shrunk = [tuple(p - (p - c) / max(np.linalg.norm(p - c), 1e-6) * 2) for p in pts]
    from PIL import ImageDraw
    ImageDraw.Draw(mask).polygon(shrunk, fill=255)
    from PIL import ImageFilter
    mask = mask.filter(ImageFilter.GaussianBlur(2))
    out = Image.composite(warped, frame, mask)
    if keep_highlight:
        f = np.asarray(frame).astype(np.float32)
        o = np.asarray(out).astype(np.float32)
        lum = f.mean(axis=2)
        hit = np.clip((lum - thr) / max(1.0, 255 - thr), 0, 1)
        hit = np.asarray(Image.fromarray((hit * 255).astype(np.uint8))
                         .filter(ImageFilter.GaussianBlur(1.5)), dtype=np.float32) / 255.0
        o = 255.0 - (255.0 - o) * (1.0 - hit[..., None] * 0.75)
        out = Image.fromarray(np.clip(o, 0, 255).astype(np.uint8))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--t", type=float, default=7.5)
    ap.add_argument("--out", required=True)
    ap.add_argument("--quad", default=None, help="TL TR BR BL，形如 'x,y x,y x,y x,y'")
    ap.add_argument("--grid", type=int, default=64)
    ap.add_argument("--step-label", type=int, default=128, help="坐标标尺间隔")
    ap.add_argument("--product", default=None)
    ap.add_argument("--crop", default=None)
    ap.add_argument("--preview", action="store_true", help="按 quad 贴出产品图预览")
    ap.add_argument("--scale", type=float, default=1.0)
    a = ap.parse_args()

    p = grab(a.video, a.t)
    frame = Image.open(p).convert("RGB")
    W, H = frame.size
    img = np.array(frame)[:, :, ::-1].copy()   # RGB→BGR
    if a.grid > 0:
        for x in range(0, W, a.grid):
            cv2.line(img, (x, 0), (x, H), (210, 210, 0), 1)
        for y in range(0, H, a.grid):
            cv2.line(img, (0, y), (W, y), (210, 210, 0), 1)
    for x in range(0, W, a.step_label):
        cv2.putText(img, str(x), (x + 3, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 3)
        cv2.putText(img, str(x), (x + 3, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (80, 255, 255), 1)
    for y in range(0, H, a.step_label):
        cv2.putText(img, str(y), (4, y + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 3)
        cv2.putText(img, str(y), (4, y + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (80, 255, 255), 1)

    out_img = Image.fromarray(img[:, :, ::-1])
    if a.quad:
        quad = [tuple(float(v) for v in s.split(",")) for s in a.quad.split()]
        if len(quad) != 4:
            sys.exit("--quad 需要 4 个坐标对")
        if a.preview and a.product and a.crop:
            prod = Image.open(a.product).convert("RGB")
            out_img = warp_product(out_img, prod, [int(v) for v in a.crop.split(",")], quad)
            img = np.array(out_img)[:, :, ::-1].copy()
        else:
            img = np.array(out_img)[:, :, ::-1].copy()
        cv2.polylines(img, [np.array(quad, np.int32)], True, (0, 0, 255), 3)
        for i, (x, y) in enumerate(quad):
            cv2.circle(img, (int(x), int(y)), 8, (0, 255, 0), -1)
            cv2.putText(img, "TL TR BR BL"[i * 2:i * 2 + 2], (int(x) + 12, int(y) - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        out_img = Image.fromarray(img[:, :, ::-1])

    if a.scale != 1.0:
        out_img = out_img.resize((int(W * a.scale), int(H * a.scale)), Image.LANCZOS)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    out_img.save(a.out, quality=93)
    os.unlink(p)
    print("✔ %s  (%dx%d)" % (a.out, out_img.size[0], out_img.size[1]))
    if a.quad:
        print("  quad = %s" % a.quad)
    print("  ★ 读法：黄色网格 %dpx 一格，边缘标尺给实际像素坐标" % a.grid)


if __name__ == "__main__":
    main()
