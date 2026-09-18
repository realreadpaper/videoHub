#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v2 关键分镜预览 · 干声生成（3 镜）

复用 make_tts 的合成/裁静音/atempo/混装，但把台词压进「镜长」窗口（v2 一镜短于
15.08s，Mode A 生成整窗 15.08s 后期裁剪，台词必须落在镜长内）。

用法（必须用装了 edge-tts 的解释器）：
  /Users/hejianglong/.workbuddy/binaries/python/envs/default/bin/python preview_dry.py
产出：_tts/v2prev/<tag>_dry.wav（15.0833s 窗，台词在前 <镜长> 秒内）
"""
import json, os, sys, tempfile

sys.path.insert(0, "/Users/hejianglong/Desktop/videoHub/h3-films")
import make_tts as M  # noqa: E402

H3 = "/Users/hejianglong/Desktop/videoHub/h3-films"
OUT = H3 + "/_tts/v2prev"
LINES = {
    "film1": H3 + "/_lines_rhythm/film1_shot_lines.json",
    "film2": H3 + "/_lines_rhythm/film2_shot_lines.json",
}
# tag -> (film, 镜号)
SHOTS = {"f1s01": ("film1", 1), "f2s03": ("film2", 3), "f2s35": ("film2", 35)}


def dry_for_tag(tag, film, no):
    data = json.load(open(LINES[film], encoding="utf-8"))
    shot = next(s for s in data["shots"] if s["no"] == no)
    secs = shot["seconds"]
    rows = [{"speaker": sp, "text": tx} for sp, tx in shot["dialogue"]]
    n = len(rows)
    vmap = M.VOICES.get(film, {})
    rate = "+40%"

    tmp = tempfile.mkdtemp(prefix="v2prev_%s_" % tag)
    try:
        M.synth_all(rows, rate, tmp, no, vmap)
        durs = []
        for i, r in enumerate(rows):
            clip = "f%02d.wav" % i
            durs.append(M.trim_clip(os.path.join(tmp, r["mp3"]), os.path.join(tmp, clip)))
            r["clip"] = clip
        # 台词必须全部落在镜长内：span = 镜长 - 镜首留白 - 尾垫
        span = max(secs - M.LEAD - 0.15, 0.8)
        floor = span - M.MIN_GAP * max(n - 1, 0)
        total, tempo = sum(durs), 1.0
        if total > floor and floor > 0:
            tempo = total / floor
            for i, r in enumerate(rows):
                out = "a%02d.wav" % i
                durs[i] = M.atempo_clip(os.path.join(tmp, r["clip"]), os.path.join(tmp, out), tempo)
                r["clip"] = out
            total = sum(durs)
        gap = min(max((span - total) / (n - 1), M.MIN_GAP), M.MAX_GAP) if n > 1 else 0.0
        t = M.LEAD
        for i, r in enumerate(rows):
            r["t"] = round(t, 3)
            r["dur"] = round(durs[i], 3)
            t += durs[i] + gap
        end = max((r["t"] + r["dur"] for r in rows), default=0.0)
        os.makedirs(OUT, exist_ok=True)
        out_wav = os.path.join(OUT, tag + "_dry.wav")
        M.assemble(rows, tmp, out_wav)
        print("[%s] 镜%02d %.2fs | %d 句 | 语速 %s | atempo %.3f | 台词占位至 %.2fs（镜长 %.2f 内=%s）"
              % (tag, no, secs, n, rate, tempo, end, secs, end <= secs + 1e-6))
        for r in rows:
            print("    %.2fs +%5.2fs %s：%s" % (r["t"], r["dur"], r["speaker"],
                                                r["text"][:40] + ("…" if len(r["text"]) > 40 else "")))
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    for tag, (film, no) in SHOTS.items():
        dry_for_tag(tag, film, no)
