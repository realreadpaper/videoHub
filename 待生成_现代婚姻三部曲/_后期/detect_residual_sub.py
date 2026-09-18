#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
残字扫描器 v3 —— 检查成片/分镜里是否残留模型自发烧的中文字幕（几乎全是乱码）

## 为什么需要它
H3 会在台词镜随机烧上中文硬字幕，而且**几乎全是乱码**（实测样本：
「太阳眼常升起」「走趿——!」「请把属于我的那份分还恰」）。
Prompt 里写了 `no subtitles` 也压不住。交付前必须逐镜过一遍，
不能靠肉眼抽帧（《不可剥夺》就是这么误判的）。

## 两版失败教训（判据演进）
* **v1「稳定高亮 AND 交集」**：
  - 01 部 shot03 是**白色婚纱特写**——大面积静止高亮 → 误报 3 处"残字"；
  - 02 部 shot08 的字幕是**浮动的**（模型做了下沉效果），逐帧位置不同，
    AND 交集直接把它消成 0 → 漏报。**两头都错。**
* **v2「描边比」**：真字幕黑描边环带占 0.21，白婚纱也有 0.13，区分度不够。

## v3 判据（当前，已验证区分度干净）
对**每一帧独立**检测，再跨帧聚类（容忍浮动）：
  ① 形状：横向长条，宽高比 >= 3.5，填充率 5%~55%（文字是稀疏笔画行）
  ② **锐利度**：白像素处的图像梯度中位数 >= 12
     —— 文字笔画是 1~2px 内 255↔0 的硬边（实测中位数 33~34）；
        白婚纱/白墙/逆光高光是平滑渐变（实测中位数 2~3）。**这是决定性判据。**
  ③ 时间持续：同一 x 区域在 >= 3 帧重复出现（字幕是持续的，随机闪光不算）

## 用法
  python3 detect_residual_sub.py <shots目录> [--th 190] [--y0 560] [--frames 20]
  需 PIL + numpy：
  /Users/hejianglong/.workbuddy/binaries/python/envs/default/bin/python

输出命中的 bbox 与可直接复制的 `delogo=` 参数。
**命中不等于一定是字幕**（锐利的白色道具文字也可能命中），务必按 bbox 抽帧人眼确认。
"""
import argparse, glob, os, subprocess, tempfile
import numpy as np
from PIL import Image

GRAD_MIN = 12.0      # 锐利度阈值（平滑高光 2~3，文字 33~34）
MIN_PX = 200         # 白像素太少统计不稳


def ffprobe_dur(mp4):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=duration", "-of", "csv=p=0", mp4],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip().split(",")[0])
    except Exception:
        return 15.0


def bands_of(mask, grad, min_px=MIN_PX, min_w=150, grad_min=GRAD_MIN):
    """单帧：找像字幕的横向行带，按「填充率 + 锐利度」过滤"""
    rows = mask.sum(axis=1)
    bands, cur = [], None
    for y, c in enumerate(rows):
        if c >= 6:
            cur = [y, y] if cur is None else [cur[0], y]
        else:
            if cur and cur[1] - cur[0] >= 5:
                bands.append(tuple(cur))
            cur = None
    if cur and cur[1] - cur[0] >= 5:
        bands.append(tuple(cur))

    out = []
    for y1, y2 in bands:
        sub = mask[y1:y2 + 1, :]
        cols = np.where(sub.sum(axis=0) > 0)[0]
        if len(cols) == 0:
            continue
        x1, x2 = int(cols.min()), int(cols.max())
        bw, bh = x2 - x1 + 1, y2 - y1 + 1
        npx = int(sub.sum())
        fill = npx / float(bw * bh)
        if npx < min_px or bw < min_w or bw / max(1, bh) < 3.5 or not (0.05 <= fill < 0.55):
            continue
        msub = mask[y1:y2 + 1, x1:x2 + 1]
        gsub = grad[y1:y2 + 1, x1:x2 + 1][msub]
        if gsub.size == 0:
            continue
        gmed = float(np.median(gsub))
        if gmed >= grad_min:
            out.append((x1, y1, x2, y2, npx, fill, gmed))
    return out


def cluster(cands, nframes):
    """同一 x 区域在 >=3 帧重复出现 → 判定残字；y 取并集（容忍浮动字幕）"""
    groups = []
    for c in cands:
        placed = False
        for g in groups:
            ov = min(g["x2"], c[2]) - max(g["x1"], c[0])
            if ov > 0.4 * min(g["x2"] - g["x1"], c[2] - c[0]):
                g.update(x1=min(g["x1"], c[0]), y1=min(g["y1"], c[1]),
                         x2=max(g["x2"], c[2]), y2=max(g["y2"], c[3]),
                         gmax=max(g["gmax"], c[6]))
                g["f"].add(c[7])
                placed = True
                break
        if not placed:
            groups.append({"x1": c[0], "y1": c[1], "x2": c[2], "y2": c[3],
                           "gmax": c[6], "f": {c[7]}})
    return [g for g in groups if len(g["f"]) >= 3]


def scan(mp4, th, y0, nframes):
    d = ffprobe_dur(mp4)
    tmp = tempfile.mkdtemp()
    cands, nframe_used = [], 0
    for i in range(nframes):
        t = d * (i + 0.5) / nframes
        p = os.path.join(tmp, "f%03d.png" % i)
        subprocess.run(["ffmpeg", "-v", "error", "-ss", "%.2f" % t, "-i", mp4,
                        "-frames:v", "1", p, "-y"], capture_output=True)
        if not os.path.exists(p):
            continue
        nframe_used += 1
        a = np.asarray(Image.open(p).convert("RGB")).astype(np.float32)
        gray = a.mean(axis=2)
        gx = np.abs(np.diff(gray, axis=1, prepend=gray[:, :1]))
        gy = np.abs(np.diff(gray, axis=0, prepend=gray[:1, :]))
        grad = gx + gy
        m = (a[:, :, 0] > th) & (a[:, :, 1] > th) & (a[:, :, 2] > th)
        m[:y0, :] = False
        for b in bands_of(m, grad):
            cands.append(b + (i,))
        os.remove(p)
    os.rmdir(tmp)
    return cluster(cands, nframe_used), len(cands), nframe_used


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir", help="shots 目录或单个 mp4")
    ap.add_argument("--th", type=int, default=190, help="近白阈值")
    ap.add_argument("--y0", type=int, default=560, help="只看该 y 以下")
    ap.add_argument("--frames", type=int, default=20)
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(a.dir, "*.mp4"))) if os.path.isdir(a.dir) else [a.dir]
    print("残字扫描 v3 | %d 文件 | 近白阈值=%d | y0=%d | 抽帧=%d | 锐利度阈值=%.0f"
          % (len(files), a.th, a.y0, a.frames, GRAD_MIN))
    print("=" * 84)
    hits = 0
    for f in files:
        name = os.path.basename(f)
        groups, ncand, nf = scan(f, a.th, a.y0, a.frames)
        if groups:
            hits += 1
            print("  %-30s ✘ %d 处疑似残字（单帧候选 %d / %d 帧）" % (name, len(groups), ncand, nf))
            for g in groups:
                w, h = g["x2"] - g["x1"] + 1, g["y2"] - g["y1"] + 1
                print("        x=%d y=%d w=%d h=%d  出现 %d/%d 帧  锐利度中位=%.1f"
                      % (g["x1"], g["y1"], w, h, len(g["f"]), nf, g["gmax"]))
                print("        delogo=x=%d:y=%d:w=%d:h=%d"
                      % (max(0, g["x1"] - 12), max(0, g["y1"] - 10), w + 24, h + 20))
        else:
            print("  %-30s ✔ 干净" % name)
    print("=" * 84)
    print("结论：%d/%d 个文件命中，请按 bbox 抽帧人眼确认（命中的也可能是锐利白色道具文字）"
          % (hits, len(files)))


if __name__ == "__main__":
    main()
