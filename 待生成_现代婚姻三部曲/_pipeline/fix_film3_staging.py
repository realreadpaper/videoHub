#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
片3《加名之夜》prompt 二次修复（2026-09-18 下午）：

A. f3s06 人物关系/构图修正（用户截图：新郎与丈母娘并肩同侧、新娘消失）
   根因 1：几何自相矛盾 —— "Medium shot across the table + S1 foreground center"
   （S1 的脸朝镜头）意味着 S3/S2 若真在"桌子对面"，应该在镜头背后，画面里根本
   看不见。模型只能就近解决，把 S3 拉到 S1 身边。
   根因 2：关系词失锚 —— f3s06 是片3 唯一把 S3 只写成 "the 56-year-old mother"
   的镜（f3s02 写的是 mother-in-law）。"mother" 坐在新郎身边 → 被读成新郎的妈。
   修法：改为 90° 剖面对峙构图（两侧人脸都可见），S3 明确为
   "his future mother-in-law" 且与新娘并肩同侧；加"仅三人、无第四只手"约束
   （顺带治试拍复盘里的"半个第四人"）；补半地下室环境锚（治背景变暖色调餐厅）。

B. 片3 其余 4 镜 <d> 标签清除（f3s02/03/04/08）
   f3s02 的 <d> 正是"女人要的是一份定心丸"——不清除，"定心丸"字幕会在该镜复发。
   口型由 <Audio 1>（tts_dry 干声）驱动，台词不丢；dialogue_cn 保留在 manifest。

同步层：manifest.json（权威）→ wf/（384 草稿）→ wf_one/（一步直出成品）
        → prompts/f3sXX.txt（可读导出副本）。

用法： python3 fix_film3_staging.py
"""
import json, os, re

ROOT = "/Users/hejianglong/Desktop/videoHub/待生成_现代婚姻三部曲"
MANIFEST = os.path.join(ROOT, "03_奉俊昊_加名之夜/manifest.json")
WF_DIR = os.path.join(ROOT, "_pipeline/wf")
WF_ONE_DIR = os.path.join(ROOT, "_pipeline/wf_one")
PROMPTS_DIR = os.path.join(ROOT, "_pipeline/prompts")

PREAMBLE_TAG = "<Audio 1>"
PREAMBLE_FULL = (
    "<Audio 1> carries the original soundtrack of this scene: the actors' real voices, ambience and music. "
    "Keep the visual timing, phrasing, lip movement and performance locked to <Audio 1> exactly. "
    "Follow the shot description below exactly.\n\n"
)

# ---------- A. f3s06 三段替换 ----------
OLD1 = (
    "[00:00.000 – 00:05.042] Medium symmetrical shot across the formica table. "
    "In the foreground center sits <Subject 1> (S1), the 32-year-old slender groom in charcoal wool coat. "
    "He sits very still, shoulders relaxed, but his jaw is subtly tightened and a faint muscle ticks along his cheek. "
    "His rimless spectacles catch the bare bulb light as he slowly inhales, eyes cold and steady."
)
NEW1 = (
    "[00:00.000 – 00:05.042] Static 90-degree profile medium shot down the long side of the formica table, "
    "two camps squared off in tense mirror symmetry. Alone on the near side sits <Subject 1> (S1), "
    "the 32-year-old slender groom in charcoal wool coat, seen in right-facing profile. "
    "He sits very still, shoulders relaxed, but his jaw is subtly tightened and a faint muscle ticks along his cheek. "
    "His rimless spectacles catch the bare bulb light as he slowly inhales, eyes cold and steady."
)

OLD2 = (
    "[00:05.042 – 00:10.042] <Subject 1> (S1) delicately flattens <Prop 2>, the private debt paper, with two fingers, "
    "places it squarely on top of the co-ownership agreement, and delivers an icy verdict in Chinese. "
    "His lips move with measured precision, a brief, cold half-smile flickering at one corner of his mouth "
    "before vanishing as he studies their faces."
)
NEW2 = (
    "[00:05.042 – 00:10.042] <Subject 1> (S1) delicately flattens <Prop 2>, the private debt paper, with two fingers, "
    "places it squarely on top of the co-ownership agreement, and delivers an icy verdict in Chinese "
    "toward the two women opposite him. His lips move with measured precision, a brief, cold half-smile flickering "
    "at one corner of his mouth before vanishing as he studies their faces."
)

OLD3 = (
    "[00:10.042 – 00:15.083] Beside his chair rests a black leather briefcase. "
    "Across the table, <Subject 3> (S3) on the left blinks rapidly, her mouth slightly open, color draining from her cheeks, "
    "while <Subject 2> (S2) on the right looks away with a visible swallow and a trembling lower lip, "
    "both women's social masks cracking. <Subject 1> (S1) holds his breath for a beat, then exhales slowly, "
    "his expression settling into merciless clarity. "
    "cinematic 16:9 widescreen, ARRI Alexa look, shallow depth of field, fine film grain, naturalistic lighting, "
    "photorealistic, no subtitles, no captions, no on-screen text, no watermark, no logo."
)
NEW3 = (
    "[00:10.042 – 00:15.083] Beside his chair rests a black leather briefcase. "
    "Directly opposite him, seated shoulder to shoulder on the far side of the table as the bride's family "
    "and facing him in left-facing profile: <Subject 3> (S3), his 56-year-old future mother-in-law in a deep plum shawl, "
    "blinks rapidly, her mouth slightly open, color draining from her cheeks; beside her <Subject 2> (S2), "
    "her 28-year-old daughter the bride in ivory knit sweater, looks away with a visible swallow and a trembling lower lip, "
    "both women's social masks cracking. Exactly three people sit at this table, no fourth person, "
    "no extra hands or arms entering the frame. Behind the two women, the cramped dim semi-basement apartment: "
    "naked hanging bulb, rain-streaked street-level transom window, the red plastic bucket brimming at the rim. "
    "<Subject 1> (S1) holds his breath for a beat, then exhales slowly, his expression settling into merciless clarity. "
    "cinematic 16:9 widescreen, ARRI Alexa look, shallow depth of field, fine film grain, naturalistic lighting, "
    "photorealistic, no subtitles, no captions, no on-screen text, no watermark, no logo."
)

# ---------- B. <d> 标签 → 自然语言（口型由 <Audio 1> 干声驱动，台词不丢）----------
D_REPLACEMENTS = {
    "f3s02": (
        'and speaks in a sweet, suffocating tone: <d>[Chinese] "振浩啊，恩熙不是要分你的房子，女人要的是一份定心丸。"</d>',
        "and speaks in a sweet, suffocating tone in Chinese, each word drawn out slow and honeyed like a lullaby",
    ),
    "f3s03": (
        'She lowers the mug and whispers in an uneasy, defensive murmur: <d>[Chinese] "我妈也是为了咱们俩好……你签了，大家都体面。"</d>',
        "She lowers the mug and whispers in an uneasy, defensive murmur in Chinese, unable to meet his eyes",
    ),
    "f3s04": (
        'murmuring quietly: <d>[Chinese] "……什么东西卡在里面了。"</d>',
        "murmuring quietly to himself in Chinese, his brow beginning to furrow",
    ),
    "f3s08": (
        'murmuring with profound liberation: <d>[Chinese] "雨……终于淋不到我了。"</d>',
        "murmuring with profound liberation in Chinese, the words dissolving into the rain",
    ),
}


KEY_RE = re.compile(r"f3s0[1-8]")


def guard(path):
    """写盘护栏：规范化后必须仍落在 ROOT 内，杜绝 key 拼出 ../ 越界。"""
    p = os.path.realpath(os.path.normpath(path))
    root = os.path.realpath(os.path.normpath(ROOT))
    assert p.startswith(root + os.sep), f"路径越界: {path!r} -> {p}"
    return p


def sync_everywhere(key, new_prompt):
    """把同一份新 prompt 写进 manifest / wf / wf_one / prompts 导出。"""
    assert KEY_RE.fullmatch(key), f"非法镜头 key: {key!r}"
    fi, no = int(key[1]), int(key[3:])
    man_path = guard(glob_manifest(fi))
    m = json.load(open(man_path, encoding="utf-8"))
    shot = next(x for x in m["shots"] if x["no"] == no)
    assert f"shot{no:02d}_" in shot["file"], (key, shot["file"])
    shot["prompt"] = new_prompt
    json.dump(m, open(man_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    for d in (WF_DIR, WF_ONE_DIR):
        p = guard(os.path.join(d, f"wf_{key}.json"))
        if not os.path.exists(p):
            print(f"  [warn] 缺 {p}，跳过")
            continue
        w = json.load(open(p, encoding="utf-8"))
        assert w["6"]["inputs"]["prompt"].startswith(PREAMBLE_TAG)
        w["6"]["inputs"]["prompt"] = new_prompt
        json.dump(w, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # 可读导出副本（与旧约定一致：去掉 <Audio 1> 前导段）
    body = new_prompt.split("integrated_multimodal_description:", 1)
    export = ("integrated_multimodal_description:" + body[1]) if len(body) == 2 else new_prompt
    os.makedirs(PROMPTS_DIR, exist_ok=True)
    with open(guard(os.path.join(PROMPTS_DIR, f"{key}.txt")), "w", encoding="utf-8") as f:
        f.write(export)


def glob_manifest(fi):
    assert fi in (1, 2, 3), fi
    import glob as g
    hits = g.glob(os.path.join(ROOT, f"{fi:02d}_*", "manifest.json"))
    assert len(hits) == 1, hits
    return hits[0]


def main():
    man_path = glob_manifest(3)
    m = json.load(open(man_path, encoding="utf-8"))

    # A. f3s06
    shot6 = next(x for x in m["shots"] if x["no"] == 6)
    p = shot6["prompt"]
    for old in (OLD1, OLD2, OLD3):
        assert old in p, f"f3s06 段落未命中：{old[:60]}..."
    assert "<d>" not in p
    new6 = p.replace(OLD1, NEW1).replace(OLD2, NEW2).replace(OLD3, NEW3)
    assert "<d>" not in new6 and "future mother-in-law" in new6
    sync_everywhere("f3s06", new6)
    print("✓ f3s06 构图/人物关系已重写（剖面对峙 + mother-in-law 锚定 + 仅三人 + 环境锚）")

    # B. 其余 4 镜 <d>
    for key, (old, new) in D_REPLACEMENTS.items():
        no = int(key[3:])
        shot = next(x for x in m["shots"] if x["no"] == no)
        p = shot["prompt"]
        assert old in p, f"{key} <d> 子句未命中"
        assert p.count("<d>") == 1, f"{key} 存在多个 <d>，需人工处理"
        newp = p.replace(old, new)
        assert "<d>" not in newp
        sync_everywhere(key, newp)
        print(f"✓ {key} <d> 标签已清除 → 自然语言 in Chinese")

    # 终检：片3 全镜无 <d>
    m = json.load(open(man_path, encoding="utf-8"))
    left = [x["no"] for x in m["shots"] if "<d>" in x["prompt"]]
    print(f"片3 残留 <d> 镜头：{left if left else '无'}")


if __name__ == "__main__":
    main()
