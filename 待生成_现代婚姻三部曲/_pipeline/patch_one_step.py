#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把现成的 stage1 工作流（384×672 草稿）改造成 **一步直出 768×1344 成品**。

依据：v3run 的工作流与本流水线 stage1 是**同一个**（同 UNET minimax_h3_fl2va、
同 4 步 dual_clock_euler / native_flow、同样 15 节点），唯一差别就是分辨率
与音轨来源。v3 以 768×1344 跑了 47 镜，实测均值 466 s/镜，链路已验证。

所以"一次生成"不需要换流程，只需：
  · width/height: 384×672 → 768×1344
  · 跳过 stage2（精修是从 384 草稿补细节，这是画质糊的根因）
  · 输出目录分开，避免与草稿混淆

用法： python3 _pipeline/patch_one_step.py
输出： _pipeline/wf_one/wf_<key>.json
"""
import json, os, glob, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "_pipeline", "wf")
DST = os.path.join(ROOT, "_pipeline", "wf_one")

W, H = 768, 1344
PREFIX_DIR = "MiniMaxH3/trilogy_one"   # 一步直出成品目录

os.makedirs(DST, exist_ok=True)
n = 0
report = []
for p in sorted(glob.glob(os.path.join(SRC, "wf_*.json"))):
    k = os.path.basename(p)[3:-5]
    d = json.load(open(p, encoding="utf-8"))

    # A. 分辨率
    before = (d["6"]["inputs"].get("width"), d["6"]["inputs"].get("height"))
    d["6"]["inputs"]["width"] = W
    d["6"]["inputs"]["height"] = H

    # B. 输出目录分开（原 f1_s02 → 一步成品加 one/ 前缀，仍保留下划线便于检索）
    old_pfx = d["12"]["inputs"].get("filename_prefix", "")
    d["12"]["inputs"]["filename_prefix"] = f"{PREFIX_DIR}/{k[:2]}_{k[2:]}"

    # C. 顶层不能有 _meta（/prompt 会把它当节点 → 400 missing_node_type）
    d.pop("_meta", None)

    out = os.path.join(DST, f"wf_{k}.json")
    json.dump(d, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    n += 1
    report.append((k, before, (W, H), old_pfx, d["12"]["inputs"]["filename_prefix"]))

print(f"✓ 已生成 {n} 个一步直出工作流 → {DST}")
print(f"  分辨率: 384×672 → {W}×{H}")
print(f"  输出目录: {PREFIX_DIR}/")
print()
print(f"{'镜':<8}{'原分辨率':<14}{'新分辨率':<14}输出前缀")
for k, b, a, o, np_ in report[:5]:
    print(f"{k:<8}{str(b):<14}{str(a):<14}{np_}")
print(f"  ... 共 {n} 镜")

# 帧数统计（用于工期估算）
frames = []
for p in sorted(glob.glob(os.path.join(DST, "wf_*.json"))):
    d = json.load(open(p, encoding="utf-8"))
    s = d.get("14", {}).get("inputs", {}).get("scene_duration_seconds")
    if s:
        frames.append(round(float(s) * 24))
if frames:
    print()
    print(f"帧数: 平均 {sum(frames)/len(frames):.0f} 帧, 范围 {min(frames)}-{max(frames)}, 合计 {sum(frames)} 帧")
    print(f"总时长: {sum(frames)/24:.1f} s")
