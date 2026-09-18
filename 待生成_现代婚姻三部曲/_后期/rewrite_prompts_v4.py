#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rewrite_prompts_v4.py —— 把 v3 的「三段式时间轴」压成「单段连续叙述」

为什么还要再改（v3 → v4）
--------------------------
v3 已把「到点切镜头」的写法清掉（删 `At 00:XX.XXX,`、加 single-continuous 锁定语、
首段交代人物入画），01~05 镜实测零硬切 ✔。

但 06/07/08 三镜仍各剩 1 处硬切，且都落在段落边界上：

    镜06  8.62s  MAE 47.4 (邻域 12~15)  ratio 3.6x   ← 巷子→车边，空间跳越大
    镜07  7.71s  MAE 61.5 (邻域 2~5)    ratio 22.8x  ← [05-10] 段内
    镜08  5.54s  MAE 43.9 (邻域 0.1~0.4) ratio 68.3x ← 静止远景→剥橙子，最刺眼

观察：`[00:00–00:05] [00:05–00:10] [00:10–00:15]` 这套**分段标记本身就是
「这里换镜头」的强暗示**——即便正文写了 single continuous，模型仍按段切。
旁证：旧版《三十八万八》shot01 用的是**单段无时间轴** prompt，实测零硬切、
最大帧差仅 9.2。v3 虽然在段首加了「same unbroken take」，但分段骨架还在。

v4 做法（只改 06/07/08）
------------------------
把三段时间轴**彻底压成一段连续叙述**，动作靠「先…接着…然后…」的语序串起来，
不留任何分段标记、不留任何时刻刻度。内容、主体、对白、环境音、配乐一字不动，
只把 [[段落]] 的墙拆掉。

用法
----
  python3 rewrite_prompts_v4.py --src 01_周星驰_三十八万八/manifest.json \
                               --out 01_周星驰_三十八万八/manifest_v4.json \
                               --shots 6,7,8
  python3 rewrite_prompts_v4.py ... --diff     # 只看摘要
"""

import argparse
import json
import os
import re
import sys

TAIL = ("cinematic 16:9 widescreen, ARRI Alexa look, shallow depth of field, fine film grain, "
        "naturalistic lighting, photorealistic, no subtitles, no captions, no on-screen text, "
        "no watermark, no logo.")

LOCK4 = ("One continuous unbroken take, no cuts, no shot changes, no montage, no scene "
         "transitions — a single camera move held from the first frame to the last.")

BODY4 = {}

# ---------------------------------------------------------------- 镜06
# 原 [00-05] 巷子跑 / [05-10] 到车边推父亲入座 / [10-15] 绕车、上车、开走
BODY4[6] = """Wide dynamic tracking shot, the camera flying backward ahead of the running subjects down a narrow tenement alley: <Subject 1> (S1), jacket unbuttoned and tie loosened, firmly grasps the arm of <Subject 2> (S2) and pulls him along, the two of them brushing past stunned bridesmaids and relatives who stand frozen like statues on either side, and as they run the mouth of the alley and a dusty vintage white 2005 sedan parked there swing into view; <Subject 1> (S1) reaches the car, wrenches the door open, bundles <Subject 2> (S2) into the passenger seat, straightens up and yells at the sky with exhilaration: <d>[Chinese] "走！爸，我带你去看真正的海！"</d> then dives into the driver's seat and slams the door, the engine catching, and the camera swings in one smooth arc around the front of the car as the tires spin over red firecracker paper and the white sedan lurches forward and accelerates away down the alley, the camera holding on the departing car."""

# ---------------------------------------------------------------- 镜07
# 原 [00-05] 车内双人 / [05-10] S1 大笑喊话 / [10-15] 摇到 S2
BODY4[7] = """Medium shot inside the cabin of a moving white sedan, the camera mounted low on the dashboard with subtle road vibration and framing both front seats: golden afternoon sunlight floods through fully rolled-down windows, a ferocious headwind whipping <Subject 1> (S1)'s black hair and tossing his red necktie over his shoulder while <Subject 2> (S2) sits beside him quietly watching the road ahead; <Subject 1> (S1) grips the worn steering wheel with one hand, throws his head back laughing with untamed liberation, and hollers into the wind: <d>[Chinese] "爸，三十八万八省下来，够咱们加满一千箱油！"</d> and the camera then drifts gently across the dashboard from the driver's side to the passenger side, settling on <Subject 2> (S2) whose wrinkled face slowly softens from bewilderment into a relieved, peaceful smile while an old cassette tape spins in the dashboard deck between them."""

# ---------------------------------------------------------------- 镜08
# 原 [00-05] 静态远景（"camera fully static at first" 是硬切诱因） / [05-10] 剥橙子 / [10-15] 咬橙子拉远
BODY4[8] = """Medium long shot on an elevated plateau roadside overlook at sunset, the camera already drifting in an extremely slow continuous push-in that never stops: a majestic snow-capped mountain range is bathed in blazing orange-magenta twilight glow, and on the gravel below a dusty white sedan is parked with <Subject 1> (S1) and <Subject 2> (S2) leaning shoulder-to-shoulder against its warm hood, both of them fully inside the frame from the start; <Subject 2> (S2) uses calloused thumbs to peel a bright juicy orange, offering a fresh crescent slice up toward his son's lips and murmuring tenderly: <d>[Chinese] "甜不甜？"</d> and <Subject 1> (S1) bites into the orange slice, a silent tear rolling down his grinning cheek, while he whispers softly: <d>[Chinese] "甜透了，爸。"</d> the camera then reverses its motion and draws slowly back out until the two figures become a small warm silhouette against the deep glowing dusk, holding there on the last frame."""

SOUND_PREFIX = "overall_soundscape:"
MUSIC_PREFIX = "non_diegetic_music:"


def split_prompt(p):
    i = p.index(SOUND_PREFIX)
    j = p.index(MUSIC_PREFIX)
    head_part = p[:i]
    m = re.match(r"\s*([a-z_]+:)\s*\n", head_part)
    header = m.group(1) if m else "integrated_multimodal_description:"
    return header, p[i:j].rstrip(), p[j:].rstrip()


def build(orig, no):
    header, sound, music = split_prompt(orig)
    return "%s\n%s %s\n\n%s\n\n%s" % (header, LOCK4, BODY4[no].strip(),
                                      sound, music)


def check(old, new, no):
    probs = []
    # 时间轴段必须清零
    if re.search(r"\[\d\d:\d\d\.\d+\s*[–-]\s*\d\d:\d\d\.\d+\]", new):
        probs.append("仍残留时间轴段标记")
    # 主体编号集合不变
    a = set(re.findall(r"<Subject\s*(\d)>", old))
    b = set(re.findall(r"<Subject\s*(\d)>", new))
    if a != b:
        probs.append("主体编号集合变了: %s -> %s" % (sorted(a), sorted(b)))
    # 对白一字不动
    if sorted(re.findall(r"<d>.*?</d>", old, re.S)) != sorted(re.findall(r"<d>.*?</d>", new, re.S)):
        probs.append("对白标签被改动")
    # 环境音 / 配乐一字不动
    for name, pre in [("环境音", SOUND_PREFIX), ("配乐", MUSIC_PREFIX)]:
        if old[old.index(pre):].strip() != new[new.index(pre):].strip():
            probs.append("%s 块被改动" % name)
    # 切换词
    for kw in ["At 00:", "suddenly", "instantly", "abrupt", "cut to", "cuts to"]:
        if kw.lower() in new.lower():
            probs.append("仍含切换词「%s」" % kw)
    return probs


def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--src", default=os.path.join(os.path.dirname(here),
                    "01_周星驰_三十八万八", "manifest.json"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--shots", default="6,7,8")
    ap.add_argument("--diff", action="store_true")
    a = ap.parse_args()

    want = [int(x) for x in a.shots.split(",") if x.strip()]
    out_path = a.out or os.path.join(os.path.dirname(a.src), "manifest_v4.json")
    m = json.load(open(a.src, encoding="utf-8"))

    print("=" * 92)
    print("v4 单段连续叙述改写 · 只改镜 %s" % want)
    print("=" * 92)
    probs_all = []
    for s in m["shots"]:
        no = s["no"]
        if no not in want:
            continue
        if no not in BODY4:
            print("  ⚠ 镜%02d 无 v4 模板" % no); continue
        old = s["prompt"]
        new = build(old, no)
        probs = check(old, new, no)
        print("  %s 镜%02d | %4d → %4d 字符 | 时间轴段 %d → %d | 主体 %s" % (
            "✔" if not probs else "✘", no, len(old), len(new),
            len(re.findall(r"\[\d\d:\d\d\.\d+", old)),
            len(re.findall(r"\[\d\d:\d\d\.\d+", new)),
            sorted(set(re.findall(r"<Subject\s*(\d)>", new)))))
        for p in probs:
            print("        ✘ %s" % p)
        probs_all += probs
        s["prompt"] = new

    print("-" * 92)
    if probs_all:
        print("✘ %d 项自检未通过，不写文件" % len(probs_all)); return 1
    print("✔ 自检通过")
    if a.diff:
        print("  (--diff，未写文件)"); return 0
    json.dump(m, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("✔ 已写出 %s" % out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
