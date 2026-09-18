#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按原片逐词时间码，把口播原文 100% 抄写并分配到每镜时间窗。

用法:
  python3 align_lines.py                # 两片全部
  python3 align_lines.py --film film1
输出:
  _lines/film1_shot_lines.json          每镜的原片时间窗 + 原文逐字
  _lines/film1_shot_lines.txt           人读对照表
"""
import argparse, json, os, re, sys

H3 = "/Users/hejianglong/Desktop/videoHub/h3-films"
REFS = {
    "film1": {
        "srt": "/Users/hejianglong/Desktop/videoHub/videos/douyin-ad/references/zui-guoli-ribs/transcript.srt",
        "src": "/Users/hejianglong/Desktop/videoHub/videos/douyin-ad/ref/7661791104643797617.mp4",
        "title": "片1·良心面试",
    },
    "film2": {
        "srt": "/Users/hejianglong/Desktop/videoHub/videos/douyin-ad-2/references/homecook/transcript.srt",
        "src": "/Users/hejianglong/Desktop/videoHub/videos/douyin-ad-2/references/homecook/source.mp4",
        "title": "片2·相亲",
    },
}
NSHOTS = 20
SHOT_SEC = 15.0

TS = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)")


def parse_srt(path):
    """逐词 srt -> [(start, end, text)]"""
    raw = open(path, encoding="utf-8").read().replace("\r\n", "\n")
    out = []
    for block in raw.strip().split("\n\n"):
        lines = [l for l in block.split("\n") if l.strip()]
        if len(lines) < 3:
            continue
        m = TS.findall(lines[1]) if "-->" in lines[1] else None
        if not m or len(m) < 2:
            continue
        def sec(t):
            h, mi, s, ms = t
            return int(h) * 3600 + int(mi) * 60 + int(s) + int(ms.ljust(3, "0")[:3]) / 1000.0
        a, b = sec(m[0]), sec(m[1])
        txt = "".join(lines[2:]).strip()
        if txt:
            out.append((a, b, txt))
    out.sort(key=lambda x: x[0])
    return out


def duration(path):
    import subprocess
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True)
    return float(r.stdout.strip())


def build(film):
    cfg = REFS[film]
    words = parse_srt(cfg["srt"])
    L = duration(cfg["src"])
    step = L / NSHOTS           # 每镜覆盖的原片时长
    shots = []
    for i in range(NSHOTS):
        t0, t1 = i * step, (i + 1) * step
        # 词边界吸附：起点取最后一个中心 < t0 的词之后的词；终点同理
        picked = [w for w in words if w[0] >= t0 - 0.001 and w[1] <= t1 + 0.001]
        # 边界补偿：把跨越边界的词按中心点归属，保证不丢字
        for w in words:
            c = (w[0] + w[1]) / 2
            if t0 <= c < t1 and w not in picked:
                picked.append(w)
        picked = [w for w in words if t0 <= (w[0] + w[1]) / 2 < t1]
        picked.sort(key=lambda x: x[0])
        text = "".join(w[2] for w in picked)
        shots.append({
            "no": i + 1,
            "t0": round(t0, 2), "t1": round(t1, 2),
            "words": len(picked),
            "text": text,
        })
    # 100% 完整性校验：拼起来应与原转写逐字一致
    joined = "".join(s["text"] for s in shots)
    orig = "".join(w[2] for w in words)
    ok = joined == orig
    return {
        "film": film, "title": cfg["title"], "src_duration": round(L, 3),
        "shot_sec_cover": round(step, 3), "n_shots": NSHOTS,
        "n_words": len(words), "coverage_exact": ok,
        "orig_chars": len(orig), "joined_chars": len(joined),
        "shots": shots,
    }


def render(md):
    L = []
    L.append("# %s · 原片台词 100%% 抄写对齐表" % md["title"])
    L.append("")
    L.append("原片时长 %.2fs → %d 镜 × %.2fs 覆盖窗；逐词 %d 个，原文 %d 字。"
             % (md["src_duration"], md["n_shots"], md["shot_sec_cover"], md["n_words"], md["orig_chars"]))
    L.append("")
    L.append("**逐字完整性**：拼接结果与原转写%s（%d / %d 字）"
             % ("完全一致 ✓" if md["coverage_exact"] else "不一致 ✗", md["joined_chars"], md["orig_chars"]))
    L.append("")
    L.append("| 镜 | 生成窗 | 原片时间窗 | 字数 | 原文（逐字） |")
    L.append("| --- | --- | --- | --- | --- |")
    for i, s in enumerate(md["shots"]):
        g0, g1 = i * SHOT_SEC, (i + 1) * SHOT_SEC
        L.append("| %d | %.1f–%.1fs | %s–%s | %d | %s |" % (
            s["no"], g0, g1, fmt(s["t0"]), fmt(s["t1"]), len(s["text"]), s["text"] or "—"))
    return "\n".join(L) + "\n"


def fmt(t):
    return "%d:%05.2f" % (int(t // 60), t % 60)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--film", default="all")
    a = ap.parse_args()
    os.makedirs(os.path.join(H3, "_lines"), exist_ok=True)
    films = ["film1", "film2"] if a.film == "all" else [a.film]
    for f in films:
        md = build(f)
        jp = os.path.join(H3, "_lines", "%s_shot_lines.json" % f)
        tp = os.path.join(H3, "_lines", "%s_shot_lines.txt" % f)
        json.dump(md, open(jp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        open(tp, "w", encoding="utf-8").write(render(md))
        print("[%s] 原片 %.2fs / %d 镜 / 逐词 %d / 原文 %d 字 / 逐字完整=%s -> %s"
              % (f, md["src_duration"], md["n_shots"], md["n_words"], md["orig_chars"],
                 "✓" if md["coverage_exact"] else "✗", tp))


if __name__ == "__main__":
    main()
