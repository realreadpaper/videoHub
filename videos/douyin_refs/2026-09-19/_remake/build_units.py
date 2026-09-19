#!/usr/bin/env python3
"""叙事单元重组 —— 把原片「按视觉切点分的镜」重新组织成「按台词句分的生成单元」。

问题背景
--------
以「原片镜」为生成单元会撞上两个相反的坑：
  · 短镜（原片中位 1.83s）→ 吸附到 H3 栅格最小档，太短演不完一个动作
  · 长镜（原片 04 有 22 个 ≥4s 的镜，最长 12s）→ prompt 里只写了"一个动作"
    → 模型 5s 演完，剩下 7s 干等 = 「一镜 15s，5s 一个动作，太缓慢」

解法
----
实测两条片语音覆盖 96.6% / 99.7%、句间间隙中位 0.00s，**台词是连续口播**。
所以「台词句」才是天然叙事单元：
  1 句 = 1 单元 = 1 个人物 = 1 条连续语音 → 原声锁天然成立，不会串 voice
  句长中位 3.6s → 吸附后 3.75–4.46s，正是「一镜 4 秒」的理想节奏

每个单元再切 2–4 个「拍点」（beat），每个拍点 = 一句台词片段 + 建议的镜内调度。
这是「人来构思」的落点：让一个镜里有起承转合，而不是一个动作磨到底。

用法
----
    python3 build_units.py <拆解目录> [--min-frames 39] [--max 7.3] [-o units.json]
                                     ↑ 39=1.63s，质量安全下限；22=0.92s 有风险
"""
from __future__ import annotations

import argparse
import json
import os
import statistics as st

FPS = 24
# 实测三点拟合（107/226/354 帧 = 110/291/553 s）；A100 40G / 768x1344 / Turbo 4 步
cost_s = lambda f: 0.812 * f + 0.002129 * f * f - 1.3

# 拍点按语义切：逗号也切（不要按字数硬剁，否则会把词切碎）
PUNCT_ANY = "，、；。？！,;.?!"
PUNCT_HARD = "。？！.;?!"


def grid_up(dur_s: float, min_frames: int) -> int:
    """秒 → 向上吸附到 17n+5 栅格帧数，不低于 min_frames"""
    need = dur_s * FPS
    n = 1
    while 17 * n + 5 < need:
        n += 1
    return max(min_frames, 17 * n + 5)


def has_punct(w: dict) -> bool:
    """该词后是否跟标点。★ 必须判空 —— `""[:1] in "，。"` 恒为 True（空串是任意串的子串），
    漏了这个判断会让每个字都变成独立拍点。"""
    p = (w.get("punctuation") or "")[:1]
    return bool(p)


def has_punct_in(w: dict, puncts: str) -> bool:
    p = (w.get("punctuation") or "")[:1]
    return bool(p) and p in puncts


def split_long(seg: dict, max_s: float) -> list[dict]:
    """过长句按标点递归切分，优先在句末标点处切"""
    if seg["t1"] - seg["t0"] <= max_s or len(seg.get("words", [])) < 8:
        return [seg]   # 少于 8 字切了也没意义（两侧都要留够）
    words = seg["words"]
    mid = (seg["t0"] + seg["t1"]) / 2

    def pick(puncts):
        # ★ 末词不能当切点 —— 在最后一个字后切会把右半切空，导致长句放弃切分
        cands = [i for i, w in enumerate(words[:-1])
                 if len(words) - 1 - i >= 3 and has_punct_in(w, puncts)]
        if not cands:
            return None
        return min(cands, key=lambda i: abs(words[i]["t1"] / 1000.0 - mid))

    cut = pick(PUNCT_HARD)
    if cut is None:
        cut = pick(PUNCT_ANY)
    if cut is None:                      # 无可用标点 → 取最接近中点处（两侧各留 ≥3 字）
        lo, hi = 3, len(words) - 4
        cut = min(range(lo, hi + 1), key=lambda i: abs(words[i]["t1"] / 1000.0 - mid))
    if cut + 1 >= len(words):
        return [seg]

    def mk(ws):
        return {"t0": ws[0]["t0"] / 1000.0, "t1": ws[-1]["t1"] / 1000.0,
                "text": "".join(w["text"] + w.get("punctuation", "") for w in ws).strip(),
                "words": ws}

    out = []
    for part in (mk(words[:cut + 1]), mk(words[cut + 1:])):
        out += split_long(part, max_s)
    return out


def make_beats(seg: dict, n: int) -> list[dict]:
    """按标点把台词切成 n 个拍点；标点段不够则均衡合并，够多则均衡合并"""
    words = seg.get("words") or []
    if not words or n <= 1:
        return [{"t": f"0.0-{seg['t1']-seg['t0']:.1f}", "text": seg["text"]}]

    # 1) 先按全部标点切（★ 用 has_punct 判空，否则每个字都会变成一段）
    chunks, cur = [], []
    for w in words:
        cur.append(w)
        if has_punct(w):
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    if len(chunks) < n:                       # 标点不够 → 在最长段的中点再分
        while len(chunks) < n:
            i = max(range(len(chunks)), key=lambda k: len(chunks[k]))
            c = chunks[i]
            if len(c) < 2:
                break
            h = len(c) // 2
            chunks[i:i + 1] = [c[:h], c[h:]]
    # 2) 段数超过 n → 反复合并「相邻字数之和最小」的一对（保均衡）
    while len(chunks) > n:
        i = min(range(len(chunks) - 1),
                key=lambda k: len(chunks[k]) + len(chunks[k + 1]))
        chunks[i:i + 2] = [chunks[i] + chunks[i + 1]]

    t0 = seg["t0"]
    beats = []
    for c in chunks:
        a, b = c[0]["t0"] / 1000.0, c[-1]["t1"] / 1000.0
        beats.append({
            "t": f"{a - t0:.1f}-{b - t0:.1f}",
            "text": "".join(w["text"] + w.get("punctuation", "") for w in c).strip(),
        })
    return beats


# 拍点角色 → 建议镜内调度（关键：同一个镜里也要有变化，否则就是"干等"）
CAM = {
    "起": "保持景别，人物由静止进入第一个微动作（抬眼 / 侧头 / 手部起势）",
    "承": "镜内缓推 dolly-in 8–12%，把信息焦点交给正在说话的人",
    "转": "过肩换轴或横移带出对面的人（不硬切），画面层次由 1 人变 2 人",
    "合": "停稳不动，给明确反应落点（点头 / 垂眼 / 嘴角变化 / 呼一口气）",
}
ROLE_SEQ = {1: ["合"], 2: ["起", "合"], 3: ["起", "承", "合"], 4: ["起", "承", "转", "合"]}


def write_review_sheet(units: list[dict], film_dur: float, path: str,
                       thresh: float = 5.0) -> int:
    """产出「换人复核表」：只列 >= thresh 秒的单元 —— ASR 会把相邻说话人并进一句，
    这些长单元是唯一需要人工判断"谁在说话"的地方。"""
    L = []
    L.append(f"# 换人复核表 · {os.path.basename(os.path.dirname(path))}\n")
    L.append(f"片长 {film_dur:.2f}s · 共 {len(units)} 单元 · "
             f"本表只列 **≥{thresh}s** 的单元（短单元几乎不会跨人）\n")
    L.append("判据：① 一句里「问完接着答」→ 换人；② 句中称呼突变（「顾董」出现在转折处）→ 换人。")
    L.append("处理：拆成两个单元，各自吸附栅格；`unit` 列写拆成几段。\n")
    L.append("| 单元 | 时间 | 时长 | 帧 | 语速 | 台词 | 换人? | 拆成 |")
    L.append("|---|---|---|---|---|---|---|---|")
    todo = 0
    for u in units:
        if u["dur_gen"] < thresh:
            continue
        todo += 1
        d = u["dialogue"].replace("|", "／")
        L.append(f"| {u['uid']} | {u['t_start']:.2f}–{u['t_end']:.2f} | {u['dur_gen']:.2f}s | "
                 f"{u['frames']} | {u['cps']} | {d} | ☐ | |")
    L.append(f"\n**待复核 {todo} 个**（其余 {len(units)-todo} 个短单元默认单人不查）\n")
    open(path, "w").write("\n".join(L))
    return todo


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dir", help="拆解目录（含 asr_raw.json / shots.json）")
    ap.add_argument("--min-frames", type=int, default=39,
                    help="单元最短帧数（39=1.63s 安全；22=0.92s 有质量风险）")
    ap.add_argument("--max", type=float, default=7.3, help="单元最长秒数，过长按标点再切")
    ap.add_argument("--review-thresh", type=float, default=5.0,
                    help="换人复核阈值（秒），只列 >= 此值的单元")
    ap.add_argument("-o", "--out", default=None)
    a = ap.parse_args()

    src = a.dir
    asr = json.load(open(os.path.join(src, "asr_raw.json")))["transcripts"][0]
    shots = json.load(open(os.path.join(src, "shots.json")))["shots"]
    film_dur = shots[-1]["end"]

    # 1) 句 → 段（仅过长句需要切；短句不合并 —— 短句就是节奏本身）
    segs = []
    for s in sorted(asr["sentences"], key=lambda x: x["begin_time"]):
        if not s["text"].strip() or len(s["text"].strip()) < 2:
            continue
        ws = [{"t0": w["begin_time"], "t1": w["end_time"],
               "text": w["text"], "punctuation": w.get("punctuation", "")}
              for w in (s.get("words") or [])]
        seg = {"t0": s["begin_time"] / 1000.0, "t1": s["end_time"] / 1000.0,
               "text": s["text"].strip(), "words": ws}
        segs += split_long(seg, a.max)

    # 2) 吸附栅格 + 切拍点
    units = []
    for i, seg in enumerate(segs, 1):
        d_src = seg["t1"] - seg["t0"]
        f = grid_up(d_src, a.min_frames)
        d_gen = f / FPS
        # 短单元不硬切拍点 —— 1.6s 的一句「这什么味儿啊？」切成两半只会把词剁碎，
        # 它本身就是「一个反应拍点」，补白走静默反应尾更自然
        nbeat = 1 if d_gen < 2.6 else (2 if d_gen < 3.2 else (3 if d_gen < 5.6 else 4))
        beats = make_beats(seg, nbeat)
        for b, r in zip(beats, ROLE_SEQ.get(nbeat, ["起", "承", "合"])):
            b["role"] = r
            b["cam"] = CAM[r]
        covered = sorted({s["index"] for s in shots if s["end"] > seg["t0"] and s["start"] < seg["t1"]})
        units.append({
            "uid": f"u{i:03d}", "no": i,
            "t_start": round(seg["t0"], 3), "t_end": round(seg["t1"], 3),
            "dur_src": round(d_src, 3), "dur_gen": round(d_gen, 3),
            "frames": f, "pad": round(d_gen - d_src, 3),
            "chars": len(seg["text"]), "cps": round(len(seg["text"]) / d_src, 2),
            "dialogue": seg["text"],
            "beats": beats,
            "src_shots": covered,
            "n_src_shots": len(covered),
        })

    # 3) 统计
    tot = sum(u["frames"] for u in units)
    gpu = sum(cost_s(u["frames"]) for u in units)
    durs = [u["dur_gen"] for u in units]
    pad = sum(u["pad"] for u in units)
    dist: dict[int, int] = {}
    for u in units:
        dist[u["frames"]] = dist.get(u["frames"], 0) + 1

    print("=" * 76)
    print(f"{os.path.basename(src)}")
    print(f"  原片 {film_dur:.2f}s / {len(shots)} 镜 / {len(asr['sentences'])} 句"
          f"  →  重组 {len(units)} 个生成单元")
    print(f"  单元时长 最短 {min(durs):.2f}s 中位 {st.median(durs):.2f}s 最长 {max(durs):.2f}s"
          f" 合计 {sum(durs):.1f}s")
    print(f"  帧数 {tot} | GPU 单卡 {gpu/3600:.2f} h → 双卡挂钟 {gpu/2/3600:.2f} h")
    print(f"  对照「每单元拉满 354 帧」: {len(units)*cost_s(354)/3600:.2f} h（慢 {len(units)*cost_s(354)/gpu:.1f}×）")
    print(f"  吸附补白合计 {pad:.1f}s（占 {pad/sum(durs)*100:.1f}%）—— 用拍点吃掉，就不是干等")
    print("  帧数分布:", " ".join(f"{k}×{v}" for k, v in sorted(dist.items())))
    short = [u for u in units if u["frames"] <= 39]
    if short:
        print(f"  ⚠ 短单元（≤39 帧 = 1.63s）{len(short)} 个，多为反应句/金句 —— 这正是节奏，别合并：")
        for u in short[:8]:
            print(f"      {u['uid']} {u['dur_gen']:.2f}s({u['frames']}帧) 「{u['dialogue'][:26]}」")

    out = a.out or os.path.join(src, "units.json")
    json.dump({"film_dur": film_dur, "unit_count": len(units), "total_frames": tot,
               "gpu_single_h": round(gpu / 3600, 2), "units": units},
              open(out, "w"), ensure_ascii=False, indent=1)
    print(f"  → {out}")

    rv = os.path.join(os.path.dirname(out), f"换人复核表_{os.path.basename(src)}.md")
    n = write_review_sheet(units, film_dur, rv, a.review_thresh)
    print(f"  → {rv}  （待复核 {n} 个长单元）")


if __name__ == "__main__":
    main()
