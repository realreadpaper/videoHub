#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 H3 FL2VA 首帧/尾帧锚定图 —— 把「真产品图」合进产品镜的关键帧。

为什么需要它
------------
H3 用的是 `minimax_h3_fl2va_*` 权重（**F**irst-**L**ast frame **to** **V**ideo+**A**udio），
官方原生支持 `first_frame` / `last_frame` 关键帧条件 —— 现有工作流里
`MiniMaxH3AudioConditioningT8` 节点就有这两个输入槽，只是从来没接线。

把「真产品图」合成进关键帧后模型就从这一帧开始生成，**袋面由模型自己渲染**：
透视、光影、材质天然一致，不再需要事后逐帧抠图贴图，也顺带根治了
「镜15/18 袋型偏扁、横向拉伸」的比例失真（那是后处理贴图的固有代价）。

做法（零 GPU，本地就能跑）
--------------------------
  抽关键帧 → detect_pack 自动定位袋面四边形（或 --quad 手标）→ 透视贴真产品图
  → 缩放到 H3 训练分辨率（默认 384×672，stage1 竖版）

用法
----
  # 自动定位（袋面完整清晰时首选）
  python3 make_first_frame.py \
      --shot-video _deliver/shots_film1/shot13.mp4 --at 0.0 \
      --product _product/mine/product_鲍汁红烧酱料_原图.jpg --crop 62,78,752,1022 \
      --out _frames/film1_shot13_first.png --preview _frames/film1_shot13_first_预览.jpg

  # 自动定位不准时（袋被手挡、角度偏）→ 用 mark_quad.py 出网格图手标四角，按 TL TR BR BL 传入
  python3 make_first_frame.py ... --quad 112,372 655,368 573,1059 176,1059

注意
----
* 关键帧的宽高比必须与 latent 一致（9:16），否则 H3 会先做对齐裁切、构图会漂。
  本脚本输出的就是 384×672（2:3.5 ≈ 9:16 竖版），与 stage1 一致。
* 贴图后袋面带上真包装印刷 → prompt 必须同步换成「带印刷」口径（见 p1_data.SP_PRINTED），
  否则模型会收到「袋面必须空白」的指令，与首帧互相打架。
"""
import argparse
import os
import sys
from importlib.util import module_from_spec, spec_from_file_location

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = "/System/Library/Fonts/Hiragino Sans GB.ttc"


def _load(name, path):
    sp = spec_from_file_location(name, path)
    m = module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def grab(video, at):
    """按时间抽一帧（BGR）。"""
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        sys.exit("打不开 %s" % video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(at * fps)))
    ok, bgr = cap.read()
    cap.release()
    if not ok:
        sys.exit("抽帧失败：%s @ %.3fs" % (video, at))
    return bgr, fps


def auto_quad(dp, bgr, min_area, min_fill, qerr_max=0.05):
    """自动定位袋面四边形：取 quad_err 最小（边界最直）的候选。

    quad_err = 轮廓点到拟合四边形的平均距离 / 周长 —— 袋面是直线边界，误差极小；
    肉块/酱汁/金属划痕是曲线，误差大一个量级。这是「是否能可靠定位」的判据。
    """
    packs, _ = dp.find_packs(bgr, min_area, min_fill)
    packs = [p for p in packs if p.get("quad_err", 9) <= qerr_max]
    if not packs:
        return None, []
    packs.sort(key=lambda p: p.get("quad_err", 9))
    return packs[0]["quad"], packs


def align_quad(quad, size):
    """把四角规范成 TL TR BR BL 顺序（按角度排序），避免手标顺序写错导致自交。"""
    pts = np.asarray(quad, float)
    c = pts.mean(axis=0)
    ang = np.arctan2(pts[:, 1] - c[1], pts[:, 0] - c[0])
    # 图像坐标系（y 向下）：从左上开始顺时针 = 角度从 -135° 起
    order = np.argsort((ang + np.pi * 3 / 4) % (2 * np.pi))
    return pts[order].tolist()


def preview_sheet(orig_rgb, out_rgb, quad, tag):
    w, h = orig_rgb.size
    sheet = Image.new("RGB", (w * 2 + 8, h + 34), (18, 18, 18))
    d = ImageDraw.Draw(sheet)
    f = ImageFont.truetype(FONT, 22) if os.path.exists(FONT) else ImageFont.load_default()
    sheet.paste(orig_rgb, (0, 34))
    sheet.paste(out_rgb, (w + 8, 34))
    d.text((8, 6), "%s ｜ 左＝原始关键帧（空白壳）  右＝贴真产品图后（将作为 first_frame）"
           % tag, font=f, fill=(255, 220, 120))
    # 四角标记
    for (x, y), lab in zip(quad, ("TL", "TR", "BR", "BL")):
        d.ellipse([x - 5, y + 34 - 5, x + 5, y + 34 + 5], fill=(0, 255, 120))
        d.text((x + 8, y + 34 + 6), lab, font=f, fill=(0, 255, 120))
    return sheet


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shot-video", required=True, help="原镜视频（stage2 精修后的分镜）")
    ap.add_argument("--at", type=float, default=0.0, help="抽帧时间点（秒），first_frame 用 0.0")
    ap.add_argument("--product", required=True, help="真产品图")
    ap.add_argument("--crop", required=True, help="产品图裁切框 x1,y1,x2,y2")
    ap.add_argument("--quad", nargs=4, default=None,
                    help="手标袋面四角 TL TR BR BL，形如 x,y x,y x,y x,y；不给则自动检测")
    ap.add_argument("--out", required=True, help="输出首帧 PNG")
    ap.add_argument("--res", default="384x672", help="输出分辨率 WxH（须与 latent 同比例）")
    ap.add_argument("--min-area", type=float, default=0.006)
    ap.add_argument("--min-fill", type=float, default=0.55)
    ap.add_argument("--no-highlight", action="store_true", help="不保留原帧高光（默认保留）")
    ap.add_argument("--preview", default=None, help="输出「贴图前/后」对比图")
    a = ap.parse_args()

    dp = _load("dp", os.path.join(HERE, "detect_pack.py"))
    ov = _load("ov", os.path.join(HERE, "overlay_product.py"))

    crop = [int(v) for v in a.crop.split(",")]
    RW, RH = (int(v) for v in a.res.lower().split("x"))

    bgr, fps = grab(a.shot_video, a.at)
    frame_rgb = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    print("原镜帧 %s  @ %.3fs  →  %dx%d" % (os.path.basename(a.shot_video), a.at,
                                            *frame_rgb.size))

    if a.quad:
        quad = align_quad([tuple(float(v) for v in p.split(",")) for p in a.quad], frame_rgb.size)
        print("使用手标四角：%s" % quad)
    else:
        quad, cands = auto_quad(dp, bgr, a.min_area, a.min_fill)
        if quad is None:
            sys.exit("✘ 自动定位失败（该帧没有边界足够直的红色四边形）。\n"
                     "  → 袋被手挡 / 角度倾斜 / 曝光异常时属正常，请用 mark_quad.py 手标四角后\n"
                     "    以 --quad 传入。别硬贴：定位不准的首帧会让整镜构图漂掉。")
        quad = [[float(x), float(y)] for x, y in quad]
        print("自动定位成功：quad_err=%.4f  候选 %d 个" % (
            min(p.get("quad_err", 9) for p in cands), len(cands)))

    product = Image.open(a.product).convert("RGB")
    out = ov.warp_product(frame_rgb, product, crop, quad,
                          opacity=1.0, keep_highlight=not a.no_highlight)

    out_res = out.resize((RW, RH), Image.LANCZOS)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    out_res.save(a.out)
    print("✔ 首帧锚定图 %s  (%dx%d)" % (a.out, RW, RH))

    if a.preview:
        sheet = preview_sheet(frame_rgb, out, quad, "镜 %s" % os.path.basename(a.shot_video))
        sheet.thumbnail((1600, 1600))
        sheet.save(a.preview, quality=92)
        print("✔ 预览 %s" % a.preview)


if __name__ == "__main__":
    main()
