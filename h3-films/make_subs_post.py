#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""后处理版字幕器 —— 按**实际成片时间轴**重算外挂字幕。

为什么不能用 make_subs.py
-------------------------
make_subs.py 假设「每镜等长」（(镜号-1) × 单镜时长 + 镜内时间）。
后处理一旦裁尾 / 提速对齐原片（见 trim_shots.py），每镜时长就各不相同，
再用等长公式会**逐镜累积漂移**，最后一条字幕能差好几秒。

时间轴口径
----------
    绝对时间 = Σ(前 i-1 镜的实际时长) + 镜内时间 / 速度倍率

数据来源：
  · trim_shots.py 产出的 trim_report.json（每镜 keep 时长 + speed 倍率）
  · _tts/<film>/shotNN_lines.json（每句的镜内落点，TTS 实测）

用法
----
  python3 make_subs_post.py --film film1 --trim _post/trim_report.json \
      --out-dir _post --stem "良心面试_食堂红烧（原片复刻）_全片"
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
TTS = os.path.join(ROOT, "_tts")

SPEAKER_NAME = {"1": "顾董", "2": "小林", "S1": "顾董", "S2": "小林"}


def ts_srt(t):
    h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    # 注意括号：("%02d..." % (...)).replace(...) —— 少了外层括号会把 replace 作用到 tuple 上
    return ("%02d:%02d:%06.3f" % (h, m, s)).replace(".", ",")


def ts_vtt(t):
    h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return "%02d:%02d:%06.3f" % (h, m, s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--film", default="film1")
    ap.add_argument("--trim", required=True, help="trim_shots.py 的 trim_report.json")
    ap.add_argument("--out-dir", default="_post")
    ap.add_argument("--stem", required=True, help="输出文件名（不含扩展名）")
    ap.add_argument("--speaker", action="store_true", help="台词前加角色名")
    ap.add_argument("--fps-safe", type=float, default=0.02,
                    help="字幕相对画面提前量（秒），避免卡在画面切换点上")
    a = ap.parse_args()

    rep = json.load(open(a.trim, encoding="utf-8"))
    speed = float(rep.get("speed", 1.0))
    plan = {int(p["shot"]): p for p in rep["plan"]}

    # 累计镜首时间
    starts, acc = {}, 0.0
    for n in sorted(plan):
        starts[n] = acc
        acc += float(plan[n]["keep"])

    cues = []
    for n in sorted(plan):
        lp = os.path.join(TTS, a.film, "shot%02d_lines.json" % n)
        if not os.path.exists(lp):
            print("  ⚠ 缺 %s，跳过低镜台词" % lp)
            continue
        d = json.load(open(lp, encoding="utf-8"))
        lines = d["lines"] if isinstance(d, dict) and "lines" in d else d
        keep = float(plan[n]["keep"])
        for ln in lines:
            st = starts[n] + ln["t"] / speed
            en = starts[n] + (ln["t"] + ln["dur"]) / speed
            en = min(en, starts[n] + keep)          # 不越过本镜末尾
            if en - st < 0.2:
                continue
            txt = ln["text"].strip()
            if a.speaker:
                sp = SPEAKER_NAME.get(str(ln.get("speaker", "")).strip())
                if sp:
                    txt = "%s：%s" % (sp, txt)
            cues.append((max(0.0, st - a.fps_safe), en, txt))

    cues.sort(key=lambda c: c[0])
    os.makedirs(a.out_dir, exist_ok=True)
    srt = os.path.join(a.out_dir, a.stem + ".srt")
    vtt = os.path.join(a.out_dir, a.stem + ".vtt")

    with open(srt, "w", encoding="utf-8") as f:
        for i, (st, en, tx) in enumerate(cues, 1):
            f.write("%d\n%s --> %s\n%s\n\n" % (i, ts_srt(st), ts_srt(en), tx))
    with open(vtt, "w", encoding="utf-8") as f:
        f.write("WEBVTT\n\n")
        for i, (st, en, tx) in enumerate(cues, 1):
            f.write("%d\n%s --> %s\n%s\n\n" % (i, ts_vtt(st), ts_vtt(en), tx))

    last = max(c[1] for c in cues) if cues else 0.0
    print("✔ %d 条字幕 ｜ 速度 %.4f× ｜ 末句收于 %.2fs ｜ 片长 %.2fs" % (
        len(cues), speed, last, acc))
    print("   %s" % srt)
    print("   %s" % vtt)
    if last > acc + 0.5:
        print("✘ 末句时间超出片长，时间轴有误", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
