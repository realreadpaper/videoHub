#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
prompt 优化 v3 第二轮：补 S2（表情）与 S3（位置）

S2：每镜在 "cinematic 16:9 widescreen" 前注入一句**定制**的情绪收束句，
    内含 ≥3 处微表情 + ≥1 处情绪过渡。
S3：给缺朝向锚点的单人镜补朝向。

用法： python3 _pipeline/patch_prompts_v3b.py [--dry]
"""
import json, glob, os, sys, shutil

ROOT = "/Users/hejianglong/Desktop/videoHub/待生成_现代婚姻三部曲"
WF_DIR = os.path.join(ROOT, "_pipeline/wf_one")
WF_ALL = os.path.join(ROOT, "_pipeline/wf")
DRY = "--dry" in sys.argv
ANCHOR = ", cinematic 16:9 widescreen"

# 情绪收束句（按镜定制；含 ≥3 微表情 + ≥1 过渡）
EMO = {
"f1s01": "His jaw tightens as he speaks, a muscle twitching at his temple, a bead of sweat trembling at his jawline; "
         "the grin flickers, then settles into something far more determined than confident",
"f1s02": "His nostrils flare and his lips part soundlessly, a nervous swallow bobbing in his throat, "
         "the frozen smile cracking at one corner before draining entirely from his face",
"f1s03": "Her jaw works with every syllable, one nostril flaring in open contempt, the predatory glare "
         "flickering wider then settling into flat triumph, while behind her the bride never once blinks",
"f1s04": "His jaw works, his throat clicking on a dry swallow, the pleading light in his eyes flickering "
         "then fading into resigned humiliation, the tears trembling at the rim but never falling",
"f1s05": "The laughter cracks and begins breaking into raw sobs, his jaw trembling, nostrils flaring, "
         "tears spilling freely as the grin shatters into something naked",
"f1s06": "His jaw sets hard, a muscle twitching along it, his chest heaving on one long exhale, "
         "the triumphant grin hardening into grim determination",
"f1s07": "Beside him his father's weathered face works through a slow swallow, a smile flickering at his "
         "lips then settling into quiet peace as his eyes crinkle shut against the wind",
"f1s08": "The old man's jaw works on a slow swallow, his eyes glistening as a tear trembles at the rim "
         "then slips down his cheek; his son blinks twice, fighting the sting behind his own eyes",
"f2s01": "A vein pulses at his temple, his jaw jutting, his nostrils flaring, the fierce glare flickering "
         "even wider before settling into pure obstinate command",
"f2s02": "His eyes narrow to slits, one eyebrow lifting, his lip curling, a slow blink of satisfaction, "
         "the smug sneer flickering into something colder as he savours his own arithmetic",
"f2s03": "The old man's chin quivers, a tear escaping to tremble at his jaw, his throat working around "
         "the words, the last syllable fading into a broken whisper",
"f2s04": "His jaw juts, one nostril flaring, the narrowed eyes flickering with contempt before settling "
         "into flat rural finality, a single slow blink punctuating the verdict",
"f2s05": "His eyes are red-rimmed, nostrils flaring, teeth clenched so hard the jaw shakes, the rage in "
         "his face then hardening into something immovable and cold",
"f2s06": "His jaw is set like stone, a muscle jumping in his cheek, and he exhales slowly and steadily "
         "through his nose, the pride in his face hardening with every stride",
"f2s07": "The old man throws his head back, his jaw working with glee, his chin trembling with laughter, "
         "nostrils flaring in the wind, the grin cracking his weathered face wide open",
"f2s08": "The father's mouth works soundlessly, his jaw slack with wonder, a slow blink into the blinding "
         "glare, then his whole face breaks into a grin as laughter cracks through him",
"f3s01": "A last drop trembles on the bucket's brim, quivering before the surface shudders and spills "
         "quietly over the edge, the dark overflow creeping outward across the linoleum",
"f3s02": "Her head tilts a fraction, her eyes narrowing with calculation, a slow blink, the honeyed smile "
         "flickering at the corners of her mouth before settling into something distinctly colder",
"f3s03": "A muscle twitches beneath her eye, her throat working around a dry swallow, the guilty smile "
         "flickering then vanishing as her gaze skitters away again",
"f3s04": "His brow furrows, his jaw tightening as his fingers close on the stiff bundle; he blinks once, "
         "slowly, the frown hardening into wary focus",
"f3s05": "His fingers tremble faintly as they turn the damp page, his knuckles whitening around the "
         "crumpled edge, one fingertip quivering above the crimson thumbprints, the tremor settling into stillness",
"f3s07": "His expression stays flat, a single muscle ticking in his jaw, one slow blink as the latch "
         "clicks home, the mask settling into something colder and emptier",
"f3s08": "His shoulders drop as he exhales a long breath, the tension draining from his jaw and neck, "
         "a faint smile flickering at his lips then settling into something close to peace",
}

# S3：单人镜补朝向
ORIENT = {
"f1s05": ("<Subject 1> (S1) throws his head back and bursts into",
          "<Subject 1> (S1) facing the camera throws his head back and bursts into"),
"f3s05": ("<Subject 1> (S1)'s pale slender hands fill the frame",
          "<Subject 1> (S1)'s pale slender hands fill the frame in a top-down shot"),
"f1s02": ("Close-up static shot facing a heavy rust-spotted steel security door",
          "Close-up static shot, the camera facing a heavy rust-spotted steel security door, "
          "<Subject 1> (S1) turned toward it"),
}


def main():
    arc = os.path.join(ROOT, "_archive", "2026-09-18_pre_review_v3b")
    if not DRY:
        os.makedirs(arc, exist_ok=True)

    report = []
    for mp in sorted(glob.glob(os.path.join(ROOT, "0*_*/manifest.json"))):
        m = json.load(open(mp, encoding="utf-8"))
        fi = int(os.path.basename(os.path.dirname(mp))[:2])
        if not DRY:
            shutil.copy2(mp, os.path.join(arc, f"manifest_{fi:02d}.json"))
        for s in m["shots"]:
            key = f"f{fi}s{s['no']:02d}"
            p = s["prompt"]
            acts = []
            # S2 情绪收束
            if key in EMO and ANCHOR in p:
                assert EMO[key] not in p, f"{key} 已注入过"
                p = p.replace(ANCHOR, f", {EMO[key]}{ANCHOR}", 1)
                acts.append("S2情绪")
            # S3 朝向
            if key in ORIENT:
                old, new = ORIENT[key]
                assert old in p, f"{key}: 朝向锚点未匹配 -> {old[:60]}"
                p = p.replace(old, new, 1)
                acts.append("S3朝向")
            s["prompt"] = p
            report.append((key, acts))
        if not DRY:
            json.dump(m, open(mp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    # 同步工作流
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
            if cur.startswith("<Audio 1>"):
                pre = cur.split("\n\n", 1)[0]
                d["6"]["inputs"]["prompt"] = pre + "\n\n" + shot["prompt"]
            else:
                d["6"]["inputs"]["prompt"] = shot["prompt"]
            if not DRY:
                json.dump(d, open(wp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            synced += 1

    print(f"{'[DRY RUN] ' if DRY else ''}第二轮完成")
    print(f"{'镜':<8}{'动作'}")
    for k, a in report:
        print(f"{k:<8}{', '.join(a) if a else '（无需改动）'}")
    print(f"\n同步工作流 {synced} 个")
    if not DRY:
        print(f"归档：{arc}")


if __name__ == "__main__":
    main()
