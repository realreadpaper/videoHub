#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成「逐镜时间轴剧本」——每镜锁死起止时间与帧数，从根上解决拖沓。

输入：原片拆解产物（shots.json / shots.md / framing.json）
输出：剧本_01报恩_逐镜时间轴.md + shots_full.json（生产用中间数据）

核心：每镜 length = 原片该镜时长吸附到 H3 栅格（17n+5 帧 @24fps），
     不再一律 14.75s。成片时长因此回到原片量级。
"""
import json, os, re, glob

VID = "7661613126736204025"
BASE = f"/Users/jianglong/Desktop/videoHub/videos/douyin_refs/2026-09-18/{VID}"
OUT = "/Users/jianglong/Desktop/videoHub/videos/douyin_refs/2026-09-18/_remake"

# ---- 栅格：H3 length ∈ 17n+5 ----
# ★ 必须向上吸附（≥ 原片镜长）：短了会把该镜尾音切掉，口型后半截丢失。
#   多出来的部分在拼片时裁掉，成片时长仍精确等于原片。
GRID = [(n, 17 * n + 5, (17 * n + 5) / 24) for n in range(1, 25)]
def snap(dur):
    up = [g for g in GRID if g[2] >= dur - 1e-6]
    return up[0] if up else GRID[-1]

# ---- 叙事段落（来自 ANALYSIS.md）----
SEGMENTS = [
    (0.0,   14.0,  "① 弃", "父亲当街驱逐，男孩一无所有", "夜色旧巷/家门口，冷调"),
    (14.0,  47.0,  "② 收", "老赵把他带进屋、擦药、端出红烧肉", "餐馆后门→店内，暖光"),
    (47.0,  82.0,  "③ 传", "留下帮工，教刀工、教这包酱", "厨房灶台，烟火气"),
    (82.0,  101.0, "④ 出去", "男孩要出去闯，老赵塞酱送别", "店门口，黄昏"),
    (101.0, 124.0, "⑤ 成", "十年后成了周总，店里十年只用同一款酱", "明亮餐馆，客人满座"),
    (124.0, 178.0, "⑥ 回", "回老店看叔，用同一包酱做给叔吃", "老店灶台，旧而温暖"),
    (178.0, 259.0, "⑦ 产品段", "自然切口播：电饭锅做排骨 + 9.9 五包", "厨房演示，产品特写"),
    (259.0, 999.0, "⑧ 接", "当年您接我进来，现在换我接您走", "老店门口，夕阳"),
]
def seg_of(t):
    for lo, hi, tag, func, scene in SEGMENTS:
        if lo <= t < hi:
            return tag, func, scene
    return SEGMENTS[-1][2], SEGMENTS[-1][3], SEGMENTS[-1][4]

# ---- 说话人（按剧情逐镜标注）----
SPEAKER = {
    1:"父亲",2:"父亲",3:"父亲",4:"小周(少年)",5:"父亲",6:"小周(少年)",7:"小周(少年)",8:"小周(少年)",9:"小周(少年)",
    10:"老赵",11:"老赵",12:"老赵→小周",13:"老赵",14:"老赵",15:"老赵",16:"老赵",17:"老赵",18:"老赵",19:"老赵→小周",
    20:"老赵",21:"小周→老赵",22:"老赵",23:"客人",24:"老赵",25:"老赵",26:"老赵",27:"老赵",28:"老赵",29:"老赵",
    30:"老赵",31:"老赵",32:"老赵",33:"客人",34:"客人→小周",35:"小周→老赵",36:"老赵",37:"老赵",38:"老赵",
    39:"店员",40:"店员",41:"店员",42:"店员",43:"厨师",44:"店员→周总",45:"周总",46:"助理",47:"助理→周总",48:"周总",
    49:"助理→周总",50:"周总",51:"周总→老赵",52:"老赵→周总",53:"周总→老赵",54:"老赵",55:"周总",56:"周总",57:"周总",
    58:"周总",59:"周总",60:"周总",61:"周总",62:"周总",63:"周总→老赵",64:"老赵→周总",65:"周总",66:"周总",67:"周总",
    68:"周总",69:"周总(转口播)",70:"口播",71:"口播",72:"口播",73:"口播",74:"口播",75:"口播",76:"口播",77:"口播",
    78:"口播",79:"口播",80:"老赵",81:"口播",82:"口播",83:"口播",84:"口播",85:"口播",86:"口播",
    87:"周总",88:"周总",89:"周总",90:"周总",91:"周总",92:"老赵",93:"周总",94:"周总",95:"老赵→周总",96:"老赵",
    97:"周总→老赵",98:"老赵",99:"老赵(收尾)",
}

def load():
    shots = json.load(open(f"{BASE}/shots.json"))
    shots = shots if isinstance(shots, list) else shots.get("shots", shots)
    framing = json.load(open(f"{BASE}/framing.json"))
    # 台词
    lines = {}
    for ln in open(f"{BASE}/shots.md", encoding="utf-8"):
        m = re.match(r"\|\s*(\d+)\s*\|\s*([\d:.]+)\s*\|\s*([\d.]+)s\s*\|\s*(.*?)\s*\|", ln)
        if m:
            lines[int(m.group(1))] = m.group(4).strip()
    return shots, framing, lines

def main():
    shots, framing, lines = load()
    fkeys = {float(k): v for k, v in framing.items()}

    rows = []
    for s in shots:
        idx = s["index"]
        st, du = s["start"], s["duration"]
        n, frames, sec = snap(du)
        # 参考帧（framing key 用时刻匹配）
        fk = min(fkeys, key=lambda k: abs(k - s["mid"])) if fkeys else None
        fr = fkeys.get(fk, {})
        tag, func, scene = seg_of(st)
        rows.append({
            "index": idx, "start": st, "end": st + du, "dur": du,
            "frames": frames, "sec": round(sec, 3), "n": n,
            "framing": fr.get("framing", ""), "faces": fr.get("faces", 0),
            "face_ratio": fr.get("face_ratio", 0), "kf": fr.get("file", ""),
            "speaker": SPEAKER.get(idx, ""), "line": lines.get(idx, ""),
            "seg": tag, "func": func, "scene": scene,
            "delta": round(sec - du, 3),
        })

    # ---- 输出 md ----
    md = ["# 逐镜时间轴剧本 · 01 被抛弃男孩报恩",
          "",
          f"> 原片 `{VID}` · 时长 **295.7s（4:56）** · **99 镜** · 平均 2.99s/镜",
          "> 每镜时长 **锁死为原片镜长**（吸附到 H3 栅格 17n+5 @24fps），不许自行注水。",
          "> 声音：**沿用原片音轨**（每镜按 start/end 切片），不用 TTS，音色与环境音天然全对。",
          ""]
    tot_new = sum(r["sec"] for r in rows)
    md += [f"生成总长 **{tot_new:.1f}s**（向上吸附，保证每镜 ≥ 原片镜长，尾音不被切）",
           f"→ 拼片时逐镜裁回原片镜长，**成片精确 295.7s（4:56）**，与原片等长",
           f"GPU 机时预估 **{sum(max(0,0.812*r['frames']+0.002129*r['frames']**2-1.3) for r in rows)/3600:.2f}h**（双卡挂钟 ≈ 一半）",
           "", "## 段落总览", "",
           "| 段 | 时间 | 功能 | 场景 | 镜号 |", "|---|---|---|---|---|"]
    for lo, hi, tag, func, scene in SEGMENTS:
        ids = [str(r["index"]) for r in rows if r["seg"] == tag]
        hs = SEGMENTS[0]
        rng = f"{ids[0]}–{ids[-1]}" if ids else "—"
        tstr = f"{lo:.0f}–{hi:.0f}s" if hi < 900 else f"{lo:.0f}s–结尾"
        md.append(f"| {tag} | {tstr} | {func} | {scene} | {rng} |")

    md += ["", "## 逐镜表", "",
           "| 镜 | 起止 | 时长 | 帧数/秒 | 景别 | 说话人 | 台词 | 段落 | 参考帧 |",
           "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        mm1, ss1 = divmod(r["start"], 60)
        mm2, ss2 = divmod(r["end"], 60)
        rng = f"{int(mm1):02d}:{ss1:05.2f}–{int(mm2):02d}:{ss2:05.2f}"
        md.append(f"| {r['index']} | {rng} | {r['dur']:.2f}s | {r['frames']}帧/{r['sec']}s | "
                  f"{r['framing']} | {r['speaker']} | {r['line']} | {r['seg']} | `{r['kf']}` |")

    md += ["", "## 生产参数（喂 H3）", "",
           "```",
           f"权重    Minimax-h3_Singularity_ref2va_Pruned_v1.3_int8（原声锁）",
           f"加速    Turbo LoRA 4 步 + dual_clock_euler/native_flow + ck-attention（TeaCache 禁用）",
           f"分辨率  768×1344 @24fps",
           f"length  逐镜不同：见上表「帧数」列（17n+5 栅格）",
           f"音频    原片音轨按 start/end 切片、尾部补静音到 length → input/dy_full_a/<镜号>.wav（驱动口型）",
           f"        ★ length 向上吸附，保证 ≥ 原片镜长，尾音不会被切",
           f"参考图  keyframes/<参考帧> → ref_images.ref_image_0（锁画面/构图/人物）",
           f"成片音轨 原片完整音轨（人声+环境音+BGM 全保留），不取 H3 输出音频",
           "```", "",
           "## 为什么这样就不拖沓了", "",
           "- 旧做法：每镜固定 14.75s → 11 镜撑满 2:42，**是原片镜长的 5–7.7 倍**，每个镜头都在注水。",
           "- 新做法：每镜 = 原片真实镜长（0.92–6.17s，均值 2.99s），**剪回原片节奏**，成片自动回到 ~4:56。",
           "- 附带收益：帧数从 354 降到 22–154，注意力是 O(N²)，单镜耗时 **从 553s 降到 18–110s**，",
           "  全片 99 镜 GPU 机时约 1.9h（双卡挂钟约 1h），比注水版便宜一个数量级。",
           ]

    out_md = f"{OUT}/剧本_01报恩_逐镜时间轴.md"
    open(out_md, "w", encoding="utf-8").write("\n".join(md) + "\n")

    json.dump(rows, open(f"{OUT}/shots_full.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print(f"[✓] 剧本 → {out_md}")
    print(f"[✓] 生产数据 → {OUT}/shots_full.json（{len(rows)} 镜）")
    print(f"    吸附后总时长 {tot_new:.1f}s / 原片 295.7s")
    from collections import Counter
    print(f"    帧数分布 {dict(sorted(Counter(r['frames'] for r in rows).items()))}")
    print(f"    GPU 机时 {sum(max(0,0.812*r['frames']+0.002129*r['frames']**2-1.3) for r in rows)/3600:.2f}h")

if __name__ == "__main__":
    main()
