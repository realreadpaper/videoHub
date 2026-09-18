#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第三轮精修：补齐 5 处 S2/S3 未达标项"""
import json, glob, os, shutil

ROOT = "/Users/hejianglong/Desktop/videoHub/待生成_现代婚姻三部曲"
FIX = {
# S3：f1s02 补朝向锚点（角色面朝门 = 背对镜头）
("f1s02", "<Subject 1> (S1) turned toward it",
          "<Subject 1> (S1) facing the door, his back to the camera"),
# S2：f2s05 微表情 2→3+
("f2s05", "teeth clenched so hard the jaw shakes",
          "teeth clenched so hard his jaw trembling shakes"),
# S2：f2s08 微表情 2→3+
("f2s08", "his jaw slack with wonder, a slow blink into the blinding glare",
          "his nostrils flaring, his jaw working soundlessly, a slow blink into the blinding glare"),
# S2：f3s07 微表情 2→3+
("f3s07", "a single muscle ticking in his jaw",
          "his jaw tightening, a single muscle ticking in it"),
}
arch = os.path.join(ROOT, "_archive", "2026-09-18_pre_review_v3c")
os.makedirs(arch, exist_ok=True)
for mp in sorted(glob.glob(os.path.join(ROOT, "0*_*/manifest.json"))):
    m = json.load(open(mp, encoding="utf-8")); fi = int(os.path.basename(os.path.dirname(mp))[:2])
    shutil.copy2(mp, os.path.join(arch, f"manifest_{fi:02d}.json"))
    for s in m["shots"]:
        k = f"f{fi}s{s['no']:02d}"
        for key, old, new in FIX:
            if key == k:
                assert old in s["prompt"], f"{k} 未匹配: {old[:50]}"
                s["prompt"] = s["prompt"].replace(old, new, 1)
                print(f"  ✓ {k} 修正")
    json.dump(m, open(mp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
# 同步工作流
for src in ("_pipeline/wf_one", "_pipeline/wf"):
    for wp in sorted(glob.glob(os.path.join(ROOT, src, "wf_f*.json"))):
        key = os.path.basename(wp)[3:-5]; fi = int(key[1])
        mp = glob.glob(os.path.join(ROOT, f"0{fi}_*/manifest.json"))[0]
        m = json.load(open(mp, encoding="utf-8"))
        shot = next((x for x in m["shots"] if f"f{fi}s{x['no']:02d}" == key), None)
        if not shot: continue
        d = json.load(open(wp, encoding="utf-8")); cur = d["6"]["inputs"]["prompt"]
        d["6"]["inputs"]["prompt"] = (cur.split("\n\n",1)[0] + "\n\n" + shot["prompt"]) if cur.startswith("<Audio 1>") else shot["prompt"]
        json.dump(d, open(wp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("✓ 第三轮完成，工作流已同步")
