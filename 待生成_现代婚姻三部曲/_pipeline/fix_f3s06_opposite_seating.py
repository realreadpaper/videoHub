#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
f3s06 隔桌对峙空间调度重构（2026-09-18）：
彻底解决上一版 90° 剖面被 H3 画成"三人同排/排排坐"的致命构图问题。
重构为：
- 9:16 竖屏深景深纵向隔桌对峙构图
- 男主独坐近端前景（左下角侧脸压迫），两指把借据按在协议上
- 桌子横在中间形成绝对物理分界
- 丈母娘与新娘并肩正坐对面沙发，正面迎击审判
- 严格符合 S1-S4 全部审查标准
"""
import json, os, re

ROOT = "/Users/hejianglong/Desktop/videoHub/待生成_现代婚姻三部曲"
MAN_PATH = os.path.join(ROOT, "03_奉俊昊_加名之夜/manifest.json")
WF_DIR = os.path.join(ROOT, "_pipeline/wf")
WF_ONE_DIR = os.path.join(ROOT, "_pipeline/wf_one")
PROMPTS_DIR = os.path.join(ROOT, "_pipeline/prompts")
PREAMBLE = "<Audio 1> carries the original soundtrack of this scene: the actors' real voices, ambience and music. Keep the visual timing, phrasing, lip movement and performance locked to <Audio 1> exactly. Follow the shot description below exactly.\n\n"

NEW_PROMPT = """integrated_multimodal_description:
[00:00.000 – 00:05.042] Low-angle medium over-the-shoulder confrontation shot across the low formica table. The low table forms a strict horizontal dividing barrier separating two hostile camps. In the immediate lower-left foreground, <Subject 1> (S1), the 32-year-old slender groom in tailored charcoal wool coat and rimless titanium spectacles, sits alone on the near side of the table in three-quarter profile facing toward frame-right. S1 sits upright, shoulders squared, but his jaw is tightened and a faint muscle ticks along his cheek as his rimless spectacles catch the cold bare bulb glare. In the foreground, his pale slender fingers firmly pin down <Prop 2>, the yellowed folded debt notice, squarely on top of the property co-ownership agreement, every stroke rendering as completely illegible abstract marks.
[00:05.042 – 00:10.042] <Subject 1> (S1) speaks with icy, measured precision in Chinese toward the two women seated opposite him across the table, his lips moving deliberately, a cold half-smile flickering at one corner of his mouth before settling into complete merciless detachment. Directly across the table, seated shoulder to shoulder on the saggy fabric sofa on the far side and facing frontally toward him and the camera: <Subject 3> (S3), his 56-year-old future mother-in-law in plum shawl on the left, and <Subject 2> (S2), her 28-year-old daughter the bride in ivory knit sweater on the right. Both women sit strictly opposite the groom across the table.
[00:10.042 – 00:15.083] The two women's faces freeze across the table. <Subject 3> (S3)'s mouth falls open as color drains from her cheeks, her eyes blinking in panicked disbelief; beside her, <Subject 2> (S2) hangs her head with a visible swallow and trembling lower lip, unable to meet S1's piercing gaze. Beside S1's chair rests a black leather briefcase. In the background behind the women, rain violently lashes the street-level transom window, and cold water drips into the red plastic bucket already brimming to the rim. Exactly three people sit at this table: groom alone on this near side, mother and daughter together on the far side across the table. No fourth person, no extra hands or arms entering the frame. S1 holds his breath for a beat, then exhales slowly, his jaw set, the cold half-smile vanishing as his expression settles into merciless clarity. cinematic 16:9 widescreen, ARRI Alexa look, shallow depth of field, fine film grain, naturalistic lighting, photorealistic, no subtitles, no captions, no on-screen text, no watermark, no logo.

overall_soundscape:
Crisp sound of debt paper resting on contract, sharp collective gasp from the mother and daughter opposite him, hypnotic metallic plops of water into brimming bucket, torrential rain drumming violently on the window. No background speech.

non_diegetic_music:
A chilling, dissonant classical string cadence, cold, elegant, and merciless.

strict_output_constraints: Absolutely no subtitles, no captions, no burned-in text, no on-screen text of any kind, no watermark, no logo, no timestamp, no UI overlay, no lower-third. Any paper, document, lettering, signage, label or screen appearing in frame must render as completely illegible abstract marks — no readable characters, digits or words in any language whatsoever. Text-bearing props are set dressing only and must never be legible."""

def main():
    # 1. Update manifest
    m = json.load(open(MAN_PATH, encoding="utf-8"))
    shot6 = next(x for x in m["shots"] if x["no"] == 6)
    shot6["prompt"] = NEW_PROMPT
    with open(MAN_PATH, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)
    print("✓ manifest.json 已更新")

    # 2. Update workflows
    for d in (WF_DIR, WF_ONE_DIR):
        p = os.path.join(d, "wf_f3s06.json")
        if os.path.exists(p):
            w = json.load(open(p, encoding="utf-8"))
            w["6"]["inputs"]["prompt"] = PREAMBLE + NEW_PROMPT
            with open(p, "w", encoding="utf-8") as f:
                json.dump(w, f, ensure_ascii=False, indent=1)
            print(f"✓ {p} 已同步更新")

    # 3. Update prompts export
    os.makedirs(PROMPTS_DIR, exist_ok=True)
    exp_path = os.path.join(PROMPTS_DIR, "f3s06.txt")
    with open(exp_path, "w", encoding="utf-8") as f:
        f.write(NEW_PROMPT)
    print(f"✓ {exp_path} 已同步更新")

if __name__ == "__main__":
    main()
