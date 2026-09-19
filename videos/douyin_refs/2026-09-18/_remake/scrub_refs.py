#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""参考帧文字清洗：把原片关键帧里的「硬字幕 / 时间戳 / 竖排标题 / 水印」抹掉。

为什么必须做：
  实测 dy1_s003 生成图把原片字幕「往后别再说你是我儿子」原样复刻出来了；
  dy3_s001 生成图把左缘竖排标题「顾婉宁女儿」也复刻了。
  只裁底部 10% 不管用——字幕坐在 ~77% 高度、竖排标题贴左缘，都不在裁剪区内。
  而一旦启用 first_frame（精确第 0 帧）锁构图，这些字会 100% 出现在成片首帧。

做法：分区检测「带描边的亮字 / 高饱和彩字」→ 只对检出块做重度高斯模糊 + 去饱和。
只掩蔽检出区域，避免误伤面部。
"""
import os, sys, json, glob
import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "/Users/jianglong/Desktop/videoHub/videos/douyin_refs/2026-09-18"
FILMS = {"01_报恩": "7661613126736204025",
         "02_继母": "7686341460064787045",
         "03_挑食": "7664454812574337402"}

# 需要防硬字幕：先裁底部（原片字幕在 ~77%，所以裁 10% 不够 → 改裁 6% 保留构图，靠掩蔽解决）
OUT_SRC = f"{HERE}/scrub_src"      # 清洗后的原始比例帧
OUT_REF = f"{HERE}/full_ref2"      # 768x1344 参考图（ref_images 用）
OUT_FIRST = f"{HERE}/full_first"   # 768x1344 首帧（first_frame 用）
OUT_DBG = f"{HERE}/_scrub_dbg"

# 检测分区 (x0,x1,y0,y1) 归一化
ZONES = [
    ("sub",   0.00, 1.00, 0.62, 0.95),   # 底部大字幕
    ("stamp", 0.00, 0.28, 0.00, 0.07),   # 左上时间戳/平台角标
    ("ltitle",0.00, 0.13, 0.00, 0.50),   # 左缘竖排标题
    ("rtitle",0.87, 1.00, 0.00, 0.50),   # 右缘竖排标题
    ("wmk",   0.60, 1.00, 0.86, 1.00),   # 右下水印
]

def box_mean(a, k):
    """积分图快速盒均值"""
    p = np.pad(a, ((1, 0), (1, 0)), mode="edge")
    c = p.cumsum(0).cumsum(1)
    H, W = a.shape
    y0 = np.clip(np.arange(H) - k // 2, 0, H)
    y1 = np.clip(np.arange(H) + k // 2 + 1, 0, H)
    x0 = np.clip(np.arange(W) - k // 2, 0, W)
    x1 = np.clip(np.arange(W) + k // 2 + 1, 0, W)
    return (c[np.ix_(y1, x1)] - c[np.ix_(y0, x1)] - c[np.ix_(y1, x0)] + c[np.ix_(y0, x0)]) \
        / np.maximum((y1 - y0)[:, None] * (x1 - x0)[None, :], 1)

def detect(img):
    """返回检出块列表 [(x0,x1,y0,y1,score,name)]（像素坐标）"""
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    H, W = a.shape[:2]
    lum = 0.299 * a[:, :, 0] + 0.587 * a[:, :, 1] + 0.114 * a[:, :, 2]
    sat = a.max(2) - a.min(2)
    bg = box_mean(lum, max(9, H // 40))
    contrast = lum - bg
    # 带描边的亮字：亮 + 明显比邻域亮
    bright_txt = (lum > 168) & (contrast > 22)
    # 高饱和彩字（黄/红标题）
    color_txt = (sat > 70) & (lum > 110) & (contrast > 16)
    txt = bright_txt | color_txt

    hits = []
    for name, x0, x1, y0, y1 in ZONES:
        sx0, sx1 = int(x0 * W), int(x1 * W)
        sy0, sy1 = int(y0 * H), int(y1 * H)
        sub = txt[sy0:sy1, sx0:sx1]
        if sub.size == 0:
            continue
        rows = sub.mean(1)
        cols = sub.mean(0)
        # 行/列密度阈值（字幕是大字，单行密度高）
        rth = 0.055 if name == "sub" else 0.045
        hot_rows = rows > rth
        dens = float(sub.mean())
        if hot_rows.sum() >= 2 or (name != "sub" and dens > 0.06):
            ys = np.where(hot_rows)[0]
            if len(ys) >= 2:
                ry0, ry1 = sy0 + int(ys.min()), sy0 + int(ys.max()) + 1
            else:
                ry0, ry1 = sy0, sy1
            # 列范围
            hot_cols = cols > rth * 0.6
            xs = np.where(hot_cols)[0]
            if len(xs) >= 2:
                rx0, rx1 = sx0 + int(xs.min()), sx0 + int(xs.max()) + 1
            else:
                rx0, rx1 = sx0, sx1
            # 竖向标题：扩展到整个候选纵向范围
            pad_x = int(0.015 * W); pad_y = int(0.012 * H)
            rx0 = max(0, rx0 - pad_x); rx1 = min(W, rx1 + pad_x)
            ry0 = max(0, ry0 - pad_y); ry1 = min(H, ry1 + pad_y)
            score = float(dens)
            hits.append((rx0, rx1, ry0, ry1, score, name))
    return hits, txt

def scrub(img, hits):
    """对检出块做重度模糊+去饱和"""
    if not hits:
        return img, 0
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    H, W = a.shape[:2]
    out = a.copy()
    for x0, x1, y0, y1, sc, name in hits:
        # 放大取样区以拿到周边背景，再重度模糊
        ex = int((x1 - x0) * 0.5); ey = int((y1 - y0) * 1.6)
        cx0 = max(0, x0 - ex); cx1 = min(W, x1 + ex)
        cy0 = max(0, y0 - ey); cy1 = min(H, y1 + ey)
        region = Image.fromarray(a[cy0:cy1, cx0:cx1].astype(np.uint8))
        r = max(8, int((y1 - y0) * 0.55))
        blur = np.asarray(region.filter(ImageFilter.GaussianBlur(r)), dtype=np.float32)
        # 轻度去饱和，避免彩字残影
        m = blur.mean(2, keepdims=True)
        blur = 0.35 * blur + 0.65 * m
        out[cy0:cy1, cx0:cx1] = blur
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)), len(hits)

def to_canvas(img, crop_bottom=0.94):
    """原始比例 → 768x1344（填充+中心裁切）"""
    H, W = img.height, img.width
    img = img.crop((0, 0, W, int(H * crop_bottom)))
    tw, th = 768, 1344
    s = max(tw / img.width, th / img.height)
    img = img.resize((max(1, round(img.width * s)), max(1, round(img.height * s))), Image.LANCZOS)
    l = (img.width - tw) // 2; t = (img.height - th) // 2
    return img.crop((l, t, l + tw, t + th))

def main():
    for d in (OUT_SRC, OUT_REF, OUT_FIRST, OUT_DBG):
        os.makedirs(d, exist_ok=True)
    rows = json.load(open(f"{HERE}/shots_all.json", encoding="utf-8"))
    report = {}
    n_hit = 0; total = 0
    for film, lst in rows.items():
        vid = FILMS[film]
        tag = {"01_报恩": "dy1", "02_继母": "dy2", "03_挑食": "dy3"}[film]
        kfd = f"{BASE}/{vid}/keyframes"
        film_report = []
        for r in lst:
            total += 1
            nm = f"{tag}_s{r['index']:03d}"
            src = os.path.join(kfd, r["kf"])
            if not os.path.exists(src):
                print(f"  ✗ 缺帧 {nm} {r['kf']}"); continue
            img = Image.open(src)
            hits, tmap = detect(img)
            clean, n = scrub(img, hits)
            if n:
                n_hit += 1
            clean.save(f"{OUT_SRC}/{nm}.jpg", quality=95)
            to_canvas(clean).save(f"{OUT_REF}/{nm}.jpg", quality=95)
            to_canvas(clean).save(f"{OUT_FIRST}/{nm}.jpg", quality=95)
            if n:
                # 调试图：原图 + 检出框
                dbg = img.convert("RGB").copy()
                da = np.asarray(dbg).copy()
                for x0, x1, y0, y1, sc, zname in hits:
                    da[y0:y1, max(0, x0 - 2):min(da.shape[1], x1 + 2), 0] = 255
                    da[y0:y1, max(0, x0 - 2):min(da.shape[1], x1 + 2), 1] = 0
                    da[y0:y1, max(0, x0 - 2):min(da.shape[1], x1 + 2), 2] = 0
                Image.fromarray(da).save(f"{OUT_DBG}/{nm}_det.jpg", quality=88)
                Image.new("RGB", (dbg.width // 3 * 2 + 6, dbg.height // 3)).save(f"{OUT_DBG}/_tmp.jpg")
            film_report.append(dict(nm=nm, kf=r["kf"], faces=None,
                                    hits=[dict(zone=h[5], box=[int(v) for v in h[:4]], score=round(h[4], 3))
                                          for h in hits]))
        report[film] = film_report
        nh = sum(1 for x in film_report if x["hits"])
        print(f"[{film}] {len(film_report)} 帧，检出文字 {nh} 帧")
    json.dump(report, open(f"{HERE}/_scrub_report.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\n[✓] 共 {total} 帧，含文字 {n_hit} 帧 ({n_hit/total*100:.1f}%)")
    print(f"    清洗帧 → {OUT_SRC}\n    参考图 → {OUT_REF}\n    首帧   → {OUT_FIRST}\n    调试图 → {OUT_DBG}")

if __name__ == "__main__":
    main()
