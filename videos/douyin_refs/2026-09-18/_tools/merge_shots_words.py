#!/usr/bin/env python3
"""把镜头表与词级转写对齐，产出逐镜脚本表。

与"按句对齐"不同：这里用词级时间戳，每个镜头只拿到该镜头时间窗内说出的词，
避免长句在多个镜头里被整句重复。跨界词按起始时间归属。

用法: python merge_shots_words.py <shots.json> <asr_raw.json> <out_prefix>
"""
import csv
import json
import sys
from bisect import bisect_right


def load_words(asr_path):
    t = json.load(open(asr_path))
    tr = (t.get("transcripts") or [{}])[0]
    sentences = tr.get("sentences", [])
    words = []
    for si, s in enumerate(sentences):
        for w in (s.get("words") or []):
            words.append({"text": w.get("text", ""), "start": w.get("begin_time", 0) / 1000.0,
                          "end": w.get("end_time", 0) / 1000.0, "sent": si})
    words.sort(key=lambda x: x["start"])
    sents = [{"text": (s.get("text") or "").strip(), "start": s.get("begin_time", 0) / 1000.0,
              "end": s.get("end_time", 0) / 1000.0} for s in sentences]
    return words, sents


def main():
    shots_path, asr_path, prefix = sys.argv[1], sys.argv[2], sys.argv[3]
    shots = json.load(open(shots_path))["shots"]
    words, sents = load_words(asr_path)

    starts = [w["start"] for w in words]
    rows = []
    for s in shots:
        lo = bisect_right(starts, s["start"] - 1e-9)
        # 该镜头时段内的词（起点落在区间内）
        seg = [words[i] for i in range(len(words)) if s["start"] <= words[i]["start"] < s["end"]]
        text = "".join(w["text"] for w in seg)
        sids = sorted({w["sent"] for w in seg})
        rows.append({
            "镜号": s["index"], "开始": s["start"], "结束": s["end"], "时长": s["duration"],
            "字数": len(text), "台词": text, "句号": ",".join(str(i + 1) for i in sids),
        })

    with open(f"{prefix}.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["镜号", "开始", "结束", "时长", "字数", "台词", "句号"])
        w.writeheader()
        w.writerows(rows)

    with open(f"{prefix}.md", "w", encoding="utf-8") as f:
        f.write(f"# 逐镜脚本表（{len(rows)} 镜 · 词级对齐）\n\n")
        f.write("| 镜号 | 时间 | 时长 | 台词 |\n|---|---|---|---|\n")
        for r in rows:
            t = f"{int(r['开始'])//60:02d}:{r['开始']%60:05.2f}"
            f.write(f"| {r['镜号']} | {t} | {r['时长']:.2f}s | {r['台词']} |\n")

    # 句级台词表
    with open(f"{prefix}_dialogue.md", "w", encoding="utf-8") as f:
        f.write(f"# 台词分句表（{len(sents)} 句）\n\n")
        f.write("| # | 时间 | 台词 |\n|---|---|---|\n")
        for i, s in enumerate(sents, 1):
            t0 = f"{int(s['start'])//60:02d}:{s['start']%60:05.2f}"
            t1 = f"{int(s['end'])//60:02d}:{s['end']%60:05.2f}"
            f.write(f"| {i} | {t0}–{t1} | {s['text']} |\n")

    empty = sum(1 for r in rows if not r["台词"])
    print(f"{len(rows)} 镜 | 有台词 {len(rows)-empty} 镜 | 无台词(画面/音乐) {empty} 镜 "
          f"| 总词数 {sum(r['字数'] for r in rows)}")
    print(f"  → {prefix}.csv / {prefix}.md / {prefix}_dialogue.md")


if __name__ == "__main__":
    main()
