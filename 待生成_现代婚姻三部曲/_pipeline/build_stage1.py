#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""照抄 v3：参数直接写进 API JSON（无 --set）。生成 stage1 草稿工作流。
用法： python3 build_stage1.py --all | --one f1s02
"""
import argparse, json, os, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL  = "/Users/hejianglong/Desktop/videoHub/h3-films/_remote/v2prev_tpl/s16.api.json"
OUT  = os.path.join(ROOT, "_pipeline", "wf")
DIRS = {"01_周星驰_三十八万八": "f1", "02_姜文_老子不娶了": "f2", "03_奉俊昊_加名之夜": "f3"}

# 原声锁声明（照抄 v3 的 audio.preamble）
PREAMBLE = ("<Audio 1> carries the original soundtrack of this scene: the actors' "
            "real voices, ambience and music. Keep the visual timing, phrasing, lip "
            "movement and performance locked to <Audio 1> exactly. Follow the shot "
            "description below exactly.\n\n")

def load(p): return json.load(open(p, encoding="utf-8"))

def build(fkey, no, man, wf_out):
    s = next(x for x in man["shots"] if x["no"] == no)
    wf = load(TPL)
    dur = s["h3_length"] / 24.0
    wf["6"]["inputs"]["prompt"] = PREAMBLE + s["prompt"]
    wf["6"]["inputs"]["width"], wf["6"]["inputs"]["height"] = 384, 672
    wf["13"]["inputs"]["audio"] = s["audio_file"]           # 原声锁
    wf["14"]["inputs"]["scene_duration_seconds"] = dur      # 逐镜时长（17n+5 栅格）
    wf["12"]["inputs"]["filename_prefix"] = "MiniMaxH3/trilogy/%s_s%02d" % (fkey, no)
    wf["9"]["inputs"]["noise_seed"] = man["seed"] + no * 7
    json.dump(wf, open(wf_out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return dur

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--one", help="f1s02 形式")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    keys = []
    for d, fk in DIRS.items():
        man = load(os.path.join(ROOT, d, "manifest.json"))
        for s in man["shots"]:
            keys.append("%ss%02d" % (fk, s["no"]))
    if a.list:
        print("\n".join(keys)); return
    want = keys if a.all else ([a.one] if a.one else [])
    for k in want:
        fk, no = k[:2], int(k[3:])
        d = [k2 for k2, v in DIRS.items() if v == fk][0]
        man = load(os.path.join(ROOT, d, "manifest.json"))
        dur = build(fk, no, man, os.path.join(OUT, "wf_%s.json" % k))
        print("  %s  %.3fs  ->  wf_%s.json" % (k, dur, k))
    open(os.path.join(OUT, "keys.txt"), "w").write("\n".join(want) + "\n")
    print("\n生成 %d 份，keys 已写入 keys.txt" % len(want))

main()
