#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v3.1 细切重剪计划（stdout，由 bash 循环执行 ffmpeg）：
  film no t0_gen dur_gen t0_src dur_src
每个 v3 窗按「原片窗内细切点的相对节奏」切成子镜：
  画面 = 生成的 shotNN.mp4 同比例切段（Mode B 生成时长=窗长，天然对齐）
  原声 = 参考片对应子窗原声（音画同步）
子镜最短 0.6s，更近的切点丢弃（闪切合并）。
"""
import json

CUTS = {
    "film1": "/Users/hejianglong/Desktop/videoHub/videos/douyin-ad/shots/shots.json",
    "film2": "/Users/hejianglong/Desktop/videoHub/videos/douyin-ad-2/shots/shots.json",
}
MIN_SUB = 0.6

for film in ("film1", "film2"):
    cuts = json.load(open(CUTS[film]))["shots"]
    lines = json.load(open("/Users/hejianglong/Desktop/videoHub/h3-films/_lines_rhythm/"
                           + film + "_shot_lines.json", encoding="utf-8"))
    for w in lines["shots"]:
        L = w["t1"] - w["t0"]
        gen_len = w["frames"] / 24.0
        inner = [c["end"] for c in cuts if w["t0"] + 0.3 < c["end"] < w["t1"] - 0.3]
        rel = [(x - w["t0"]) / L for x in inner]
        bounds = [0.0] + [r for i, r in enumerate(rel)
                          if r - (rel[i - 1] if i else 0) > MIN_SUB / L
                          and MIN_SUB / L < r < 1 - MIN_SUB / L] + [1.0]
        for i in range(len(bounds) - 1):
            a, b = bounds[i], bounds[i + 1]
            print(film, w["no"],
                  "%.3f" % (a * gen_len), "%.3f" % ((b - a) * gen_len),
                  "%.3f" % (w["t0"] + a * L), "%.3f" % ((b - a) * L))
