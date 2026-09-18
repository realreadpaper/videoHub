#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""逐帧产品贴图引擎 —— 把真产品图贴到生成画面里的袋面上（零 GPU）。

为什么要逐帧而不是一张静态 quad
-------------------------------
H3 生成的镜头里袋子会移动、被手遮挡、随镜头推近放大（实测 shot15 袋面在镜内位移
可达数百像素，shot18 从人物手持切到袋面特写）。静态 quad 一贴就露馅。

定位策略（每帧，三级降级）
--------------------------
  1. **检测**：detect_pack 找红色四边形候选，取与「参考 quad」四角平均距离最小者；
     距离 ≤ tol_detect 即接受。（袋面完整时实测 qerr≈0.003，非常可靠）
  2. **光流**：检测不到（遮挡 / 曝光跳变）→ 用 LK 光流从上一帧追踪四个角点；
     位移 ≤ tol_track 即接受。
  3. **不贴**：两级都失败 → 该帧保持原样（宁可少贴，不可贴歪）。

参考 quad 每帧更新 → 天然跟随袋子运动；进入/离开贴图时段时做 fade 淡入淡出，
避免硬切观感。

音频**原样直通**（-c:a copy），画质 crf 16，不做任何音画同步改动。

用法
----
  python3 overlay_product.py --tracks tracks_film1.json [--shots 13,15,18] [--dry-run]
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from importlib.util import module_from_spec, spec_from_file_location

_sp = spec_from_file_location("dp", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                "detect_pack.py"))
dp = module_from_spec(_sp)
_sp.loader.exec_module(dp)

LK = dict(winSize=(41, 41), maxLevel=3,
          criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 40, 0.005))


def quad_dist(a, b):
    return float(np.mean(np.linalg.norm(np.asarray(a, float) - np.asarray(b, float), axis=1)))


def zone_red_ratio(bgr, quad):
    """quad 区域内的红色像素占比 —— 用来确认「这里仍然是袋面」而不是漂到别处。

    没有这道门会出事故：袋子离开画面后，若背景静止，LK 光流会"成功追踪"到不存在的
    袋子（角点位移≈0，通过位移阈值），结果把产品图贴到人物身上。
    """
    m = dp.red_mask(bgr)
    mask = np.zeros(m.shape, np.uint8)
    cv2.fillPoly(mask, [np.asarray(quad, np.int32)], 255)
    n = int((mask > 0).sum())
    return float(((m > 0) & (mask > 0)).sum()) / n if n else 0.0


def shade(quad, cx, cy, k):
    """把 quad 绕自身中心缩放到 k 倍（用于 fade 时的轻微收缩，避免边缘硬边）。"""
    q = np.asarray(quad, float)
    c = q.mean(axis=0)
    return (c + (q - c) * k).tolist()


def warp_product(frame_rgb, product, crop, quad, opacity=1.0, keep_highlight=True, thr=200):
    """透视贴图。frame_rgb / 返回均为 PIL.Image（RGB）。"""
    from PIL import ImageDraw, ImageFilter
    W, H = frame_rgb.size
    prod = product.crop(tuple(crop))
    pw, ph = prod.size
    A, B = [], []
    src = [(0, 0), (pw, 0), (pw, ph), (0, ph)]
    for (u, v), (x, y) in zip(src, quad):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); B.append(u)
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y]); B.append(v)
    coeffs = tuple(np.linalg.solve(np.array(A, float), np.array(B, float)).tolist())
    warped = prod.transform((W, H), Image.PERSPECTIVE, coeffs, Image.BICUBIC)

    pts = np.asarray(quad, float)
    c = pts.mean(axis=0)
    shrunk = [tuple(p - (p - c) / max(float(np.linalg.norm(p - c)), 1e-6) * 2) for p in pts]
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).polygon(shrunk, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(2))
    if opacity < 1.0:
        mask = mask.point(lambda v: int(v * opacity))
    out = Image.composite(warped, frame_rgb, mask)

    if keep_highlight:
        f = np.asarray(frame_rgb).astype(np.float32)
        o = np.asarray(out).astype(np.float32)
        lum = f.mean(axis=2)
        hit = np.clip((lum - thr) / max(1.0, 255 - thr), 0, 1)
        hit = np.asarray(Image.fromarray((hit * 255).astype(np.uint8))
                         .filter(ImageFilter.GaussianBlur(1.5)), dtype=np.float32) / 255.0
        o = 255.0 - (255.0 - o) * (1.0 - hit[..., None] * 0.75)
        out = Image.fromarray(np.clip(o, 0, 255).astype(np.uint8))
    return out


def process_shot(src, dst, cfg, product, crop, args):
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        sys.exit("打不开 %s" % src)
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    lo, hi = cfg["range"]
    fade = cfg.get("fade", 0.35)
    ref = None if cfg.get("seed") == "auto" else [list(map(float, p)) for p in cfg["seed"]]
    lost, reset_after = 0, cfg.get("reset_after", 45)
    seed_qerr = cfg.get("seed_qerr", 0.02)
    min_red = cfg.get("min_red", 0.25)
    max_track = cfg.get("max_track", 14)
    track_run = 0
    tol_d = cfg.get("tol_detect", 55.0)
    tol_t = cfg.get("tol_track", 26.0)
    keep_hl = cfg.get("keep_highlight", True)
    opacity_cap = cfg.get("opacity", 1.0)

    tmp = tempfile.mktemp(suffix=".mp4")
    pr = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
         "-s", "%dx%d" % (W, H), "-r", "%.6f" % fps, "-i", "-",
         "-an", "-c:v", "libx264", "-preset", "medium", "-crf", str(args.crf),
         "-pix_fmt", "yuv420p", tmp, "-y"], stdin=subprocess.PIPE)

    prev_gray, prev_quad = None, None
    stat = {"frames": 0, "seed": 0, "detect": 0, "track": 0, "skip": 0, "out_of_range": 0}
    for i in range(total):
        ok, bgr = cap.read()
        if not ok:
            break
        stat["frames"] += 1
        t = i / fps
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        out_bgr = bgr

        if lo <= t <= hi:
            packs, _ = dp.find_packs(bgr, cfg.get("min_area", args.min_area),
                                     cfg.get("min_fill", args.min_fill))
            if ref is None:
                # 自动取种：时段内第一个「边界足够直」的候选（只有袋面完整帧才通过）
                cands = [p for p in packs if p.get("quad_err", 9) <= seed_qerr]
                if cands:
                    pk = min(cands, key=lambda r: r.get("quad_err", 9))
                    ref = [list(map(float, q)) for q in pk["quad"]]
                    stat["seed"] += 1
            if ref is not None:
                cur = ref
                best, bd = None, 1e9
                for pk in packs:
                    d = quad_dist(pk["quad"], cur)
                    if d < bd:
                        bd, best = d, pk["quad"]
                mode = None
                if best is not None and bd <= tol_d:
                    ref = [list(map(float, q)) for q in best]
                    mode = "detect"
                elif prev_gray is not None and prev_quad is not None:
                    q0 = np.asarray(prev_quad, np.float32).reshape(-1, 1, 2)
                    q1, st, _ = cv2.calcOpticalFlowPyrLK(prev_gray, gray, q0, None, **LK)
                    if q1 is not None and st is not None and st.ravel().all():
                        cand = q1.reshape(-1, 2)
                        if quad_dist(cand, prev_quad) <= tol_t:
                            ref = cand.tolist()
                            mode = "track"
                if mode:
                    # ① 红度校验：袋面区域必须仍是「红」的，否则判定漂移
                    if min_red > 0 and zone_red_ratio(bgr, ref) < min_red:
                        mode = None
                    elif mode == "track":
                        # ② 纯追踪不得连续太久（会缓慢漂移），超限强制重新检测
                        track_run += 1
                        if track_run > max_track:
                            mode, ref, track_run = None, None, 0
                    else:
                        track_run = 0
                if mode:
                    # fade：时段两端淡入淡出 + 轻微收缩，观感更自然
                    edge = min(t - lo, hi - t)
                    op = opacity_cap * (1.0 if edge >= fade else max(0.0, edge / fade))
                    q = ref if op >= 0.999 else shade(ref, *np.mean(ref, axis=0),
                                                     1.0 - (1 - op) * 0.02)
                    out_bgr = np.array(warp_product(
                        Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)),
                        product, crop, q, opacity=op, keep_highlight=keep_hl))[:, :, ::-1].copy()
                    stat[mode] += 1
                    lost = 0
                else:
                    stat["skip"] += 1
                    lost += 1
                    if lost >= reset_after:
                        ref = None      # 连续失败太久（袋子离开 / 被遮挡）→ 允许重新取种
                        lost = 0
                prev_quad = ref
            else:
                stat["skip"] += 1
        else:
            stat["out_of_range"] += 1

        pr.stdin.write(out_bgr.tobytes())
        prev_gray = gray

    cap.release()
    pr.stdin.close()
    pr.wait()

    subprocess.run(["ffmpeg", "-v", "error", "-i", tmp, "-i", src,
                    "-map", "0:v", "-map", "1:a?", "-c:v", "copy", "-c:a", "copy",
                    "-movflags", "+faststart", dst, "-y"], check=True)
    os.unlink(tmp)
    return stat


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tracks", required=True, help="tracks JSON（含 product/crop/tracks 配置）")
    ap.add_argument("--shots", default=None, help="只处理这些镜，如 13,15,18")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--crf", type=int, default=16)
    ap.add_argument("--min-area", type=float, default=0.006)
    ap.add_argument("--min-fill", type=float, default=0.55)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    cfg = json.load(open(a.tracks, encoding="utf-8"))
    shots_dir = cfg["shots_dir"]
    out_dir = a.out_dir or cfg.get("out_dir") or os.path.join(os.path.dirname(shots_dir),
                                                              "shots_overlay")
    product = Image.open(cfg["product"]).convert("RGB")
    crop = [int(v) for v in cfg["crop"]]
    only = set(int(x) for x in a.shots.split(",")) if a.shots else None

    print("产品图: %s  crop=%s" % (cfg["product"], crop))
    print("输出目录: %s" % out_dir)
    if not a.dry_run:
        os.makedirs(out_dir, exist_ok=True)

    rows = []
    for k, sc in sorted(cfg["tracks"].items(), key=lambda x: int(x[0])):
        n = int(k)
        if only and n not in only:
            continue
        src = os.path.join(shots_dir, "shot%02d.mp4" % n)
        if not os.path.exists(src):
            print("  ✘ 缺 %s" % src); continue
        dst = os.path.join(out_dir, "shot%02d.mp4" % n)
        if a.dry_run:
            print("  [dry] shot%02d 时段 %.1f–%.1fs  seed=%s" % (n, sc["range"][0], sc["range"][1], sc["seed"]))
            continue
        st = process_shot(src, dst, sc, product, crop, a)
        eff = st["detect"] + st["track"]
        print("  ✔ shot%02d  检测 %3d 帧 / 追踪 %3d 帧 / 跳过 %3d 帧  有效覆盖 %.0f%%"
              % (n, st["detect"], st["track"], st["skip"],
                 eff / max(1, st["detect"] + st["track"] + st["skip"]) * 100))
        rows.append({"shot": n, **st})
    # 未配置的镜原样复制 —— 输出目录必须始终是「完整 N 镜」，
    # 否则下一阶段（trim_shots）拿不到全部分镜，会直接漏掉整片内容。
    if not a.dry_run:
        copied = 0
        for f in sorted(os.listdir(shots_dir)):
            if not f.endswith(".mp4"):
                continue
            dst = os.path.join(out_dir, f)
            if os.path.exists(dst):
                continue
            subprocess.run(["ffmpeg", "-v", "error", "-i", os.path.join(shots_dir, f),
                            "-c", "copy", dst, "-y"], check=True)
            copied += 1
        n_mp4 = len([x for x in os.listdir(out_dir) if x.endswith(".mp4")])
        print("  ·  未配置的镜已原样复制 %d 个；输出目录共 %d 镜" % (copied, n_mp4))

    if rows:
        with open(os.path.join(out_dir, "_overlay_report.json"), "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=1)
        print("→ %s/_overlay_report.json" % out_dir)


if __name__ == "__main__":
    main()
