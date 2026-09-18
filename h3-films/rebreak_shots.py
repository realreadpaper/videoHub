#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v3 · 边界对齐版切分：把两片切成 10–15s 的生成镜（一镜一次生成整窗）。

与 v2 细拆版（--min 2.0 的 2~3s 镜）相反：镜长回到贴近 362 帧整窗（10–15.083s），
一次性生成质量更稳；重点全部放在**镜界质量**上：

  1. 镜界只能落在**原片实测切点**上（reelbench 场景检测），绝不从一镜中间穿过；
  2. 场景/段落换段（短剧↔口播↔收尾等）是**硬边界**，一个生成镜绝不横跨两种内容；
  3. 段内用 DP 选切点：镜长 ∈ [10, 15.083]s、贴近目标 14.6s，
     并对「边界处运动尖峰最强」的切点给奖励——视觉变化大的地方切，
     相邻两镜的内容不容易在生成时搅在一起。

台词分配 / 校验与 v2 相同（词中心归属、逐字守恒、与旧表交叉核对）。
细拆版随时可复现：python3 rebreak_shots.py --film film1 --min 2.0 --maxlen 15.083 --target 2.0

用法: python3 rebreak_shots.py --film film1 --fmt json > _lines_rhythm/film1_shot_lines.json
"""
import argparse, json, os, re, sys

ROOT = "/Users/hejianglong/Desktop/videoHub"
H3 = ROOT + "/h3-films"
ALLOWED = os.path.realpath(ROOT)
TS = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)")
PUNCT = set("，。？！、：；「」『』（）…—·,.?!:;()\"'“”‘’~% ")

FILMS = {
    "film1": {
        "dir": "film1-office",
        "cuts": ROOT + "/videos/douyin-ad/shots/shots.json",
        "track": ROOT + "/videos/douyin-ad/shots/track.json",
        "srt": ROOT + "/videos/douyin-ad/references/zui-guoli-ribs/transcript.srt",
        "old_lines": H3 + "/_lines/film1_shot_lines.json",
        "title": "良心面试 · 食堂红烧",
        "seed": 20260918,
        "segments": [  # (名, t0, t1) —— 换段硬边界（999=片尾）
            ("剧情 A · 假摔测试", 0, 75), ("剧情 B · 扶人与分饭", 75, 120),
            ("剧情 C · 身份揭示", 120, 172), ("桥 · 进厨房", 172, 186),
            ("卖货 · 口播带货", 186, 272), ("收尾 · 结论", 272, 999),
        ],
    },
    "film2": {
        "dir": "film2-blinddate",
        "cuts": ROOT + "/videos/douyin-ad-2/shots/shots.json",
        "track": ROOT + "/videos/douyin-ad-2/shots/track.json",
        "srt": ROOT + "/videos/douyin-ad-2/references/homecook/transcript.srt",
        "old_lines": H3 + "/_lines/film2_shot_lines.json",
        "title": "相亲这场 · 一包搞定",
        "seed": 20260919,
        "segments": [
            ("短剧 A · 父子试探", 0, 30), ("短剧 A · 相亲嫌弃", 30, 89),
            ("铰链 · 进店", 89, 104), ("卖货 · 口播带货", 104, 208),
            ("短剧 B · 反转", 208, 267), ("收尾 · 结论", 267, 999),
        ],
    },
}
MAX_SHOT = 362 / 24.0  # 15.0833s，验证过的帧数栅格


def safe(path):
    rp = os.path.realpath(path)
    if not (rp == ALLOWED or rp.startswith(ALLOWED + os.sep)):
        raise ValueError("path outside workspace: " + path)
    return rp


def parse_srt(path):
    raw = open(safe(path), encoding="utf-8").read().replace("\r\n", "\n")
    out = []
    for block in raw.strip().split("\n\n"):
        lines = [l for l in block.split("\n") if l.strip()]
        if len(lines) < 3 or "-->" not in lines[1]:
            continue
        m = TS.findall(lines[1])
        if len(m) < 2:
            continue

        def sec(t):
            h, mi, s, ms = t
            return int(h) * 3600 + int(mi) * 60 + int(s) + int(ms.ljust(3, "0")[:3]) / 1000.0

        txt = "".join(lines[2:]).strip()
        if txt:
            a, b = sec(m[0]), sec(m[1])
            out.append({"t0": a, "t1": b, "c": (a + b) / 2.0, "w": txt})
    out.sort(key=lambda x: x["t0"])
    return out


def unpunct(s):
    return "".join(ch for ch in s if ch not in PUNCT)


def punct_split(s, n):
    if n <= 0:
        return "", s
    cnt = 0
    for i, ch in enumerate(s):
        if ch not in PUNCT:
            cnt += 1
            if cnt == n:
                j = i + 1
                while j < len(s) and s[j] in PUNCT:
                    j += 1
                return s[:j], s[j:]
    return s, ""


def motion_label(m):
    return "固定机位" if m <= 1.5 else ("缓动/主体运动" if m < 12 else "强运动")


def seg_of(segments, t):
    for name, a, b in segments:
        if a <= t < b:
            return name
    return segments[-1][0]


def pick_boundaries(cuts, segments, dur, minlen, maxlen, target, edge_choices):
    """返回选中的镜界时间列表（含 0 与 dur）。edge_choices = 每个换段边界的吸附时间。"""
    bnds = sorted(cs["end"] for cs in cuts)[:-1]  # 实测切点（片内）
    bnds = [b for b in bnds if 0.5 < b < dur - 0.5]

    hard = [0.0, dur] + list(edge_choices)
    hard = sorted(set(round(h, 2) for h in hard))

    def spk(t):
        return SPIKE[max(0, min(int(round(t * HZ)), len(SPIKE) - 1))]

    chosen = []
    for a, b in zip(hard[:-1], hard[1:]):
        inner = [x for x in bnds if a + 0.5 < x < b - 0.5]
        nodes = [a] + inner + [b]
        # DP：从 a 到 b，步长 ∈ [minlen, maxlen]
        INF = float("inf")
        dp = [INF] * len(nodes)
        pre = [-1] * len(nodes)
        dp[0] = 0.0
        for i in range(len(nodes)):
            if dp[i] == INF:
                continue
            for j in range(i + 1, len(nodes)):
                ln = nodes[j] - nodes[i]
                if ln > maxlen + 1e-9:
                    break
                if ln < minlen - 1e-9:
                    continue
                cost = (ln - target) ** 2 - 3.0 * spk(nodes[j])
                if dp[i] + cost < dp[j] - 1e-9:
                    dp[j] = dp[i] + cost
                    pre[j] = i
        if dp[-1] == INF:
            return None, (a, b)
        path, k = [], len(nodes) - 1
        while k > 0:
            path.append(nodes[k])
            k = pre[k]
        chosen += [a] + path[::-1][:-1]
    chosen.append(dur)
    return sorted(set(round(x, 2) for x in chosen)), None


def run(film, minlen, maxlen, target):
    cfg = FILMS[film]
    cuts = json.load(open(safe(cfg["cuts"]), encoding="utf-8"))["shots"]
    words = parse_srt(cfg["srt"])
    dur = cuts[-1]["end"]
    trk = json.load(open(safe(cfg["track"]), encoding="utf-8"))
    global HZ, SPIKE
    HZ, SPIKE = trk["hz"], trk["values"]
    spike_vals = sorted(SPIKE)
    p95 = spike_vals[int(len(spike_vals) * 0.95)] or 1.0
    SPIKE = [min(v / p95, 1.5) for v in SPIKE]

    # 换段边界候选：名义边 ±3s 内的实测切点（+名义本身），组合搜索选可行吸附
    all_bnds = sorted(cs["end"] for cs in cuts)
    edge_cands = []
    for _, a, b in cfg["segments"]:
        if 0 < a < 999 and 0.5 < a < dur - 0.5:
            cands = sorted(set([round(a, 2)] + [round(x, 2) for x in all_bnds if abs(x - a) <= 3.0]))
            edge_cands.append(cands)

    def search(minlen):
        best = None
        idx = [0] * len(edge_cands)

        def dfs(k, choice, dev):
            nonlocal best
            if best is not None and dev > best[0]:
                return
            if k == len(edge_cands):
                picked, fail = pick_boundaries(cuts, cfg["segments"], dur, minlen,
                                               maxlen, target, choice)
                if picked is not None:
                    best = (dev, tuple(choice), picked)
                return
            for c in edge_cands[k]:
                dfs(k + 1, choice + [c], dev + abs(c - segments_edges[k]))
        dfs(0, [], 0.0)
        return best

    segments_edges = [a for _, a, b in cfg["segments"] if 0 < a < 999 and 0.5 < a < dur - 0.5]
    relaxed = []
    ml = minlen
    picked = None
    while True:
        best = search(ml)
        if best is not None:
            picked = best[2]
            break
        relaxed.append(ml)
        ml -= 1.0
        if ml < 5:
            raise SystemExit("切分不可行（含边界候选搜索）")
    windows = []
    for t0, t1 in zip(picked[:-1], picked[1:]):
        g = [cs for cs in cuts if cs["start"] >= t0 - 0.01 and cs["end"] <= t1 + 0.01]
        windows.append({
            "t0": round(t0, 2), "t1": round(t1, 2), "seconds": round(t1 - t0, 2),
            "frames": round((t1 - t0) * 24),
            "motion": round(sum(x["motion"] for x in g) / len(g), 1) if g else 0.0,
            "src_cuts": len(g),
        })

    # 词 -> 镜（词中心），并交叉核对旧 20 镜窗
    bounds = [w["t0"] for w in windows] + [windows[-1]["t1"]]
    for w in words:
        wi = 0
        for i, b in enumerate(bounds):
            if b <= w["c"] + 1e-9:
                wi = i
        w["shot"] = min(wi, len(windows) - 1)

    old = json.load(open(safe(cfg["old_lines"]), encoding="utf-8"))
    ob = [old["shots"][0]["t0"]] + [s["t1"] for s in old["shots"]]
    ok_cross = True
    for k, s in enumerate(old["shots"]):
        mine = "".join(w["w"] for w in words if ob[k] <= w["c"] < ob[k + 1])
        if mine != s["text"]:
            ok_cross = False
            print("  [交叉核对不一致] 旧镜%d" % (k + 1), file=sys.stderr)

    # manifest 台词行 -> 词区间（旧窗内按累计无标点字符连续切分），再按新镜界切开
    manifest = json.load(open(safe(H3 + "/" + cfg["dir"] + "/manifest.json"), encoding="utf-8"))
    old_words = [[w for w in words if ob[k] <= w["c"] < ob[k + 1]] for k in range(len(old["shots"]))]
    for w in windows:
        w["dialogue"] = []
    for k, s in enumerate(manifest["shots"]):
        ws = old_words[k]
        if ws:
            fallback_shot = ws[-1]["shot"]
        else:
            mid = (ob[k] + ob[k + 1]) / 2
            fallback_shot = 0
            for i, b in enumerate(bounds):
                if b <= mid:
                    fallback_shot = i
            fallback_shot = min(fallback_shot, len(windows) - 1)
        if not ws:
            for sp, text in s["dialogue"]:
                windows[fallback_shot]["dialogue"].append([sp, text])
            continue
        wcum = [0]
        for x in ws:
            wcum.append(wcum[-1] + len(x["w"]))
        total = wcum[-1]
        man_w = sum(len(unpunct(t)) for _, t in s["dialogue"]) or 1

        def idx_at(c):
            c = max(0, min(c, total))
            i = 0
            while i < len(ws) - 1 and wcum[i + 1] <= c:
                i += 1
            return i

        cum_line, prev_wb = 0, 0
        n_lines = len(s["dialogue"])
        for li, (sp, text) in enumerate(s["dialogue"]):
            n = len(unpunct(text))
            wa = idx_at(round(cum_line * total / man_w))
            cum_line += n
            wb = len(ws) if li == n_lines - 1 else idx_at(round(cum_line * total / man_w))
            wa = max(wa, prev_wb)
            wb = max(wb, wa + 1) if wa < len(ws) else wa
            prev_wb = wb
            if wa >= len(ws):
                windows[fallback_shot]["dialogue"].append([sp, text])
                continue
            if wa >= wb:
                continue
            runs, cur_shot, cur_words = [], ws[wa]["shot"], []
            for i in range(wa, wb):
                if ws[i]["shot"] != cur_shot:
                    runs.append((cur_shot, cur_words))
                    cur_shot, cur_words = ws[i]["shot"], []
                cur_words.append(ws[i])
            runs.append((cur_shot, cur_words))
            remaining = text
            last_shot_i = None
            for shot_i, rws in runs:
                n_here = sum(len(x["w"]) for x in rws)
                part, remaining = punct_split(remaining, n_here)
                if part:
                    windows[shot_i]["dialogue"].append([sp, part])
                    last_shot_i = shot_i
            if unpunct(remaining):
                windows[(last_shot_i if last_shot_i is not None else fallback_shot)]["dialogue"] \
                    .append([sp, remaining])

    # 校验
    errs = []
    for i, w in enumerate(windows):
        if i and abs(w["t0"] - windows[i - 1]["t1"]) > 0.011:
            errs.append("镜%d窗不连续" % (i + 1))
        if w["seconds"] > MAX_SHOT + 0.01:
            errs.append("镜%d超 15.083s" % (i + 1))
        if w["seconds"] < minlen - 1e-9 and i < len(windows) - 1:
            errs.append("镜%d短于下限" % (i + 1))
    src_all = "".join(w["w"] for w in words)
    joined = "".join("".join(x["w"] for x in words if x["shot"] == i) for i in range(len(windows)))
    if joined != src_all:
        errs.append("词级拼接不守恒")
    dlg_all = "".join(unpunct(t) for w in windows for _, t in w["dialogue"])
    man_all = "".join(unpunct(t) for s in manifest["shots"] for _, t in s["dialogue"])
    if dlg_all != man_all:
        errs.append("台词逐字不守恒: 新%d vs 旧%d" % (len(dlg_all), len(man_all)))

    # 逐镜元数据（承自中心所在旧镜）
    span = dur / 20.0
    seg_edges = set()
    for _, a, b in cfg["segments"]:
        if 0 < a < 999:
            seg_edges.add(round(a, 2))
    n_seg_edge = 0
    for i, w in enumerate(windows):
        mid = (w["t0"] + w["t1"]) / 2
        m = manifest["shots"][min(int(mid / span), 19)]
        if i and any(abs(w["t0"] - e) <= 2.6 for e in seg_edges):
            n_seg_edge += 1
        w.update({
            "no": i + 1, "file": "shot%02d" % (i + 1),
            "text": "".join(x["w"] for x in words if x["shot"] == i),
            "words": sum(1 for x in words if x["shot"] == i),
            "camera": motion_label(w["motion"]),
            "segment": seg_of(cfg["segments"], w["t0"]),
            "scene": m["scene"], "base_framing": m["framing"],
            "base_characters": m["character"], "src_unit": m["file"],
        })

    out = {
        "film": film, "title": cfg["title"],
        "mode": "cut-aligned-units(镜界对齐实测切点/换段硬边界)",
        "mode_note": "镜长 %g–%.3fs 贴近整窗一次生成；镜界全部落在原片实测切点，换段处为硬边界，"
                     "边界优选运动尖峰最强的切点（相邻镜内容不互相渗透）" % (minlen, maxlen),
        "src_duration": round(dur, 2), "min_len": minlen, "max_len": round(maxlen, 4),
        "target_len": target, "n_shots": len(windows), "n_words": len(words),
        "n_boundaries_at_segment_edges": n_seg_edge,
        "relaxed": relaxed,
        "orig_chars": len(src_all), "joined_chars": len(joined),
        "dialogue_chars_conserved": dlg_all == man_all, "cross_check_old_lines": ok_cross,
        "seed": cfg["seed"], "shots": windows,
    }
    print("[%s] %d 镜 | 镜长 %.1f–%.1fs 平均 %.2f | 换段硬边界 %d/%d | 词守恒 %s | 台词守恒 %s | "
          "旧表交叉核对 %s%s"
          % (film, len(windows), min(w["seconds"] for w in windows),
             max(w["seconds"] for w in windows),
             sum(w["seconds"] for w in windows) / len(windows), n_seg_edge,
             len(seg_edges), joined == src_all, dlg_all == man_all,
             "一致" if ok_cross else "不一致",
             (" | ⚠ 松弛:" + str(relaxed)) if relaxed else ""), file=sys.stderr)
    if errs:
        print("  ⚠ " + "; ".join(errs), file=sys.stderr)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--film", choices=["film1", "film2"], required=True)
    ap.add_argument("--fmt", choices=["json", "txt"], default="json")
    ap.add_argument("--min", type=float, default=10.0, help="镜长下限（默认 10s）")
    ap.add_argument("--maxlen", type=float, default=MAX_SHOT)
    ap.add_argument("--target", type=float, default=14.6, help="目标镜长（DP 代价中心）")
    a = ap.parse_args()
    data = run(a.film, a.min, a.maxlen, a.target)
    if a.fmt == "json":
        json.dump(data, sys.stdout, ensure_ascii=False, indent=1)
    else:
        for w in data["shots"]:
            print("镜%03d  %7.2f – %7.2f  %5.2fs/%3df  motion%5.1f %s  %s  承自 %s"
                  % (w["no"], w["t0"], w["t1"], w["seconds"], w["frames"],
                     w["motion"], w["camera"], w["segment"], w["src_unit"]))
            for sp, t in w["dialogue"]:
                print("    %s：%s" % (sp, t))
            if not w["dialogue"]:
                print("    （无台词 · 插入/空镜）")
