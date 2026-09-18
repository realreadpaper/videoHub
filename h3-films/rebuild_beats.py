#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
重排动作段 + 注入表情描述（解决「表情没配合上」与「动作粒度对不上台词」）

问题回顾
--------
原始 manifest 把每镜一律切成「3 段 × 5 秒」，但每镜台词节奏差 8 倍：
镜5 每 1.9 秒一句，镜19 一句铺满 15 秒。结果——
  · 情绪转折点落在某段中间，而 prompt 对这段只写了一个中性动作；
  · 模型只能用一个表情走完 5 秒，该转的情绪没转。
另外实测：35 个「画面里有人」的动作段中，只有 12 段写了表情（缺口 66%）。

本工具怎么修
------------
1. 用**干声实测的逐句时间**（`_tts/<film>/shotNN_lines.json` 里的 t/dur）作为切分依据，
   把 15 秒重排成「一句台词一段」，让 prompt 的粒度跟台词对齐。
2. 给每一段补上说话人此刻的**面部表情描述**（眉/眼/嘴/下颌/呼吸），
   情绪由规则表推断，可被 override 表覆盖。
3. 原动作描述按时间重叠度分配到新段里，不丢信息。
4. 输出新 manifest + 一份**逐句审阅表**，让你先看再跑。

用法
----
  python rebuild_beats.py --manifest film1-office/manifest.json \
      --lines _tts/film1 --shots 2,3,4,10,14,19,20 \
      --out-manifest _review/manifest_beats.json \
      --out-review   _review/表情注入审阅表.md
"""
import argparse
import json
import os
import re

# ── 情绪规则表：关键词 → (情绪标签, 面部描述) ───────────────────────────
# 面部描述刻意写成「可被视频模型执行」的英文：眉/眼/嘴/下颌/呼吸，而非抽象情绪词。
RULES = [
    (r"赔得起|你这种|别挡我|势在必得|最需要我|懂形象管理",
     ("傲慢轻蔑", "chin lifted, eyes narrowed with contempt, one corner of the mouth pulled up in a cold smirk, nostrils slightly flared")),
    (r"你饿关我什么事|不是救助站|管不好|难听|嫌弃|什么味",
     ("冷淡嫌恶", "lips pressed thin and turned down, eyes flicking away in disdain, a tight disapproving crease between the brows")),
    (r"帮|扶|搭把手|麻烦你|能不能",
     ("虚弱恳切", "brows drawn up in the middle, eyes soft and pleading, mouth slightly open with effort, jaw slack with fatigue")),
    (r"谢谢|好姑娘|愿意把自己的|珍贵|这一关过了|过不了",
     ("温和欣慰", "eyes crinkling warmly at the corners, a slow genuine smile softening the whole face, shoulders relaxing")),
    (r"不缺会写简历|缺的是有良心|不只看简历|良心不能没有|手艺也得过关|今天你先用",
     ("沉稳笃定", "steady level gaze, jaw set, brows calm and unhurried, the faintest approving tilt of the head")),
    (r"我刚才真的不知道|会不会不太礼貌|那我|真的|对不起",
     ("错愕心虚", "eyes widening a beat too late, blink quickening, lips parting then pressing together, a flush rising along the cheekbones")),
    (r"对不对|颠覆|轻轻松松|搞定|简单|点击左下角|九块九|拼手速|包邮|厨房之光|懒人",
     ("热情自信", "bright open eyes meeting the lens directly, an easy confident smile, animated brows lifting on each beat")),
    (r"直接脱骨|一戳就脱骨|出锅的色泽|软烂|红亮|吸满",
     ("惊喜满足", "eyes going round with delight, brows lifting high, a small involuntary smile of pure satisfaction")),
    (r"怎么办|来不及|出事",
     ("焦急担忧", "brows pinched together, eyes wide and urgent, mouth tight with worry")),
]
DEFAULT = ("平静中性", "expression composed and unreadable, gaze steady, mouth relaxed and closed")

# 说话人语速/语气基调（同一情绪在不同人身上力度不同）
SPEAKER_BIAS = {
    "S1": "restrained and deliberate, emotion held just under the surface",
    "S2": "warm and sincere, emotion shown openly",
    "S3": "abrupt and self-important, emotion pushed to the front",
    "S4": "cold and clipped, emotion tight and controlled",
    "S5": "deferential and low-key",
}


def guess_emotion(text, speaker):
    for pat, (label, desc) in RULES:
        if re.search(pat, text):
            return label, desc
    return DEFAULT


def parse_action_beats(prompt):
    """从原 prompt 里抽出 [时间码] 的动作段，返回 [(start, end, text)]。"""
    seg = prompt[prompt.find("[00:00.000"):prompt.find("overall_soundscape")]
    out = []
    for line in seg.strip().split("\n"):
        line = line.strip()
        m = re.match(r"\[(\d+):(\d+\.\d+)\s*[–-]\s*(\d+):(\d+\.\d+)\]\s*(.*)", line)
        if m:
            s = int(m.group(1)) * 60 + float(m.group(2))
            e = int(m.group(3)) * 60 + float(m.group(4))
            out.append((s, e, m.group(5).strip()))
    return out


def overlap(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def fmt(t):
    return "%02d:%06.3f" % (int(t // 60), t % 60)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--lines", required=True, help="干声目录（含 shotNN_lines.json）")
    ap.add_argument("--shots", default="", help="要处理的镜号，逗号分隔；空=全部")
    ap.add_argument("--out-manifest", required=True)
    ap.add_argument("--out-review", required=True)
    ap.add_argument("--tail", type=float, default=0.0,
                    help="每镜尾部裁掉多少秒（治拖沓用；0=不裁）")
    args = ap.parse_args()

    m = json.load(open(args.manifest))
    shots = m["shots"] if isinstance(m, dict) and "shots" in m else m
    want = set(int(x) for x in args.shots.split(",") if x.strip()) if args.shots else None

    review = ["# 表情注入审阅表", "",
              "> 每段一行。情绪由关键词规则推断，**你可以直接改这份表**，改完重跑即可。",
              "> 面部描述写成了可执行的英文（眉/眼/嘴/下颌），不是抽象情绪词。", ""]
    changed = 0

    for s in shots:
        if want and s["no"] not in want:
            continue
        lf = os.path.join(args.lines, "shot%02d_lines.json" % s["no"])
        if not os.path.exists(lf):
            print("跳过 镜%d：找不到 %s" % (s["no"], lf))
            continue
        lines = json.load(open(lf))
        acts = parse_action_beats(s["prompt"])
        if not acts or not lines:
            continue

        # ── 按台词实测时间重排段边界 ──
        bounds = []
        for i, ln in enumerate(lines):
            st = ln["t"]
            en = st + ln["dur"]
            if i + 1 < len(lines):
                en = min(en + 0.35, lines[i + 1]["t"])   # 段尾带到下一句起头，留一点反应时间
            bounds.append((st, en, ln))

        # 原动作段只分配给「与它重叠最大」的那一个新段，避免相邻几段复读同一句动作。
        # 做法：对每个原动作段，找重叠最大的新段下标，占据它。
        assign = {}
        for ai, (a0, a1, _txt) in enumerate(acts):
            bi_ov, bi_idx = -1.0, None
            for ni, (st, en, _ln) in enumerate(bounds):
                ov = overlap(st, en, a0, a1)
                if ov > bi_ov:
                    bi_ov, bi_idx = ov, ni
            if bi_idx is not None and bi_idx not in assign:
                assign[bi_idx] = ai

        # 没分到原动作的段，用一句中性的「承接动作」，不要空着也不要复读
        FILLERS = [
            "the shot holds on {sp}, weight shifting subtly",
            "{sp} draws a short breath and settles into the next line",
            "a small beat of stillness on {sp} before the reply lands",
        ]

        new_beats, rows, flagged = [], [], []
        for ni, (st, en, ln) in enumerate(bounds):
            if ni in assign:
                best = acts[assign[ni]][2]
                # 原动作段若压根没提到这个说话人，说明它属于别人——那不如用中性承接动作，
                # 否则会出现"动作写的是 S4 站着、台词却是 S1 在说"的错配。
                if ln["speaker"] not in best:
                    flagged.append((ni, ln["speaker"], best[:44]))
                    best = None
            else:
                best = None
            if best is None:
                best = FILLERS[ni % len(FILLERS)].format(sp=ln["speaker"])
            label, face = guess_emotion(ln["text"], ln["speaker"])
            bias = SPEAKER_BIAS.get(ln["speaker"], "")
            head = re.sub(r"\s*cinematic 9:16.*$", "", best)       # 去掉原段尾的风格串
            head = head.rstrip(" ,.")
            body = ("%s %s, delivering: \"%s\" — face: %s; %s."
                    % (head + "." if head else "", ln["speaker"], ln["text"][:34], face, bias))
            new_beats.append("[%s – %s] %s" % (fmt(st), fmt(en), body))
            rows.append((ln["speaker"], ln["text"], label,
                         "%s – %s" % (fmt(st), fmt(en)), ln["dur"]))

        # ── 拼回 prompt（保留角色/场景/尾串）──
        p = s["prompt"]
        head = p[:p.find("[00:00.000")]
        tail = p[p.find("overall_soundscape"):]
        style = re.search(r"(cinematic 9:16[^\n]*)", p)
        style = style.group(1) if style else "cinematic 9:16 vertical, photorealistic live-action footage"
        s["prompt_original"] = p
        s["prompt"] = head + "\n".join(new_beats) + " " + style + "\n\n" + tail
        s["beats_v2"] = [{"start": r[3].split(" – ")[0], "speaker": r[0], "emotion": r[2]} for r in rows]
        changed += 1

        review.append("## 镜 %d　%s" % (s["no"], s.get("framing", "")))
        review.append("")
        if flagged:
            review.append("> ⚠ 以下段落的原动作描述所属人物与说话人不一致，已自动换成中性承接动作，请重点复核：")
            for _ni, _sp, _tx in flagged:
                review.append("> - `%s` —— 原描述「%s…」" % (_sp, _tx))
            review.append("")
        review.append("| 说话人 | 台词 | 推断情绪 | 时段 | 时长 |")
        review.append("|---|---|---|---|---|")
        for sp, tx, lb, rng, du in rows:
            review.append("| %s | %s | **%s** | %s | %.2fs |" % (sp, tx[:30], lb, rng, du))
        review.append("")

    m_out = m if isinstance(m, dict) else {"shots": shots}
    if isinstance(m, dict) and "shots" in m:
        m_out["shots"] = shots
    json.dump(m_out, open(args.out_manifest, "w"), ensure_ascii=False, indent=1)
    open(args.out_review, "w").write("\n".join(review))

    print("✔ 处理 %d 镜" % changed)
    print("  · 新 manifest → %s" % args.out_manifest)
    print("  · 审阅表     → %s" % args.out_review)


if __name__ == "__main__":
    main()
