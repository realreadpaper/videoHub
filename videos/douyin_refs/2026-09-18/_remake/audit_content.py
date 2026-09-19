#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""内容规范审核：373 个 wf 逐条过硬标准（S1 零字幕 / S2 表情 / S3 锚点 / S4 技术对齐）。"""
import json, os, re, glob

HERE = os.path.dirname(os.path.abspath(__file__))
WF = f"{HERE}/wf_full"
A = f"{HERE}/full_a"
R = f"{HERE}/full_ref"

def check(nm, d):
    p = d["6"]["inputs"]["prompt"]
    sec = d["14"]["inputs"]["scene_duration_seconds"]
    aud = d["13"]["inputs"]["audio"]
    ref = d["300"]["inputs"]["image"]
    out = []
    # S1 零字幕
    if "<d>" in p or "<d " in p: out.append("S1 出现 <d> 字幕标签")
    if "strict_output_constraints" not in p: out.append("S1 缺 strict_output_constraints 段")
    if "No subtitles" not in p: out.append("S1 缺 No subtitles 禁令")
    if "illegible" not in p: out.append("S1 文字道具未声明 illegible")
    # S2 表情到位
    if "micro-expression" not in p.lower(): out.append("S2 缺微表情要求")
    if not re.search(r"continuous|never freeze|breathing", p.lower()): out.append("S2 缺连续运动要求")
    # S3 锚点
    if "<Picture 1>" not in p: out.append("S3 缺参考帧锚点")
    if "authoritative reference" not in p: out.append("S3 参考帧未声明为权威")
    # S4 技术对齐：prompt 末段时间戳 == scene_duration
    ts = re.findall(r"\[(\d\d):(\d\d)\.(\d\d\d)\s*-\s*(\d\d):(\d\d)\.(\d\d\d)\]", p)
    if not ts:
        out.append("S4 prompt 无时间戳段")
    else:
        mm, ss, ms = int(ts[-1][3]), int(ts[-1][4]), int(ts[-1][5])
        end = mm * 60 + ss + ms / 1000
        if abs(end - sec) > 0.002:
            out.append(f"S4 时间戳末段 {end:.3f}s ≠ scene_duration {sec}s")
    # 资源存在
    if not os.path.exists(os.path.join(A, os.path.basename(aud))): out.append(f"音频缺失 {aud}")
    if not os.path.exists(os.path.join(R, os.path.basename(ref))): out.append(f"参考帧缺失 {ref}")
    # 栅格
    frames = round(sec * 24)
    if (frames - 5) % 17 != 0: out.append(f"栅格非法 {frames} 帧")
    return out

def main():
    files = sorted(glob.glob(f"{WF}/wf_*.json"))
    bad = {}
    stat = {}
    for f in files:
        nm = os.path.basename(f)[3:-5]
        d = json.load(open(f, encoding="utf-8"))
        iss = check(nm, d)
        if iss:
            bad[nm] = iss
        for i in iss:
            stat[i.split()[0]] = stat.get(i.split()[0], 0) + 1
    L = ["# 内容规范审核 · 373 镜", "",
         f"- 检查工作流 **{len(files)}** 个",
         f"- 不合规 **{len(bad)}** 个",
         ""]
    if not bad:
        L.append("✅ **全部通过**：S1 零字幕 / S2 表情 / S3 参考帧锚点 / S4 时间戳对齐 / 资源齐全 / 栅格合法")
    else:
        L.append("| 工作流 | 问题 |"); L.append("|---|---|")
        for k, v in list(bad.items())[:40]:
            L.append(f"| `{k}` | {'；'.join(v)} |")
    L += ["", "## 逐项统计（按标准号）", "", "| 标准 | 命中数 |", "|---|---|"]
    for k in sorted(stat):
        L.append(f"| {k} | {stat[k]} |")
    p = f"{HERE}/审核_内容规范_373镜.md"
    open(p, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(f"[✓] {p}")
    print(f"    检查 {len(files)} 个，不合规 {len(bad)} 个")
    for k, v in list(bad.items())[:10]:
        print(f"    ✗ {k}: {'; '.join(v)}")

if __name__ == "__main__":
    main()
