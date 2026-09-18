#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v3 全量生产工作流生成器（Mode B · 按镜帧数 · 原声锁 · 直出 768×1344）。

  --list           打印全部工作流 key（供 bash 循环）
  --one KEY        打印单份工作流 JSON（stdout，由 shell 重定向落盘）
  --bundle         打印全部合并的 bundle JSON

key 命名：f1s01 / f2s25；执行序 = T2V(f1 全部) → T2V(f2) → I2V(f1) → I2V(f2)。
落盘用法（bash）：
  for k in $(python3 build_workflows_v3.py --list); do
    python3 build_workflows_v3.py --one $k > _remote/v3run/wf_$k.json
  done
"""
import argparse, json
from pathlib import Path

H3 = "/Users/hejianglong/Desktop/videoHub/h3-films"
TPL = H3 + "/_remote/v2prev_tpl"
REF_IMG = "refs/prod_P2_white.png"
FILMS = {
    "f1": ("film1", "film1-office"),
    "f2": ("film2", "film2-blinddate"),
}


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def build_one(fkey, no):
    film, fdir = FILMS[fkey]
    man = load(H3 + "/" + fdir + "/manifest_v2.json")
    lines = load(H3 + "/_lines_rhythm/" + film + "_shot_lines.json")
    w = next(x for x in lines["shots"] if x["no"] == no)
    s = next(x for x in man["shots"] if x["no"] == no)
    is_i2v = s["task_type"] == "ref2va"
    wf = load(TPL + ("/pg_B.api.json" if is_i2v else "/s16.api.json"))
    dur = w["frames"] / 24.0  # Mode B：窗口 = 镜帧数（24fps 栅格整数帧）
    wf["6"]["inputs"]["prompt"] = man["audio"]["preamble"] + s["prompt"]
    wf["6"]["inputs"]["width"], wf["6"]["inputs"]["height"] = 768, 1344
    wf["13"]["inputs"]["audio"] = s["audio_file"]
    wf["12"]["inputs"]["filename_prefix"] = "MiniMaxH3/v3run/%s" % s["file"].replace(
        "shot", fkey + "s")
    wf["9"]["inputs"]["noise_seed"] = man["seed"] + no
    wf["14"]["inputs"]["scene_duration_seconds"] = dur
    if is_i2v:
        wf["17"]["inputs"]["image"] = REF_IMG
    return wf


def all_keys():
    keys = []
    for phase in ("t2v", "i2v"):
        for fkey in ("f1", "f2"):
            film, fdir = FILMS[fkey]
            man = load(H3 + "/" + fdir + "/manifest_v2.json")
            want = "ref2va" if phase == "i2v" else "t2va"
            keys += ["%ss%02d" % (fkey, s["no"]) for s in man["shots"] if s["task_type"] == want]
    return keys


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--one")
    ap.add_argument("--bundle", action="store_true")
    a = ap.parse_args()
    if a.list:
        print("\n".join(all_keys()))
    elif a.one:
        print(json.dumps(build_one(a.one[0:2], int(a.one[3:])),
                         ensure_ascii=False, indent=1))
    elif a.bundle:
        print(json.dumps({k: build_one(k[0:2], int(k[2:])) for k in all_keys()},
                         ensure_ascii=False))
