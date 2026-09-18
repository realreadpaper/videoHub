#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
打印原声提取计划（stdout：film no t0 dur），由外层 bash 循环执行 ffmpeg：
  python3 plan_audio_orig.py | while read film no t0 dur; do ... done
产物 32kHz 立体声 PCM，补静音到 15.0833s 整窗（Mode A）。
"""
import json

H3 = "/Users/hejianglong/Desktop/videoHub/h3-films"
for film in ("film1", "film2"):
    lines = json.load(open(H3 + "/_lines_rhythm/" + film + "_shot_lines.json", encoding="utf-8"))
    for w in lines["shots"]:
        print(film, int(w["no"]), "%.3f" % w["t0"], "%.3f" % (w["t1"] - w["t0"]))
