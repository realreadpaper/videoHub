#!/usr/bin/env python3
"""把镜头表（shots.json）与字幕（.srt）对齐，产出拆解表 shots.csv + shots.md。

对齐规则：一句台词跨越哪些镜头，就把该句拆到对应镜头；每个镜头列出与其时间重叠的台词片段。
用法: python merge_shots_srt.py <shots.json> <subtitle.srt> <out_prefix>
"""
import csv
import json
import re
import sys


def parse_srt(path):
    text = open(path, encoding="utf-8").read().strip()
    cues = []
    for block in re.split(r"\n\s*\n", text):
        lines = [l for l in block.splitlines() if l.strip()]
        if len(lines) < 3:
            continue
        m = re.match(r"(\d+):(\d+):(\d+),(\d+)\s*-->\s*(\d+):(\d+):(\d+),(\d+)", lines[1])
        if not m:
            continue
        h1, m1, s1, ms1, h2, m2, s2, ms2 = map(int, m.groups())
        start = h1 * 3600 + m1 * 60 + s1 + ms1 / 1000
        end = h2 * 3600 + m2 * 60 + s2 + ms2 / 1000
        cues.append({"start": start, "end": end, "text": "".join(lines[2:]).strip()})
    return cues


def assign(cues, start, end):
    """返回与该镜头时间区间有重叠的台词（按重叠长度取，含跨界片段）。"""
    out = []
    for c in cues:
        ov = min(c["end"], end) - max(c["start"], start)
        if ov > 0.08:
            piece = c["text"]
            # 台词完全包含该镜：直接给；否则按跨界标注
            if c["start"] < start - 0.05 or c["end"] > end + 0.05:
                piece = f"{piece}（跨界）"
            out.append({"text": piece, "t0": round(c["start"], 2), "t1": round(c["end"], 2), "ov": round(ov, 2)})
    return out


def main():
    shots_path, srt_path, prefix = sys.argv[1], sys.argv[2], sys.argv[3]
    shots = json.load(open(shots_path))["shots"]
    cues = parse_srt(srt_path)

    rows = []
    for s in shots:
        lines = assign(cues, s["start"], s["end"])
        rows.append({
            "镜号": s["index"], "开始": s["start"], "结束": s["end"], "时长": s["duration"],
            "台词": " | ".join(l["text"] for l in lines),
            "台词时间": "; ".join(f"{l['t0']}-{l['t1']}" for l in lines),
        })

    with open(f"{prefix}.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["镜号", "开始", "结束", "时长", "台词", "台词时间"])
        w.writeheader()
        w.writerows(rows)

    with open(f"{prefix}.md", "w", encoding="utf-8") as f:
        f.write(f"# 镜头拆解表（{len(rows)} 镜）\n\n")
        f.write("| 镜号 | 时间 | 时长 | 台词 |\n|---|---|---|---|\n")
        for r in rows:
            t = f"{int(r['开始'])//60:02d}:{r['开始']%60:05.2f}"
            f.write(f"| {r['镜号']} | {t} | {r['时长']:.2f}s | {r['台词']} |\n")

    with_text = sum(1 for r in rows if r["台词"])
    print(f"{len(rows)} 镜，其中 {with_text} 镜有台词 → {prefix}.csv / {prefix}.md")


if __name__ == "__main__":
    main()
