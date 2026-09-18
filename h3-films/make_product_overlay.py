#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把「真产品图」按透视贴到生成帧里的包装袋平面上。

为什么需要它
------------
H3 是生成模型，包装上的中文必然被画成乱码（实测片1 镜3/镜12 出现成片的伪字）。
所以工程上分两层（见 _product/PRODUCT.md）：
  · 生成层：prompt 只描述「壳」——形状/配色/材质/光感/成品图/挂孔，
            品牌与品名区域写成 clean unprinted red field，画面保持干净。
  · 合成层：把真实产品图按透视贴到这个空壳上，文字由真图提供，100% 准确。

本脚本就是「合成层」的最小实现：不改 prompt、不重跑 GPU，只在成帧上做透视贴图。

用法
----
  python make_product_overlay.py --frame 生成帧.jpg --product 产品图.jpg \
      --crop 62,78,752,1022 --quad 112,372 655,368 573,1059 176,1059 \
      --out 贴图结果.jpg

  --quad 按 TL TR BR BL 顺序给四个角（生成帧里包装袋正面的四个角，像素坐标）。
  --crop 是产品图里「袋子本体」的裁切框 x1,y1,x2,y2（去掉背景）。
  --keep-highlight 会保留原帧的高光（塑料膜反光），贴图后不那么"平"。
"""
import argparse
import sys

import numpy as np
from PIL import Image, ImageFilter


def perspective_coeffs(src_pts, dst_pts):
    """求 PIL PERSPECTIVE 需要的 8 个系数。

    PIL 的 transform(PERSPECTIVE, c) 把**目标**坐标映射回**源**坐标：
        u = (a·x + b·y + c) / (g·x + h·y + 1)
        v = (d·x + e·y + f) / (g·x + h·y + 1)
    这里传入的 src_pts 是袋子在**产品图**里的四角（源），dst_pts 是袋子在**生成帧**里的四角（目标）。
    我们要的正是「目标 → 源」，所以直接解这个方程组。
    """
    A, B = [], []
    for (u, v), (x, y) in zip(src_pts, dst_pts):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        B.append(u)
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        B.append(v)
    res = np.linalg.solve(np.array(A, dtype=float), np.array(B, dtype=float))
    return tuple(res.tolist())


def build_mask(size, quad, shrink=2.0, feather=2.0):
    """在目标帧尺寸上，用四边形生成一张带羽化的 alpha 蒙版。"""
    w, h = size
    mask = Image.new("L", (w, h), 0)
    # 四边形四角各往里收 shrink 像素，避免把袋子的描边一起盖掉
    pts = np.array(quad, dtype=float)
    center = pts.mean(axis=0)
    shrunk = []
    for p in pts:
        d = p - center
        n = np.linalg.norm(d)
        shrunk.append(tuple(p - d / n * shrink) if n > 0 else tuple(p))
    ImageDraw_polygon(mask, shrunk, 255)
    if feather > 0:
        mask = mask.filter(ImageFilter.GaussianBlur(feather))
    return mask


def ImageDraw_polygon(img, pts, fill):
    from PIL import ImageDraw
    ImageDraw.Draw(img).polygon(pts, fill=fill)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", required=True, help="生成帧（要贴图的画面）")
    ap.add_argument("--product", required=True, help="真实产品图")
    ap.add_argument("--crop", required=True, help="产品图裁切框 x1,y1,x2,y2")
    ap.add_argument("--quad", required=True, nargs=4,
                    help="生成帧里袋子四角 TL TR BR BL，形如 x,y x,y x,y x,y")
    ap.add_argument("--out", required=True)
    ap.add_argument("--opacity", type=float, default=1.0, help="贴图不透明度 0-1")
    ap.add_argument("--keep-highlight", action="store_true",
                    help="保留原帧高光（塑料膜反光），让贴图不那么平")
    ap.add_argument("--highlight-thr", type=int, default=205,
                    help="高光判定阈值（0-255），越高保留越少")
    args = ap.parse_args()

    crop = [int(v) for v in args.crop.split(",")]
    quad = [tuple(float(v) for v in p.split(",")) for p in args.quad]
    if len(crop) != 4 or len(quad) != 4:
        sys.exit("--crop 要 4 个数，--quad 要 4 个坐标对")

    frame = Image.open(args.frame).convert("RGB")
    W, H = frame.size
    prod = Image.open(args.product).convert("RGB").crop(tuple(crop))
    pw, ph = prod.size

    # 产品图矩形的四角 → 生成帧里的四角
    src_pts = [(0, 0), (pw, 0), (pw, ph), (0, ph)]
    coeffs = perspective_coeffs(src_pts, quad)

    warped = prod.transform((W, H), Image.PERSPECTIVE, coeffs, Image.BICUBIC)
    mask = build_mask((W, H), quad, shrink=2, feather=2)

    if args.opacity < 1.0:
        mask = mask.point(lambda v: int(v * args.opacity))

    out = Image.composite(warped, frame, mask)

    if args.keep_highlight:
        f = np.asarray(frame).astype(np.float32)
        o = np.asarray(out).astype(np.float32)
        lum = f.mean(axis=2)
        hit = np.clip((lum - args.highlight_thr) / max(1.0, 255 - args.highlight_thr), 0, 1)
        hit = np.asarray(Image.fromarray((hit * 255).astype(np.uint8)).filter(
            ImageFilter.GaussianBlur(1.5)), dtype=np.float32) / 255.0
        hit = hit[..., None]
        # screen 叠加：把原帧的高光重新打回贴图上
        o = 255.0 - (255.0 - o) * (1.0 - hit * 0.75)
        out = Image.fromarray(np.clip(o, 0, 255).astype(np.uint8))

    out.save(args.out, quality=95)
    print(f"✔ 已输出 {args.out}  ({W}×{H})")
    print(f"  产品图裁切 {pw}×{ph}  →  四角 {quad}")


if __name__ == "__main__":
    main()
