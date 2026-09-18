#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
重跑：f1s01 / f2s03 改 T2V 一键直出 768×1344（fl2va + audio-lock，不走精修）。
换新 seed（+7000 偏移）重抽，规避草稿阶段的伪字幕。
产出 _remote/v2prev/xd_f1s01.json / xd_f2s03.json
"""
import json
from pathlib import Path

H3 = "/Users/hejianglong/Desktop/videoHub/h3-films"
TPL = H3 + "/_remote/v2prev_tpl"
PREAMBLE = (
    "<Audio 1> holds the voice of the person speaking on screen: a clear Mandarin Chinese line. "
    "Keep the visual timing, phrasing and rhythm locked to <Audio 1>, with natural matching "
    "mouth movement and body performance. Follow the shot description below exactly.\n\n")
JOBS = {"f1s01": ("film1", 1), "f2s03": ("film2", 3)}


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def prompt_of(film, no):
    m = load(H3 + ("/film1-office/manifest_v2.json" if film == "film1"
                   else "/film2-blinddate/manifest_v2.json"))
    s = next(x for x in m["shots"] if x["no"] == no)
    return s["prompt"], m["seed"]


def build(tag, film, no):
    wf = load(TPL + "/s16.api.json")  # fl2va + audio-lock 模板（已验证路径）
    pr, seed = prompt_of(film, no)
    wf["6"]["inputs"]["prompt"] = PREAMBLE + pr
    wf["6"]["inputs"]["width"], wf["6"]["inputs"]["height"] = 768, 1344  # 直出 768
    wf["13"]["inputs"]["audio"] = "tts_dry/v2prev/%s_dry.wav" % tag
    wf["12"]["inputs"]["filename_prefix"] = "MiniMaxH3/v2prev/%s_direct768" % tag
    wf["9"]["inputs"]["noise_seed"] = seed + no + 7000  # 换 seed 重抽
    return wf


def main():
    Path("/Users/hejianglong/Desktop/videoHub/h3-films/_remote/v2prev/xd_f1s01.json").write_text(
        json.dumps(build("f1s01", *JOBS["f1s01"]), ensure_ascii=False, indent=1), encoding="utf-8")
    Path("/Users/hejianglong/Desktop/videoHub/h3-films/_remote/v2prev/xd_f2s03.json").write_text(
        json.dumps(build("f2s03", *JOBS["f2s03"]), ensure_ascii=False, indent=1), encoding="utf-8")
    for tag in JOBS:
        pr, seed = prompt_of(*JOBS[tag])
        print("%s | direct768 | prompt %d chars | seed %d" % (tag, len(pr), seed + JOBS[tag][1] + 7000))


if __name__ == "__main__":
    main()
