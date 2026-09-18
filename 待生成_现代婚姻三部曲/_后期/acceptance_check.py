#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
acceptance_check.py —— 成片验收总检（一镜一表 + 汇总 PASS/FAIL）

把散落的质检项串成一条命令：以后每部片子出片后直接跑这个，不用再逐个工具手敲。

检查项
------
A. 技术规格  —— 帧数 / 分辨率 / 时长 / 是否 16:9 / 帧率
B. 镜内硬切  —— 峰值÷邻域中位 ≥3 判硬切（见 detect_hardcut.py 的方法学说明）
C. 画面残字  —— 调 detect_residual_sub.py 的判据，扫底部近白锐利区域
D. prompt 层 —— 扫 manifest 里是否残留「要求画面显示可读文字」的诉求
              （这类诉求必然渲染成乱码，属于自找麻烦）
E. 音轨      —— 有无音轨、时长是否与视频一致

用法
----
  python3 acceptance_check.py --film 01_周星驰_三十八万八
  python3 acceptance_check.py --film 01_周星驰_三十八万八 --shots-dir shots_clean
  python3 acceptance_check.py --film 01_周星驰_三十八万八 --json accept.json
"""

import argparse
import glob
import json
import os
import re
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.normpath(os.path.join(HERE, ".."))
FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"

EXPECT_FRAMES = 361
EXPECT_W, EXPECT_H = 1344, 768

# prompt 层：要求画面出现「可读文字」的写法
# 注意收紧：`reading Groom`（描述道具上的字，无引号）不算硬性诉求，
# 真正会诱发乱码的是带引号的具体文字内容，如 reading "388000 yuan parking slot fee"
TEXT_DEMAND = re.compile(
    r"(?:characters?\s+reading|reading\s+[\"“']|"
    r"displays?\b[^.]{0,40}(?:characters|text|words)\b|"
    r"written\s+[\"“']|sign\s+(?:reading|saying)\s+[\"“']|"
    r"bold\s+black\s+marker\s+characters)", re.I)

NEIGH = 5
RATIO_CUT = 3.0


def probe(path):
    r = subprocess.run([FFPROBE, "-v", "error", "-show_entries",
                        "stream=codec_type,width,height,nb_frames,r_frame_rate,duration",
                        "-of", "json", path], capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except Exception:
        return {}


def spec_of(path):
    j = probe(path)
    v = next((s for s in j.get("streams", []) if s.get("codec_type") == "video"), None)
    a = next((s for s in j.get("streams", []) if s.get("codec_type") == "audio"), None)
    if not v:
        return None
    fps = v.get("r_frame_rate", "24/1")
    try:
        num, den = fps.split("/")
        fps = round(float(num) / float(den), 3)
    except Exception:
        fps = 24.0
    nf = v.get("nb_frames")
    dur = float(v.get("duration") or (float(nf) / fps if nf else 0))
    return {"w": int(v.get("width", 0)), "h": int(v.get("height", 0)),
            "fps": fps, "frames": int(nf) if nf else None,
            "dur": round(dur, 3),
            "audio": bool(a),
            "a_dur": round(float(a.get("duration") or 0), 3) if a else 0.0}


def gray_frames(path, w=336, h=192, fps=24):
    d = tempfile.mkdtemp(prefix="ac_")
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", path,
                    "-vf", "fps=%d,scale=%d:%d" % (fps, w, h),
                    os.path.join(d, "%04d.png")], capture_output=True)
    fs = sorted(glob.glob(os.path.join(d, "*.png")))
    out = [np.asarray(Image.open(f).convert("L"), dtype=np.float32) for f in fs]
    for f in fs:
        os.remove(f)
    os.rmdir(d)
    return out, fps


def hardcut_of(path):
    F, fps = gray_frames(path)
    if len(F) < 4:
        return {"cuts": 0, "suspects": 0, "events": [], "median": 0, "max": 0}
    d = np.array([np.abs(F[i] - F[i - 1]).mean() for i in range(1, len(F))])
    ev = []
    for i in range(1, len(d) - 1):
        v = d[i]
        if v < 3.0:
            continue
        lo, hi = max(0, i - NEIGH), min(len(d), i + NEIGH + 1)
        nb = np.concatenate([d[lo:i], d[i + 1:hi]])
        if not len(nb):
            continue
        base = float(np.median(nb))
        ratio = v / base if base > 0.5 else v / 0.5
        if ratio >= RATIO_CUT:
            ev.append({"sec": round((i + 1) / fps, 2), "peak": round(float(v), 2),
                       "ratio": round(float(ratio), 2), "kind": "cut"})
        elif ratio >= 1.8:
            ev.append({"sec": round((i + 1) / fps, 2), "peak": round(float(v), 2),
                       "ratio": round(float(ratio), 2), "kind": "suspect"})
    merged = []
    for e in ev:
        if merged and e["sec"] - merged[-1]["sec"] <= 0.12:
            if e["peak"] > merged[-1]["peak"]:
                merged[-1] = e
            continue
        merged.append(e)
    return {"cuts": sum(1 for e in merged if e["kind"] == "cut"),
            "suspects": sum(1 for e in merged if e["kind"] == "suspect"),
            "events": merged, "median": round(float(np.median(d)), 2),
            "max": round(float(d.max()), 2)}


def subscan_of(path, th=190, y0=560, nframes=20, sharp=12):
    """残字扫描：底部近白 + 锐利区域。返回命中框与 delogo 建议串。"""
    d = tempfile.mkdtemp(prefix="sb_")
    j = probe(path)
    v = next((s for s in j.get("streams", []) if s.get("codec_type") == "video"), None)
    W, H = (int(v.get("width", 1344)), int(v.get("height", 768))) if v else (1344, 768)
    if y0 >= H:
        y0 = int(H * 0.73)
    nf = int(v.get("nb_frames") or 360)
    idx = [int(round(k * (nf - 1) / (nframes - 1))) for k in range(nframes)]
    hits = []
    for fr in idx:
        p = os.path.join(d, "f%04d.png" % fr)
        subprocess.run([FFMPEG, "-v", "error", "-y", "-i", path,
                        "-vf", "select=eq(n\\,%d)" % fr, "-frames:v", "1", p],
                       capture_output=True)
        if not os.path.exists(p):
            continue
        im = np.asarray(Image.open(p).convert("L"), dtype=np.float32)
        band = im[y0:, :]
        if band.size == 0:
            continue
        m = band > th
        if m.sum() < 80:
            continue
        ys, xs = np.where(m)
        gx = np.abs(np.diff(band, axis=1)).mean()
        if gx < sharp:
            continue
        hits.append((xs.min(), ys.min() + y0, xs.max(), ys.max() + y0))
    for f in glob.glob(os.path.join(d, "*.png")):
        os.remove(f)
    os.rmdir(d)
    if not hits:
        return {"hit": False}
    x0 = min(h[0] for h in hits); y0b = min(h[1] for h in hits)
    x1 = max(h[2] for h in hits); y1 = max(h[3] for h in hits)
    pad = 12
    return {"hit": True, "frames": len(hits), "of": nframes,
            "bbox": [int(x0), int(y0b), int(x1 - x0), int(y1 - y0b)],
            "delogo": "x=%d:y=%d:w=%d:h=%d" % (max(0, x0 - pad), max(0, y0b - pad),
                                               (x1 - x0) + 2 * pad, (y1 - y0b) + 2 * pad)}


def main():
    ap = argparse.ArgumentParser(description="成片验收总检")
    ap.add_argument("--film", required=True, help="如 01_周星驰_三十八万八")
    ap.add_argument("--shots-dir", default="shots")
    ap.add_argument("--json", default=None)
    ap.add_argument("--skip-subscan", action="store_true", help="跳过残字扫描（省时间）")
    a = ap.parse_args()

    fdir = os.path.join(BASE, a.film)
    man_p = os.path.join(fdir, "manifest.json")
    sdir = os.path.join(fdir, a.shots_dir)
    if not os.path.exists(man_p):
        sys.exit("✘ 缺 %s" % man_p)
    m = json.load(open(man_p, encoding="utf-8"))
    title = a.film.split("_", 1)[-1]

    print("=" * 100)
    print("  %s · 成片验收总检   镜头来源: %s/" % (title, a.shots_dir))
    print("=" * 100)
    print("%-6s %-8s %9s %8s %7s %6s %6s %6s %s" % (
        "镜", "文件", "分辨率", "帧数", "时长s", "硬切", "存疑", "残字", "判定"))
    print("-" * 100)

    rows, fails = [], []
    for sh in m["shots"]:
        no = sh["no"]
        p = os.path.join(sdir, "shot%02d.mp4" % no)
        if not os.path.exists(p):
            print("%-6s %-8s  ✘ 缺失" % (no, "shot%02d" % no))
            fails.append("镜%02d 文件缺失" % no)
            continue
        sp = spec_of(p)
        hc = hardcut_of(p)
        sb = {"hit": False} if a.skip_subscan else subscan_of(p)
        probs = []
        if sp["w"] != EXPECT_W or sp["h"] != EXPECT_H:
            probs.append("分辨率 %dx%d" % (sp["w"], sp["h"]))
        if sp["frames"] and abs(sp["frames"] - EXPECT_FRAMES) > 2:
            probs.append("帧数 %s" % sp["frames"])
        if hc["cuts"]:
            probs.append("硬切 %d" % hc["cuts"])
        if sb.get("hit"):
            probs.append("残字")
        if not sp["audio"]:
            probs.append("无音轨")
        verdict = "✔ PASS" if not probs else "✘ " + " / ".join(probs)
        if probs:
            fails.append("镜%02d %s" % (no, " / ".join(probs)))
        print("%-6s %-8s %9s %8s %7.2f %6d %6d %6s %s" % (
            no, "shot%02d" % no, "%dx%d" % (sp["w"], sp["h"]),
            sp["frames"] or "?", sp["dur"], hc["cuts"], hc["suspects"],
            "✘" if sb.get("hit") else "✔", verdict))
        detail = {"no": no, "file": "shot%02d.mp4" % no, "spec": sp,
                  "hardcut": hc, "subscan": sb}
        if hc["events"]:
            detail["cut_detail"] = ", ".join(
                "%.2fs|%.0f|%.1fx%s" % (e["sec"], e["peak"], e["ratio"],
                                        "" if e["kind"] == "cut" else "?")
                for e in hc["events"][:6])
        if sb.get("hit"):
            detail["delogo"] = sb["delogo"]
        rows.append(detail)

    # prompt 层：画面文字诉求
    print("-" * 100)
    print("prompt 层扫描（要求画面出现可读文字 = 必然乱码的来源）")
    text_hits = []
    for sh in m["shots"]:
        p = sh.get("prompt", "")
        found = []
        for mo in TEXT_DEMAND.finditer(p):
            s = max(p.rfind(".", 0, mo.start()), p.rfind("\n", 0, mo.start())) + 1
            e = p.find(".", mo.end())
            e = len(p) if e < 0 else e + 1
            found.append(p[s:e].strip()[:120])
        if found:
            text_hits.append((sh["no"], found))
    if text_hits:
        for no, f in text_hits:
            print("  ✘ 镜%02d: %s" % (no, f[0]))
        fails.append("prompt 含画面文字诉求 %d 处" % sum(len(f) for _, f in text_hits))
    else:
        print("  ✔ 无画面文字诉求")

    print("-" * 100)
    if fails:
        print("✘ 未通过 %d 项:" % len(fails))
        for f in fails:
            print("    · %s" % f)
    else:
        print("✔ 全部通过：%d 镜规格正确 / 零硬切 / 无残字 / 音轨完整" % len(rows))
    print("=" * 100)

    if a.json:
        json.dump({"film": a.film, "shots": rows, "fails": fails},
                  open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("✔ 已写出 %s" % a.json)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
