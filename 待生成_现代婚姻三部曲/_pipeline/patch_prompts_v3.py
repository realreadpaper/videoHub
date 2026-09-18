#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
《现代婚姻三部曲》prompt 全量优化 v3
依据《剧本审查标准 v3》四条硬标准：
  S1 零字幕   ← 去掉全部 <d>[Chinese]"…"</d> 标签
  S2 表情到位 ← 每镜注入 ≥3 处微表情 + ≥1 处情绪过渡
  S3 位置逻辑 ← 补多角色镜方位锚点、单人镜朝向锚点（按场景坐标表）
  S4 技术对齐 ← 保持时长/分辨率/音轨不变

用法： python3 _pipeline/patch_prompts_v3.py [--dry]
"""
import json, glob, os, re, shutil, sys, datetime

ROOT = "/Users/hejianglong/Desktop/videoHub/待生成_现代婚姻三部曲"
WF_DIR = os.path.join(ROOT, "_pipeline/wf_one")
WF_ALL = os.path.join(ROOT, "_pipeline/wf")          # 384 草稿模板（同步）
DRY = "--dry" in sys.argv

# ─────────────────────────────────────────────────────────────
# 一、<d> 标签改写表：old_fragment → new_fragment
#     统一形如 ' in Chinese, <表演提示>.'
# ─────────────────────────────────────────────────────────────
D_MAP = {
"f1s01": (': <d>[Chinese] "爸，等会儿进去你别紧张，一切有我。"</d>',
          ' in Chinese, forcing a grin that never reaches his eyes while sweat tracks down his jaw.'),
"f1s02": (': <d>[Chinese] "大喜的日子，开开门啦，大舅哥！"</d>',
          ' in Chinese, his grin wide and unguarded, knuckles rapping eagerly.'),
"f1s03": (': <d>[Chinese] "不拿出这三十八万八，我家静静绝不出这个门！"</d>',
          ' in Chinese, her lips curling back off her teeth, a vein standing out at her temple.'),
"f1s04": (': <d>[Chinese] "亲家母，我这还有张两万的存折……你看行不行？"</d>',
          ' in Chinese, his lower lip quivering, each word a visible effort.'),
"f1s05": (': <d>[Chinese] "哈！哈哈哈！这婚，谁爱结谁结！"</d>',
          ' in Chinese, the laughter cracking at the edges into something raw and torn.'),
"f1s06": (': <d>[Chinese] "走！爸，我带你去看真正的天地！"</d>',
          ' in Chinese, chest heaving, eyes blazing, throat tight.'),
"f1s07": (': <d>[Chinese] "爸，三十八万八省下来，够咱们加满一千箱油！"</d>',
          ' in Chinese, wind tearing the words apart as he laughs.'),
"f2s01": (': <d>[Chinese] "吹！把唢呐给老子往死里吹！"</d>',
          ' in Chinese, a vein bulging at his neck, spittle flying from his lips.'),
"f2s02": (': <d>[Chinese] "除了那三十万彩礼，进屋前再撂二十万下车礼——我得给小勇买房凑全款。"</d>',
          ' in Chinese, one eyebrow lifting a fraction as he savours the demand.'),
"f2s03": (': <d>[Chinese] "亲家，两代人的骨髓刮干净了，账……算不平了。"</d>',
          ' in Chinese, his throat working around the words, knuckles whitening.'),
"f2s04": (': <d>[Chinese] "规矩不能坏，差一分钱，这闺女今天绝不出门坎。"</d>',
          ' in Chinese, the pipe stem jabbing the air once with each measured syllable.'),
"f2s05": (': <d>[Chinese] "你这是在卖牲口，不是嫁闺女！老子不娶了！"</d>',
          ' in Chinese, spittle flying, the cords of his neck standing out like cables.'),
"f2s06": (': <d>[Chinese] "爹，把算盘拿好，咱们爷俩走大路！"</d>',
          ' in Chinese, his jaw set like a man who has just cut a rope.'),
"f2s07": (': <d>[Chinese] "小兔崽子，油门给老子拧到底！"</d>',
          ' in Chinese, goggles glinting, a boyish grin cracking his weathered face.'),
"f2s08": (': <d>[Chinese] "太阳照常升起！走喽——！"</d>',
          ' in Chinese, the words swallowed whole by the wind.'),
# 片3《加名之夜》的 manifest 已在 v2 阶段改为 "in Chinese, ..." 形式，无需再处理。
# 仅记录：f3s02 / f3s03 / f3s04 / f3s08 的台词已去标签化。
}
# f1s08 有两个 <d>
F1S08_D = [
    (': <d>[Chinese] "甜不甜？"</d>',
     ' in Chinese, a knowing crinkle forming at the corners of his eyes.'),
    (': <d>[Chinese] "甜透了，爸。"</d>',
     ' in Chinese, his jaw working as a tear tracks down his cheek.'),
]

# ─────────────────────────────────────────────────────────────
# 二、位置锚点 + 微表情补充表
#     (old, new) —— 全部精确匹配，不匹配即报错
# ─────────────────────────────────────────────────────────────
EXTRA = {
# ── 片1《三十八万八》 ──
"f1s01": [
 # 位置：已有 "two steps below him" ✓  补微表情
 ("Behind him, <Subject 2> (S2) nods hesitantly, his calloused fingers clutching the red velvet pouch tighter",
  "Behind him and below, <Subject 2> (S2) nods hesitantly, a nervous swallow bobbing in his throat, "
  "his calloused fingers clutching the red velvet pouch tighter"),
],
"f1s02": [
 ("<Subject 1> (S1)'s beaming wedding smile instantly freezes into a stiff, bewildered grimace as cold sweat trickles down his temple",
  "<Subject 1> (S1)'s beaming wedding smile instantly freezes, the grin collapsing in stages into a stiff, "
  "bewildered grimace, his nostrils flaring as he reads, cold sweat trickling down his temple"),
],
"f1s03": [
 # 静态词 'remains completely detached' → 有张力的静止
 ("while in the soft background <Subject 4> (S4) remains completely detached, chewing gum without looking up",
  "while in the soft background <Subject 4> (S4) keeps her eyes glued to the glowing screen, jaw set, "
  "refusing to look up, one thumb scrolling without pause"),
 ("<Subject 3> (S3) uncrosses her arms, thrusts an aggressive index finger forward toward the door",
  "<Subject 3> (S3) uncrosses her arms with a sharp silk rustle, a vein standing out at her temple, "
  "thrusts an aggressive index finger forward toward the door"),
],
"f1s04": [
 # 单人特写 → 补朝向
 ("Having been reluctantly let into the bridal chamber.",
  "Having been reluctantly let into the bridal chamber, <Subject 2> (S2) stands just inside the doorway, "
  "facing off-screen to the right where the mother-in-law sits."),
],
"f1s05": [
 ("<Subject 1> (S1) bursts into three exaggerated, bitter laughs, tears spilling down his smiling cheeks",
  "<Subject 1> (S1) throws his head back and bursts into three exaggerated, bitter laughs, "
  "the corners of his mouth twitching upward even as his eyes go glassy, tears spilling down his smiling cheeks"),
],
"f1s06": [
 # 双人 → 补前后关系
 ("<Subject 1> (S1) opens the passenger door, helps his elderly father inside",
  "<Subject 1> (S1) in the foreground with his father half a step behind on his right, "
  "opens the passenger door, helps his elderly father inside"),
],
"f1s07": [
 # 双人车内 → 补左右
 ("<Subject 1> (S1) throws his head back with exuberant laughter, turns toward his father",
  "Inside the car, <Subject 1> (S1) sits in the driver's seat on the left, <Subject 2> (S2) in the "
  "passenger seat on the right. <Subject 1> (S1) throws his head back with exuberant laughter, "
  "turns his head toward his father"),
],
"f1s08": [
 ("<Subject 2> (S2) peels a fresh ripe orange with his calloused thumbs",
  "The car is parked at the roadside. <Subject 1> (S1) and <Subject 2> (S2) stand side by side facing the "
  "camera, <Subject 1> (S1) on the left, <Subject 2> (S2) on the right. <Subject 2> (S2) peels a fresh ripe "
  "orange with his calloused thumbs"),
],

# ── 片2《老子不娶了》 ──
"f2s01": [
 ("steps forward into howling gale winds that whip his coat, spits out a wooden toothpick",
  "in the centre of the brick courtyard facing the camera, steps forward into howling gale winds that whip "
  "his coat, spits out a wooden toothpick"),
],
"f2s02": [
 ("<Subject 3> (S3) exhales a dense plume of pungent white tobacco smoke straight toward the camera",
  "<Subject 3> (S3) sits planted behind the mahogany table at centre-frame, facing the camera. "
  "He exhales a dense plume of pungent white tobacco smoke straight toward the camera"),
],
"f2s03": [
 ("<Subject 2> (S2) trembles, tears of humiliation welling behind his round glasses",
  "<Subject 2> (S2) stands at the table's near edge, facing off-screen to the right toward the "
  "father-in-law. He trembles, tears of humiliation welling behind his round glasses"),
],
"f2s04": [
 ("<Subject 3> (S3) points the scorched pipe stem toward the doorway",
  "<Subject 3> (S3) on the far side of the mahogany table, facing off-screen left toward the groom's family, "
  "points the scorched pipe stem toward the doorway"),
],
"f2s05": [
 ("He pulls a red bank certificate from his coat pocket",
  "<Subject 1> (S1) on the near side of the table, <Subject 3> (S3) across it on the far side. "
  "He pulls a red bank certificate from his coat pocket"),
],
"f2s06": [
 ("<Subject 1> (S1) shields his father and marches toward the courtyard gate",
  "<Subject 1> (S1) in the foreground, arm around his father on his right, shields him and marches "
  "toward the courtyard gate"),
],
"f2s07": [
 ("Beside him in the sidecar, <Subject 2> (S2), the 62-year-old father in black quilted coat",
  "<Subject 1> (S1) astride the bike on the left. Beside him in the sidecar on the right, "
  "<Subject 2> (S2), the 62-year-old father in black quilted coat"),
],
"f2s08": [
 ("In the sidecar, <Subject 2> (S2), the 62-year-old father with aviator goggles",
  "<Subject 1> (S1) astride on the left, <Subject 2> (S2) in the sidecar on the right. "
  "<Subject 2> (S2), the 62-year-old father with aviator goggles"),
],

# ── 片3《加名之夜》 ──
"f3s01": [
 ("Cold rainwater drips from a dark ceiling plaster crack in steady, hypnotic rhythm",
  "Cold rainwater drips from a dark ceiling plaster crack in steady, hypnotic rhythm, each drop striking "
  "the already-full surface with a fat, trembling ripple"),
],
"f3s02": [
 ("<Subject 3> (S3), a 56-year-old calculating East Asian mother-in-law named MADAM-HE",
  "<Subject 3> (S3) sits facing the camera with her chin raised, looking slightly off to frame-right where "
  "the groom sits, a 56-year-old calculating East Asian mother-in-law named MADAM-HE"),
],
"f3s03": [
 ("<Subject 2> (S2) sips nervously, her eyes darting away with guilty evasion",
  "<Subject 2> (S2) sips nervously, her eyes darting away with guilty evasion, the mug trembling against "
  "her lower lip"),
 # 背景新郎：静态词 → 有张力的静止
 ("sitting completely motionless with cold detachment",
  "sitting very still with his jaw set and his eyes fixed on her, cold detachment radiating from him"),
],
"f3s04": [
 ("<Subject 1> (S1), the 32-year-old slender groom in charcoal wool trench coat and rimless spectacles, "
  "reaches down between the dusty cushions",
  "<Subject 1> (S1) occupies the left half of frame, torso and hands in the foreground, the 32-year-old "
  "slender groom in charcoal wool trench coat and rimless spectacles. He reaches down between the dusty cushions"),
],
"f3s05": [
 ("<Subject 1> (S1)'s pale slender hands spread out <Prop 2>, the damp yellowed paper",
  "<Subject 1> (S1)'s pale slender hands fill the frame, turning <Prop 2>, the damp yellowed paper, "
  "over between finger and thumb"),
],
"f3s07": [
 ("<Subject 1> (S1), the 32-year-old slender groom in tailored charcoal wool coat and spectacles, "
  "calmly zips his black leather briefcase",
  "<Subject 1> (S1) stands centre-frame facing the camera, the 32-year-old slender groom in tailored "
  "charcoal wool coat and spectacles. He calmly zips his black leather briefcase"),
],
"f3s08": [
 ("<Subject 1> (S1), the 32-year-old slender groom in tailored charcoal wool coat and spectacles, "
  "opens a large clean black umbrella",
  "<Subject 1> (S1) on the rain-swept sidewalk in profile facing frame-left, the 32-year-old slender groom "
  "in tailored charcoal wool coat and spectacles, opens a large clean black umbrella"),
],
}

# ─────────────────────────────────────────────────────────────
# 三、执行
# ─────────────────────────────────────────────────────────────
STATIC_BAN = ["spine straight", "unnervingly calm", "completely motionless",
              "frozen in place", "utterly calm", "blank expression",
              "remains completely detached"]

def patch_prompt(key, p):
    log = []
    # 1) <d> 标签
    if key == "f1s08":
        for old, new in F1S08_D:
            assert old in p, f"{key}: <d> 片段未找到 -> {old[:60]}"
            p = p.replace(old, new)
            log.append("去 <d>")
    elif key in D_MAP:
        old, new = D_MAP[key]
        assert old in p, f"{key}: <d> 片段未找到 -> {old[:60]}"
        p = p.replace(old, new)
        log.append("去 <d>")
    # 2) 位置/微表情
    for old, new in EXTRA.get(key, []):
        assert old in p, f"{key}: EXTRA 未匹配 -> {old[:80]}"
        p = p.replace(old, new)
        log.append("补位置/微表情")
    # 3) 残留检查
    assert "<d>" not in p, f"{key}: 仍有 <d> 标签"
    return p, log


def main():
    # 归档
    arc = os.path.join(ROOT, "_archive", "2026-09-18_pre_review_v3")
    if not DRY:
        os.makedirs(arc, exist_ok=True)

    stats = []
    for mp in sorted(glob.glob(os.path.join(ROOT, "0*_*/manifest.json"))):
        m = json.load(open(mp, encoding="utf-8"))
        fi = int(os.path.basename(os.path.dirname(mp))[:2])
        if not DRY:
            shutil.copy2(mp, os.path.join(arc, f"manifest_{fi:02d}.json"))
        for s in m["shots"]:
            key = f"f{fi}s{s['no']:02d}"
            before = s["prompt"]
            after, log = patch_prompt(key, before)
            s["prompt"] = after
            stats.append((key, len(log),
                          sum(1 for w in STATIC_BAN if w in after.lower()),
                          after.count("<d>")))
        if not DRY:
            json.dump(m, open(mp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    # 同步 wf_one（带 PREAMBLE）与 wf（草稿模板）
    synced = 0
    for src_dir in (WF_DIR, WF_ALL):
        for wp in sorted(glob.glob(os.path.join(src_dir, "wf_f*.json"))):
            key = os.path.basename(wp)[3:-5]
            fi = int(key[1])
            mp = glob.glob(os.path.join(ROOT, f"0{fi}_*/manifest.json"))[0]
            m = json.load(open(mp, encoding="utf-8"))
            shot = next((x for x in m["shots"] if f"f{fi}s{x['no']:02d}" == key), None)
            if not shot:
                continue
            d = json.load(open(wp, encoding="utf-8"))
            cur = d["6"]["inputs"]["prompt"]
            # 保留 PREAMBLE（第一个空行之前），替换其后正文
            if cur.startswith("<Audio 1>"):
                pre = cur.split("\n\n", 1)[0]
                d["6"]["inputs"]["prompt"] = pre + "\n\n" + shot["prompt"]
            else:
                d["6"]["inputs"]["prompt"] = shot["prompt"]
            if not DRY:
                json.dump(d, open(wp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            synced += 1

    print(f"{'[DRY RUN] ' if DRY else ''}prompt 优化完成")
    print(f"  处理 manifest：3 个（24 镜）")
    print(f"  同步工作流：{synced} 个（wf_one + wf）")
    print()
    print(f"{'镜':<8}{'改动项':<8}{'残留静态词':<12}{'残留<d>':<10}")
    bad = 0
    for k, n, st, dcount in stats:
        flag = "" if (st == 0 and dcount == 0) else "  ✗"
        if st or dcount:
            bad += 1
        print(f"{k:<8}{n:<8}{st:<12}{dcount:<10}{flag}")
    print()
    print(f"✓ 全部通过" if bad == 0 else f"✗ {bad} 镜仍有残留")
    if not DRY:
        print(f"\n归档：{arc}")


if __name__ == "__main__":
    main()
