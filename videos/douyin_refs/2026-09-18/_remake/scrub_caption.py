#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""成片字幕条清理：H3 会凭「抖音短剧帧 + 中文语音」的领域先验，自己在下半幅画一条乱码字幕，
与参考图里有没有字无关（参考图已确认干净）。三种 prompt 措辞都压不住 → 改在出片后清。

做法：
  1. 逐帧在下半幅找「亮字 + 深描边」像素，取并集 → 定位字幕条包围盒
  2. 逐帧用各自的笔画掩码做 cv2.inpaint（只补笔画，不动背景）
  3. 重新编码 + 原音轨
"""
import os, sys, json, subprocess, shutil, argparse
import numpy as np, cv2

HERE = os.path.dirname(os.path.abspath(__file__))
FF = "/usr/local/bin/ffmpeg"
K5 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
# 字幕条可能出现的高度带（归一化）
BAND = (0.60, 0.98)


def frame_mask(f, band):
    h, w = f.shape[:2]
    y0, y1 = int(band[0] * h), int(band[1] * h)
    af = f[y0:y1].astype(np.float32)
    lum = 0.299 * af[:, :, 2] + 0.587 * af[:, :, 1] + 0.114 * af[:, :, 0]  # BGR
    dark = (lum < 100).astype(np.uint8)
    bright = (lum > 175).astype(np.uint8)
    m = ((bright & cv2.dilate(dark, K5, 1)) | (dark & cv2.dilate(bright, K5, 1))).astype(np.uint8) * 255
    full = np.zeros((h, w), np.uint8)
    full[y0:y1] = m
    return full, (y0, y1)


def process(src, dst, report=None):
    cap = cv2.VideoCapture(src)
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    frames = []
    masks = []
    rows_hot = None
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        m, (y0, y1) = frame_mask(fr, BAND)
        frames.append(fr)
        masks.append(m)
        hot = (m[y0:y1] > 0).mean(1) > 0.004
        rows_hot = hot if rows_hot is None else (rows_hot | hot)
    cap.release()
    if not frames:
        return None
    h, w = frames[0].shape[:2]
    y0 = int(BAND[0] * h)
    idx = np.where(rows_hot)[0]
    if len(idx) < 4:
        return dict(src=os.path.basename(src), n=len(frames), action="skip", why="未检出字幕条")
    by0, by1 = y0 + int(idx.min()) - 6, y0 + int(idx.max()) + 7
    cover = float(len(idx)) / rows_hot.size
    if cover < 0.02 or len(idx) < 8:
        return dict(src=os.path.basename(src), n=len(frames), action="skip", why=f"带过窄({len(idx)}行)")
    tmp = "/tmp/_capfix"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)
    filled = 0
    for i, (fr, m) in enumerate(zip(frames, masks)):
        mm = np.zeros((h, w), np.uint8)
        mm[by0:by1] = m[by0:by1]
        if (mm > 0).sum() > 12:
            mm = cv2.dilate(mm, K5, 2)
            fr = cv2.inpaint(fr, mm, 3, cv2.INPAINT_TELEA)
            filled += 1
        cv2.imwrite(f"{tmp}/{i:05d}.png", fr)
    subprocess.run([FF, "-v", "error", "-y", "-framerate", f"{fps:.6f}", "-i", f"{tmp}/%05d.png",
                    "-i", src, "-map", "0:v", "-map", "1:a?", "-c:v", "libx264", "-crf", "19",
                    "-pix_fmt", "yuv420p", "-c:a", "copy", "-shortest", dst], check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    return dict(src=os.path.basename(src), n=len(frames), action="fixed",
                band=[int(by0), int(by1)], rows=int(len(idx)), frames_filled=filled)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--indir", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--suffix", default="_00001_.mp4")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    fs = sorted(f for f in os.listdir(a.indir) if f.endswith(".mp4"))
    if a.limit:
        fs = fs[:a.limit]
    rep = []
    for i, f in enumerate(fs):
        out = os.path.join(a.outdir, f)
        try:
            r = process(os.path.join(a.indir, f), out)
            rep.append(r or dict(src=f, action="fail"))
            print(f"[{i+1}/{len(fs)}] {f} -> {rep[-1].get('action')} {rep[-1].get('why','')}", flush=True)
        except Exception as e:
            print(f"[{i+1}/{len(fs)}] {f} 失败 {e}", flush=True)
            rep.append(dict(src=f, action="error", why=str(e)))
    json.dump(rep, open(os.path.join(a.outdir, "_caption_report.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    fx = sum(1 for r in rep if r["action"] == "fixed")
    print(f"\n[✓] {len(rep)} 个片段：清理 {fx}，跳过 {len(rep)-fx}")


if __name__ == "__main__":
    main()
