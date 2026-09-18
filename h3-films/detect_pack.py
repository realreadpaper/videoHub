#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自动识别生成帧里的「空白产品袋」，输出袋面四边形 —— 产品贴图的定位器。

为什么能自动
------------
生成层的 prompt 强制包装袋是 `clean unprinted red field`（见 _product/PRODUCT.md），
所以袋子在画面里是一块**高饱和纯红**区域 —— 这是极强的颜色信号，比任何文字检测可靠。
扫描全部分镜即可自动找出「哪些镜里有产品袋」，批量生产不需要人工逐镜指定。

判据（四条同时满足）
--------------------
1. 红色连通域面积 ≥ min_area × 画面面积
2. 四边形填充率 ≥ min_fill（袋子是实心矩形，酱油/红布之类会碎）
3. 长宽比在 ar 范围内（袋面近似竖向矩形）
4. approxPolyDP 能收敛到 4 点（保留透视，不用 minAreaRect 的旋转矩形）

用法
----
  # 扫全部分镜，自动列出含产品袋的镜
  python3 detect_pack.py --shots _deliver/shots_film1 --per-shot 3
  # 单帧
  python3 detect_pack.py --frame xx.jpg --annotate out.jpg --json out.json
产物：标注图（四边形 + 序号 + 面积占比，供人眼 10 秒核对）+ JSON（quad 列表）
"""
import argparse
import glob
import json
import os
import subprocess
import tempfile

import cv2
import numpy as np

# 默认阈值（在片1 的 6 个产品镜上标定，见 _review/prod6/）
MIN_AREA = 0.012      # 面积占画面比例下限
MIN_FILL = 0.62       # 四边形填充率下限
ASPECT = (0.30, 1.40)  # 短边/长边 范围
MAX_EDGE = 0.06       # 轮廓内纹理密度上限（空袋 ≈0.01，红烧肉/生肉 ≥0.10）
MAX_QUAD_ERR = 0.003  # 四边形直线度误差上限（袋子边界是直线）
RED_LO1, RED_HI1 = (0, 80, 60), (12, 255, 255)     # 红（0° 附近）
RED_LO2, RED_HI2 = (168, 80, 60), (180, 255, 255)  # 红（180° 附近）


def grab(video, t):
    p = tempfile.mktemp(suffix=".png")
    subprocess.run(["ffmpeg", "-v", "error", "-ss", "%.3f" % t, "-i", video,
                    "-frames:v", "1", p, "-y"], capture_output=True)
    return p if os.path.exists(p) and os.path.getsize(p) > 0 else None


def red_mask(bgr):
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    m1 = cv2.inRange(hsv, np.array(RED_LO1, np.uint8), np.array(RED_HI1, np.uint8))
    m2 = cv2.inRange(hsv, np.array(RED_LO2, np.uint8), np.array(RED_HI2, np.uint8))
    m = cv2.bitwise_or(m1, m2)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k, iterations=2)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, k, iterations=1)
    return m


def order_quad(pts):
    """按 TL, TR, BR, BL 排序。"""
    pts = np.asarray(pts, dtype=np.float32).reshape(-1, 2)
    s = pts.sum(axis=1)
    d = (pts[:, 0] - pts[:, 1])
    return [pts[np.argmin(s)], pts[np.argmax(d)], pts[np.argmax(s)], pts[np.argmin(d)]]


def contour_features(c, q, W, H, m, edges):
    """算判别特征 —— 用来把「产品袋」从「红烧肉 / 生肉 / 不锈钢」里分出来。

    三个判据：
      quad_err   轮廓点到拟合四边形的平均距离 / 周长 —— 袋子边界是**直线**，误差极小；
                 肉块、酱汁边界是曲线，误差大一个量级。
      edge_ratio 轮廓内部 Canny 边缘密度 —— 空袋面是**纯平色块**，密度极低；
                 红烧肉/生肉有大量纹理。
      red_ratio  轮廓内部红色像素占比 —— 袋子主体是红的。
    """
    cpts = c.reshape(-1, 2).astype(np.float32)
    qn = np.asarray(q, np.float32)
    if len(cpts) < 4:
        return None
    peri = float(cv2.arcLength(c, True))
    ds = []
    for k in range(4):
        a1, a2 = qn[k], qn[(k + 1) % 4]
        v = a2 - a1
        L = float(np.linalg.norm(v))
        if L < 1e-6:
            continue
        dx = cpts[:, 0] - a1[0]
        dy = cpts[:, 1] - a1[1]
        ds.append(np.abs(v[0] * dy - v[1] * dx) / L)   # 二维叉积（np.cross 已不支持 2D）
    quad_err = float(np.min(np.stack(ds), axis=0).mean() / max(peri, 1)) if ds else 1.0

    mc = np.zeros((H, W), np.uint8)
    cv2.drawContours(mc, [c], -1, 255, -1)
    mc = cv2.erode(mc, np.ones((11, 11), np.uint8), iterations=1)
    n = int((mc > 0).sum())
    if n <= 0:
        return None
    edge_ratio = float(((edges > 0) & (mc > 0)).sum()) / n
    red_ratio = float(((m > 0) & (mc > 0)).sum()) / n
    return {"quad_err": round(quad_err, 5), "edge_ratio": round(edge_ratio, 4),
            "red_ratio": round(red_ratio, 3)}


def find_packs(bgr, min_area=MIN_AREA, min_fill=MIN_FILL, aspect=ASPECT,
               max_edge=None, max_quad_err=None):
    H, W = bgr.shape[:2]
    m = red_mask(bgr)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 60, 160)
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in cnts:
        a = cv2.contourArea(c)
        if a < min_area * W * H:
            continue
        peri = cv2.arcLength(c, True)
        ap = None
        for eps in (0.015, 0.02, 0.03, 0.045, 0.06):
            ap = cv2.approxPolyDP(c, eps * peri, True)
            if len(ap) == 4:
                break
        if ap is None or len(ap) != 4:
            ap = cv2.boxPoints(cv2.minAreaRect(c)).reshape(-1, 1, 2)
        q = order_quad(ap)
        qa = cv2.contourArea(np.array(q, np.float32))
        fill = a / qa if qa > 0 else 0.0
        w = float(np.linalg.norm(np.array(q[1]) - np.array(q[0])))
        h = float(np.linalg.norm(np.array(q[3]) - np.array(q[0])))
        ratio = min(w, h) / max(w, h, 1e-6)
        if fill < min_fill or not (aspect[0] <= ratio <= aspect[1]):
            continue
        rec = {
            "quad": [[round(float(x), 1), round(float(y), 1)] for x, y in q],
            "area": round(float(a), 1),
            "area_ratio": round(float(a / (W * H)), 4),
            "fill": round(float(fill), 3),
            "aspect": round(float(ratio), 3),
            "w": round(w, 1), "h": round(h, 1),
        }
        f = contour_features(c, q, W, H, m, edges)
        if f:
            rec.update(f)
        if max_edge is not None and rec.get("edge_ratio", 1) > max_edge:
            continue
        if max_quad_err is not None and rec.get("quad_err", 1) > max_quad_err:
            continue
        out.append(rec)
    out.sort(key=lambda r: -r["area"])
    return out, m


def annotate(bgr, packs, tag=""):
    im = bgr.copy()
    colors = [(0, 255, 255), (255, 200, 0), (0, 255, 0), (255, 0, 255)]
    for i, p in enumerate(packs):
        q = np.array(p["quad"], np.int32)
        cv2.polylines(im, [q], True, colors[i % 4], 3)
        for j, (x, y) in enumerate(p["quad"]):
            cv2.circle(im, (int(x), int(y)), 7, colors[i % 4], -1)
            cv2.putText(im, "TL TR BR BL"[j * 2:j * 2 + 2], (int(x) + 9, int(y) - 9),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, colors[i % 4], 2)
        cx, cy = q.mean(axis=0)
        cv2.putText(im, "#%d %d%%" % (i + 1, round(p["area_ratio"] * 100)),
                    (int(cx) - 60, int(cy)), cv2.FONT_HERSHEY_SIMPLEX, 0.9, colors[i % 4], 2)
    if tag:
        cv2.putText(im, tag, (10, 34), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 4)
        cv2.putText(im, tag, (10, 34), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
    return im


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--frame")
    g.add_argument("--shots")
    g.add_argument("--video")
    ap.add_argument("--per-shot", type=int, default=3, help="分镜模式：每镜抽几帧")
    ap.add_argument("--every", type=float, default=2.0, help="整片模式：每 N 秒一帧")
    ap.add_argument("--min-area", type=float, default=MIN_AREA)
    ap.add_argument("--min-fill", type=float, default=MIN_FILL)
    ap.add_argument("--max-edge", type=float, default=MAX_EDGE, help="轮廓内纹理密度上限")
    ap.add_argument("--max-quad-err", type=float, default=MAX_QUAD_ERR, help="四边形直线度误差上限")
    ap.add_argument("--no-filter", action="store_true", help="关闭边/直线度过滤（只看颜色候选）")
    ap.add_argument("--dump-features", action="store_true", help="打印候选特征，用于标定阈值")
    ap.add_argument("--annotate", default=None, help="单帧模式的标注图输出路径")
    ap.add_argument("--json", default=None, help="结果 JSON")
    ap.add_argument("--outdir", default="_review/pack_detect", help="批量模式的标注图目录")
    a = ap.parse_args()

    me = None if a.no_filter else a.max_edge
    mq = None if a.no_filter else a.max_quad_err

    def detect(bgr):
        return find_packs(bgr, a.min_area, a.min_fill, ASPECT, me, mq)

    def dump(packs):
        for j, pk in enumerate(packs):
            print("      #%d area=%5.1f%% fill=%.2f ar=%.2f qerr=%.5f edge=%.4f red=%.2f"
                  % (j + 1, pk["area_ratio"] * 100, pk["fill"], pk["aspect"],
                     pk.get("quad_err", -1), pk.get("edge_ratio", -1), pk.get("red_ratio", -1)))

    def emit(bgr, label, out_png):
        packs, _ = detect(bgr)
        cv2.imwrite(out_png, annotate(bgr, packs, label))
        return packs

    results = []
    if a.frame:
        bgr = cv2.imread(a.frame)
        packs = emit(bgr, os.path.basename(a.frame),
                     a.annotate or (os.path.splitext(a.frame)[0] + "_annot.jpg"))
        print(json.dumps(packs, ensure_ascii=False, indent=1))
        results = [{"source": a.frame, "packs": packs}]

    elif a.shots:
        os.makedirs(a.outdir, exist_ok=True)
        files = sorted(f for f in os.listdir(a.shots) if f.endswith(".mp4"))
        for fn in files:
            v = os.path.join(a.shots, fn)
            r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                "-of", "csv=p=0", v], capture_output=True, text=True)
            try:
                dur = float(r.stdout.strip())
            except ValueError:
                dur = 15.04
            best, bestp, bestt = None, None, None
            for k in range(a.per_shot):
                t = dur * (k + 1) / (a.per_shot + 1)
                p = grab(v, t)
                if not p:
                    continue
                bgr = cv2.imread(p)
                packs, _ = detect(bgr)
                os.unlink(p)
                if packs and (bestp is None or packs[0]["area_ratio"] > bestp[0]["area_ratio"]):
                    best, bestp, bestt = bgr, packs, t
            tag = fn.replace(".mp4", "")
            if a.dump_features:
                print("  %s" % tag)
                dump(bestp or [])
            if bestp:
                cv2.imwrite(os.path.join(a.outdir, "%s_annot.jpg" % tag),
                            annotate(best, bestp,
                                     "%s @%.1fs  %d pack" % (tag, bestt, len(bestp))))
                print("  ✔ %-12s 检出 %d 个袋面  最大占画面 %.1f%%  (t=%.1fs)"
                      % (tag, len(bestp), bestp[0]["area_ratio"] * 100, bestt))
            else:
                print("  ·  %-12s 无袋面" % tag)
            results.append({"id": tag, "t": bestt, "packs": bestp or []})

    else:
        os.makedirs(a.outdir, exist_ok=True)
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "csv=p=0", a.video], capture_output=True, text=True)
        dur = float(r.stdout.strip())
        t, idx = a.every / 2, 0
        while t < dur:
            p = grab(a.video, t)
            if p:
                bgr = cv2.imread(p)
                packs, _ = detect(bgr)
                os.unlink(p)
                idx += 1
                if packs:
                    cv2.imwrite(os.path.join(a.outdir, "t%07.1f_annot.jpg" % t),
                                annotate(bgr, packs, "t=%.1fs" % t))
                    print("  ✔ t=%7.1fs  %d 个袋面  最大 %.1f%%  镜%02d"
                          % (t, len(packs), packs[0]["area_ratio"] * 100, int(t // 15.0417) + 1))
                    results.append({"t": round(t, 2), "shot": int(t // 15.0417) + 1, "packs": packs})
            t += a.every
        print("扫描 %d 帧，命中 %d 帧" % (idx, len(results)))

    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"results": results}, f, ensure_ascii=False, indent=1)
        print("→ %s" % a.json)


if __name__ == "__main__":
    main()
