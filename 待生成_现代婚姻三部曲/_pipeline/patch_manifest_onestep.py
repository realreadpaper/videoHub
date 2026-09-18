#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按「一步直出 768×1344」口径重出 manifest。

为什么必须改
------------
两阶段时成片经 LTX `frame_policy=trim_to_8n_plus_1` 裁剪，
manifest 里 duration/duration_frames 存的是 **trim 后** 的值：
    f1s02  H3 311 帧 → trim 305 帧 = 12.708 s

一步直出**不经过 LTX**，成片就是 H3 原始帧数：
    f1s02  311 帧 = 12.958 s

若沿用旧值，字幕时间轴会按 12.708 排，而画面是 12.958，
每镜差 0.04–0.25 s，24 镜累积可达数秒 —— 字幕越往后越飘。

改什么
------
  · shots[].duration         = h3_length / 24
  · shots[].duration_frames  = h3_length
  · 顶层 generation_mode / resolution 标注
  ★ prompt 不动：其时间戳末段本来就是按 H3 全长生成的（校验项⑤）

用法： python3 _pipeline/patch_manifest_onestep.py
"""
import json, os, glob, shutil, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FPS = 24

def ts(sec):
    m, s = divmod(sec, 60)
    return f"{int(m):02d}:{s:06.3f}"

manifests = sorted(glob.glob(os.path.join(ROOT, "0*_*/manifest.json")))
assert manifests, "未找到 manifest.json"

total = 0
allrows = []
for path in manifests:
    d = json.load(open(path, encoding="utf-8"))
    film = os.path.basename(os.path.dirname(path))
    print(f"\n=== {film} ===")
    print(f"  {'镜':<6}{'H3帧':>6}{'旧(trim)':>16}{'新(一步)':>16}   校验")

    changed = 0
    for s in d["shots"]:
        h3 = s["h3_length"]
        # 栅格校验：H3 length 必须落在 17n+5
        assert (h3 - 5) % 17 == 0, f"{film} s{s['no']:02d} h3_length={h3} 不在 17n+5 栅格"

        old_dur, old_fr = s["duration"], s["duration_frames"]
        new_dur = round(h3 / FPS, 3)
        new_fr = h3

        s["duration"] = new_dur
        s["duration_frames"] = new_fr
        changed += 1
        total += 1
        delta = new_dur - old_dur
        allrows.append((f"{film[:2]}s{s['no']:02d}", h3, old_fr, old_dur, new_fr, new_dur, delta))
        print(f"  s{s['no']:02d}  {h3:>6}{f'{old_fr}帧/{old_dur}s':>16}"
              f"{f'{new_fr}帧/{new_dur}s':>16}   Δ{delta:+.3f}s")

    # 顶层标注
    d["generation_mode"] = "one_step_768x1344"
    d["resolution_stage1"] = "768x1344"
    d["resolution_stage2"] = None          # 一步直出，无精修阶段
    d["trim_applied"] = False               # 不经 LTX trim
    d["manifest_revised_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    d["manifest_revision_note"] = (
        "改为一步直出 768×1344：duration/duration_frames 由 LTX trim 值改回 H3 原始帧数。"
        "prompt 时间戳未改（末段本就按 H3 全长）。"
    )
    # 顶层 refined_frames 与单镜同义，同步为 H3 值
    if "refined_frames" in d and d["shots"]:
        d["refined_frames"] = d["shots"][0]["h3_length"]

    json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"  ✓ 更新 {changed} 镜 → {path}")

print("\n" + "=" * 62)
print(f"合计更新 {total} 镜（{len(manifests)} 部片）")
print()
print("差异汇总（Δ = 新 - 旧，即字幕轴需要补的量）：")
print(f"  {'镜':<8}{'H3帧':>6}{'旧帧':>6}{'新帧':>6}{'旧s':>9}{'新s':>9}{'Δ秒':>9}")
for r in allrows[:6]:
    print(f"  {r[0]:<8}{r[1]:>6}{r[2]:>6}{r[4]:>6}{r[3]:>9}{r[5]:>9}{r[6]:>+9.3f}")
print(f"  ... 共 {len(allrows)} 镜")
ds = [r[6] for r in allrows]
print()
print(f"Δ 范围: {min(ds):+.3f} ~ {max(ds):+.3f} s   累计: {sum(ds):+.3f} s")
print(f"旧总时长: {sum(r[3] for r in allrows):.2f} s   新总时长: {sum(r[5] for r in allrows):.2f} s")
print()
print("★ 字幕时间轴必须按新的 duration 重算，否则全片累积漂移 %.2f s" % sum(ds))
