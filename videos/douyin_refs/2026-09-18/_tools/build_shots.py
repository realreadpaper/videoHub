#!/usr/bin/env python3
"""从 hypit media boundaries 的候选点生成镜头表。

思路：候选点是逐帧变化量，含真实剪切与镜头内运动。按分数阈值筛 + 最小间隔去重 +
最短镜长约束，得到可用的镜头切分。

用法: python build_shots.py <boundaries.json> <duration_s> <out.json> [--threshold 0.15]
"""
import argparse
import json
import sys


def build(cands, duration, threshold, min_gap=0.40, min_shot=0.60):
    pts = sorted([c["at"] for c in cands if c["score"] >= threshold])
    cuts = [0.0]
    for t in pts:
        if t - cuts[-1] >= min_gap:
            cuts.append(t)
    # 结尾闭合
    if duration - cuts[-1] < min_shot:
        cuts.pop()
    cuts.append(duration)
    # 过短镜头与前一个合并（保留前一个的起点）
    merged = []
    i = 0
    while i < len(cuts) - 1:
        start, end = cuts[i], cuts[i + 1]
        if merged and end - start < min_shot:
            merged[-1]["end"] = end
        else:
            merged.append({"start": round(start, 3), "end": round(end, 3)})
        i += 1
    for idx, m in enumerate(merged, 1):
        m["index"] = idx
        m["duration"] = round(m["end"] - m["start"], 3)
        m["mid"] = round((m["start"] + m["end"]) / 2, 3)
    return merged


def main():
    p = argparse.ArgumentParser()
    p.add_argument("boundaries")
    p.add_argument("duration", type=float)
    p.add_argument("out")
    p.add_argument("--threshold", type=float, default=0.15)
    a = p.parse_args()

    d = json.load(open(a.boundaries))
    cands = d.get("candidates", d)
    shots = build(cands, a.duration, a.threshold)

    json.dump({"threshold": a.threshold, "count": len(shots), "shots": shots},
              open(a.out, "w"), ensure_ascii=False, indent=2)

    durs = [s["duration"] for s in shots]
    durs_sorted = sorted(durs)
    med = durs_sorted[len(durs_sorted) // 2]
    print(f"阈值 {a.threshold}: {len(shots)} 镜 | 平均 {sum(durs)/len(durs):.2f}s "
          f"中位 {med:.2f}s 最短 {min(durs):.2f}s 最长 {max(durs):.2f}s")
    print(f"  >5s 的长镜: {sum(1 for x in durs if x > 5)} 个 | <1s 的短镜: {sum(1 for x in durs if x < 1)} 个")


if __name__ == "__main__":
    main()
