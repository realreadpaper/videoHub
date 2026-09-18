#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v2 关键分镜预览 · 构建 5 份 API 工作流（写入 _remote/v2prev/，路径字面量）

  d_f1s01.json  片1镜01  T2V 草稿 384×672（s16 模板 · fl2va + audio-lock）
  d_f2s03.json  片2镜03  T2V 草稿 384×672（同上）
  x_f2s35.json  片2镜35  Ref2VA 直出 768×1344（pg_B 模板 · ref2va UNET + 参考图）
  r_f1s01.json  片1镜01  LTX 精修 768×1344（api_s13 模板，吃上面草稿）
  r_f2s03.json  片2镜03  同上
"""
import json
from pathlib import Path

H3 = "/Users/hejianglong/Desktop/videoHub/h3-films"
TPL = H3 + "/_remote/v2prev_tpl"
OUTDIR = H3 + "/_remote/v2prev"
PREAMBLE = (
    "<Audio 1> holds the voice of the person speaking on screen: a clear Mandarin Chinese line. "
    "Keep the visual timing, phrasing and rhythm locked to <Audio 1>, with natural matching "
    "mouth movement and body performance. Follow the shot description below exactly.\n\n")

# tag -> (film, 镜号, v1 manifest 里的 seed)
JOBS = {
    "f1s01": ("film1", 1), "f2s03": ("film2", 3), "f2s35": ("film2", 35),
}


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def prompt_of(film, no):
    m = load(H3 + ("/film1-office/manifest_v2.json" if film == "film1"
                   else "/film2-blinddate/manifest_v2.json"))
    s = next(x for x in m["shots"] if x["no"] == no)
    return s["prompt"], s["seconds"], s["exec_tier"], m["seed"]


def build_draft(tag, film, no):
    wf = load(TPL + "/s16.api.json")
    pr, secs, tier, seed = prompt_of(film, no)
    wf["6"]["inputs"]["prompt"] = PREAMBLE + pr
    wf["6"]["inputs"]["width"], wf["6"]["inputs"]["height"] = 384, 672
    wf["13"]["inputs"]["audio"] = "tts_dry/v2prev/%s_dry.wav" % tag
    wf["12"]["inputs"]["filename_prefix"] = "MiniMaxH3/v2prev/%s_draft" % tag
    wf["9"]["inputs"]["noise_seed"] = seed + no
    return wf


def build_direct(tag, film, no):
    wf = load(TPL + "/pg_B.api.json")
    pr, secs, tier, seed = prompt_of(film, no)
    wf["6"]["inputs"]["prompt"] = PREAMBLE + pr
    wf["6"]["inputs"]["width"], wf["6"]["inputs"]["height"] = 768, 1344
    wf["17"]["inputs"]["image"] = "refs/prod_P2_white.png"
    wf["13"]["inputs"]["audio"] = "tts_dry/v2prev/%s_dry.wav" % tag
    wf["12"]["inputs"]["filename_prefix"] = "MiniMaxH3/v2prev/%s_direct768" % tag
    wf["9"]["inputs"]["noise_seed"] = seed + no
    return wf


def build_refine(tag, film, no):
    wf = load(TPL + "/api_s13.json")
    pr, secs, tier, seed = prompt_of(film, no)
    wf["1"]["inputs"]["file"] = "drafts/v2prev/%s_draft.mp4" % tag
    wf["3"]["inputs"]["target_width"], wf["3"]["inputs"]["target_height"] = 768, 1344
    wf["12"]["inputs"]["text"] = pr
    wf["20"]["inputs"]["filename_prefix"] = "MiniMaxH3/v2prev/%s_refined" % tag
    return wf


def main():
    outs = {
        "d_f1s01.json": build_draft("f1s01", *JOBS["f1s01"]),
        "d_f2s03.json": build_draft("f2s03", *JOBS["f2s03"]),
        "x_f2s35.json": build_direct("f2s35", *JOBS["f2s35"]),
        "r_f1s01.json": build_refine("f1s01", *JOBS["f1s01"]),
        "r_f2s03.json": build_refine("f2s03", *JOBS["f2s03"]),
    }
    names = [
        "/Users/hejianglong/Desktop/videoHub/h3-films/_remote/v2prev/d_f1s01.json",
        "/Users/hejianglong/Desktop/videoHub/h3-films/_remote/v2prev/d_f2s03.json",
        "/Users/hejianglong/Desktop/videoHub/h3-films/_remote/v2prev/x_f2s35.json",
        "/Users/hejianglong/Desktop/videoHub/h3-films/_remote/v2prev/r_f1s01.json",
        "/Users/hejianglong/Desktop/videoHub/h3-films/_remote/v2prev/r_f2s03.json",
    ]
    for name, wf in zip(names, outs.values()):
        Path(name).write_text(json.dumps(wf, ensure_ascii=False, indent=1), encoding="utf-8")
    for tag in JOBS:
        pr, secs, tier, seed = prompt_of(*JOBS[tag])
        print("%s | %.2fs | %s | prompt %d chars" % (tag, secs, tier, len(pr)))


if __name__ == "__main__":
    main()
