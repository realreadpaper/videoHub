#!/usr/bin/env python3
"""把台词分句与镜头对齐，产出"叙事段落表"：每句台词对应哪些镜头、各镜多久。

用法: python build_segments.py <shots.json> <asr_raw.json> <out.md> [--gap 0.8]
"""
import json
import sys


def load(asr_path):
    t = json.load(open(asr_path))
    tr = (t.get("transcripts") or [{}])[0]
    sents = [{"text": (s.get("text") or "").strip(), "start": s.get("begin_time", 0) / 1000.0,
              "end": s.get("end_time", 0) / 1000.0} for s in tr.get("sentences", [])]
    return [s for s in sents if s["text"]]


def mmss(x):
    return f"{int(x)//60:02d}:{x%60:05.2f}"


def main():
    shots_path, asr_path, out = sys.argv[1], sys.argv[2], sys.argv[3]
    gap = 0.8
    if "--gap" in sys.argv:
        gap = float(sys.argv[sys.argv.index("--gap") + 1])
    shots = json.load(open(shots_path))["shots"]
    sents = load(asr_path)

    # 把相邻且间隔很小的句子合并成段（一段≈一个连续说话回合）
    segs = []
    for s in sents:
        if segs and s["start"] - segs[-1]["end"] < gap and len(segs[-1]["text"]) < 60:
            segs[-1]["text"] += s["text"]
            segs[-1]["end"] = s["end"]
        else:
            segs.append(dict(s))

    lines = [f"# 叙事段落表（{len(segs)} 段 / {len(shots)} 镜）\n",
             "| 段 | 时间 | 时长 | 镜数 | 镜头区间 | 台词 |",
             "|---|---|---|---|---|---|"]
    for i, seg in enumerate(segs, 1):
        inside = [s for s in shots if s["start"] < seg["end"] - 0.05 and s["end"] > seg["start"] + 0.05]
        ids = [s["index"] for s in inside]
        rng = f"#{ids[0]}–#{ids[-1]}" if ids else "—"
        durs = ", ".join(f"{s['duration']:.1f}" for s in inside)
        lines.append(f"| {i} | {mmss(seg['start'])}–{mmss(seg['end'])} | {seg['end']-seg['start']:.1f}s "
                     f"| {len(inside)} | {rng} | {seg['text']} |")
        lines.append(f"| | | | | 镜长: {durs} | |")

    open(out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(f"{len(segs)} 段 → {out}")


if __name__ == "__main__":
    main()
