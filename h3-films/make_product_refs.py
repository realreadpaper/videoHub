#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把产品原图加工成 H3 Ref2VA 可直接消费的参考图组。

为什么不能直接用原图
--------------------
你的产品原图是**电商详情页截图**：红色背景与红袋同色系、顶部有被裁切的金色大字、
四角散落着桂皮八角。Ref2VA 的参考图是「身份权威」——模型会把图上的一切都当成产品的一部分
学进去，于是金色大字变成袋面花纹、背景食材长进画面。所以必须先把袋子**单独抠出来**。

产出（默认写到 _refs/，上传到远端 ComfyUI 的 input/refs/ 即可被 --ref-images 引用）
------------------------------------------------------------------------------------
  prod_P1_front.png   裁掉外围背景的袋子本体，保留全部印刷细节（权威外观参考，首选）
  prod_P2_white.png   白底抠图版：轮廓与袋型最清晰，帮助模型聚焦主体
  prod_P3_canvas.png  按 9:16 生成画布比例留白摆好的版本（可选，构图引导用）
  _refs_preview.jpg   三张并排 + 边界标注，供人眼验收

用法
  python3 make_product_refs.py --src _product/mine/product_鲍汁红烧酱料_原图.jpg
  python3 make_product_refs.py --src xx.jpg --rect 62,62,686,963      # 手标袋子外接框
  python3 make_product_refs.py --src xx.jpg --no-grabcut              # 只裁框，不抠图
"""
import argparse
import os

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.abspath(__file__))
FONT = "/System/Library/Fonts/Hiragino Sans GB.ttc"


def grabcut_fg(bgr, rect, iters=6):
    """用 grabCut 抠出框内前景（袋子）。返回 uint8 掩膜 0/255。"""
    mask = np.zeros(bgr.shape[:2], np.uint8)
    bgd = np.zeros((1, 65), np.float64)
    fgd = np.zeros((1, 65), np.float64)
    cv2.grabCut(bgr, mask, rect, bgd, fgd, iters, cv2.GC_INIT_WITH_RECT)
    return np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype("uint8")


def clean_mask(fg, ksize=7, keep_largest=True):
    """形态学去毛刺 + 只保留最大连通域（去掉散落的小块，如被误判的食材）。"""
    k = np.ones((ksize, ksize), np.uint8)
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, k, iterations=2)
    fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, k, iterations=1)
    if keep_largest:
        n, lab, stats, _ = cv2.connectedComponentsWithStats(fg, 8)
        if n > 1:
            idx = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
            fg = np.where(lab == idx, 255, 0).astype("uint8")
    return fg


def bbox_of(mask, pad=6):
    ys, xs = np.where(mask > 0)
    if len(xs) == 0:
        return None
    h, w = mask.shape[:2]
    return (max(0, int(xs.min()) - pad), max(0, int(ys.min()) - pad),
            min(w, int(xs.max()) + 1 + pad), min(h, int(ys.max()) + 1 + pad))


def on_canvas(rgb, target_wh=(384, 672), margin=0.90):
    """把产品按比例摆到 9:16 画布中央（白底），用于构图引导。"""
    tw, th = target_wh
    h, w = rgb.shape[:2]
    s = min(tw * margin / w, th * margin / h)
    nw, nh = max(1, int(w * s)), max(1, int(h * s))
    im = Image.fromarray(rgb).resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGB", (tw, th), (242, 242, 242))
    canvas.paste(im, ((tw - nw) // 2, (th - nh) // 2))
    return np.array(canvas)


def make_sheet(items, out_path, title=""):
    ims = []
    for label, arr in items:
        im = Image.fromarray(arr).convert("RGB")
        orig = im.size
        im.thumbnail((460, 700), Image.LANCZOS)
        ims.append((label, im, orig))
    W = sum(i.width for _, i, _ in ims) + 16 * (len(ims) + 1)
    H = max(i.height for _, i, _ in ims) + 78
    sheet = Image.new("RGB", (W, H), (24, 24, 24))
    d = ImageDraw.Draw(sheet)
    try:
        f = ImageFont.truetype(FONT, 17)
        fb = ImageFont.truetype(FONT, 21)
    except Exception:
        f = fb = ImageFont.load_default()
    if title:
        d.text((14, 10), title, font=fb, fill=(255, 214, 110))
    x = 16
    for label, im, orig in ims:
        sheet.paste(im, (x, 60))
        d.rectangle([x - 1, 59, x + im.width, 60 + im.height], outline=(90, 90, 90))
        d.text((x + 2, 34), "%s  %dx%d" % (label, orig[0], orig[1]), font=f, fill=(200, 230, 200))
        x += im.width + 16
    sheet.save(out_path, quality=92)
    return sheet.size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out-dir", default=os.path.join(ROOT, "_refs"))
    ap.add_argument("--rect", default=None, help="袋子外接框 x,y,w,h（默认按常见详情页版面估算）")
    ap.add_argument("--no-grabcut", action="store_true", help="只按框裁剪，不做抠图")
    ap.add_argument("--prefix", default="prod")
    a = ap.parse_args()

    src = a.src if os.path.isabs(a.src) else os.path.join(ROOT, a.src)
    bgr = cv2.imread(src, cv2.IMREAD_COLOR)
    if bgr is None:
        raise SystemExit("✘ 读不到图片：%s" % src)
    H, W = bgr.shape[:2]
    print("源图 %dx%d  %s" % (W, H, os.path.relpath(src, ROOT)))

    # 袋子外接框：默认按「详情页袋子约占中间 62%~95%」估算
    if a.rect:
        x, y, w, h = [int(v) for v in a.rect.split(",")]
        rect = (x, y, w, h)
    else:
        x = int(W * 0.070); y = int(H * 0.055)
        w = int(W * 0.845); h = int(H * 0.880)
        rect = (x, y, w, h)
    print("袋子外接框 rect=(%d,%d,%d,%d)" % rect)

    os.makedirs(a.out_dir, exist_ok=True)
    out = []

    # ── P1：仅裁框（保留袋子本身，去掉顶部金大字与四角食材）────────────
    x, y, w, h = rect
    crop = bgr[y:y + h, x:x + w].copy()
    p1 = os.path.join(a.out_dir, "%s_P1_front.png" % a.prefix)
    cv2.imwrite(p1, crop)
    out.append(("P1 裁剪原袋", cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)))
    print("  ✔ %s  %dx%d" % (os.path.basename(p1), crop.shape[1], crop.shape[0]))

    # ── P2：白底抠图（轮廓/袋型最清晰）──────────────────────────────
    if a.no_grabcut:
        fg = np.full(bgr.shape[:2], 255, np.uint8)
    else:
        fg = grabcut_fg(bgr, rect)
        fg = clean_mask(fg)
    ratio = float((fg > 0).sum()) / float(fg.size)
    print("  前景占比 %.1f%%（合理区间约 25%%~85%%）" % (ratio * 100))
    if ratio < 0.12 or ratio > 0.95:
        print("  ⚠ 抠图置信度低 —— 建议用 --rect 手标袋子框，或加 --no-grabcut 只裁框")
    bb = bbox_of(fg, pad=4) or (x, y, x + w, y + h)
    x0, y0, x1, y1 = bb
    # ★ 底色用极浅灰 #F2F2F2 而不是纯白：这只袋子顶部有一条**白色挂带**，
    #   纯白底会把挂带"融解"掉，模型就学不到袋顶结构了。
    BG = 242
    white = np.full_like(bgr, BG)
    m3 = (fg[y0:y1, x0:x1] > 0)[:, :, None]
    white[y0:y1, x0:x1] = np.where(m3, bgr[y0:y1, x0:x1], BG)
    p2 = os.path.join(a.out_dir, "%s_P2_white.png" % a.prefix)
    cv2.imwrite(p2, white[y0:y1, x0:x1])
    out.append(("P2 白底抠图", cv2.cvtColor(white[y0:y1, x0:x1], cv2.COLOR_BGR2RGB)))
    print("  ✔ %s  %dx%d" % (os.path.basename(p2), x1 - x0, y1 - y0))

    # ── P3：9:16 画布留白版（构图引导）─────────────────────────────
    p3 = os.path.join(a.out_dir, "%s_P3_canvas.png" % a.prefix)
    c3 = on_canvas(cv2.cvtColor(white[y0:y1, x0:x1], cv2.COLOR_BGR2RGB), (384, 672))
    Image.fromarray(c3).save(p3)
    out.append(("P3 9:16画布", c3))
    print("  ✔ %s  %dx%d" % (os.path.basename(p3), c3.shape[1], c3.shape[0]))

    sheet = os.path.join(a.out_dir, "_refs_preview.jpg")
    print("  ✔ %s %s" % (os.path.basename(sheet),
                         make_sheet(out, sheet, "产品参考图就绪包 · Ref2VA（<Picture 1> 建议用 P1 或 P2）")))
    print("\n上传到远端 ComfyUI 的 input/refs/ 后，即可：")
    print("  python3 build_voice_workflow.py --shot 15 --ref-images refs/%s_P2_white.png"
          % a.prefix)


if __name__ == "__main__":
    main()
