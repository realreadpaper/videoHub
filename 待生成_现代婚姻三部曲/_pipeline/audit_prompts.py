#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
扫描 24 镜 prompt，审查表情僵硬风险与 <d> 标签。
"""
import json, glob, os, re

ROOT = "/Users/hejianglong/Desktop/videoHub/待生成_现代婚姻三部曲"

# 过度静态的词
STATIC = ["spine straight", "unnervingly calm", "completely motionless",
          "frozen in place", "perfectly still", "utterly calm", "without expression",
          "blank expression", "deadly pale silence", "not moving", "sits still"]

# 好的微表情提示
GOOD = ["twitch", "tremble", "blink", "swallow", "sigh", "exhale", "shallow breath",
        "jaw tighten", "mouth slightly open", "lip", "muscle", "flicker", "grimace",
        "eyes narrow", "gaze dart", "look away", "flinch", "clench", "shudder"]

# 表情 transition / 情绪弧
ARCS = ["then", "before", "after", "flickering", "vanishing", "settling", "shattering",
        "draining", "cracking", "fading", "growing", "hardening", "softening"]

def analyze(prompt):
    issues = []
    for w in STATIC:
        if w in prompt.lower():
            issues.append(f"静态词：'{w}'")
    has_d = "<d>" in prompt
    micro = sum(1 for w in GOOD if w in prompt.lower())
    arc = sum(1 for w in ARCS if w in prompt.lower())
    return dict(has_d=has_d, issues=issues, micro=micro, arc=arc,
                static=len(issues))

rows = []
for mp in sorted(glob.glob(os.path.join(ROOT, "0*_*/manifest.json"))):
    m = json.load(open(mp, encoding="utf-8"))
    fi = int(os.path.basename(os.path.dirname(mp))[:2])
    for s in m["shots"]:
        k = f"f{fi}s{s['no']:02d}"
        a = analyze(s["prompt"])
        rows.append(dict(k=k, film=m["film_title"], shot=s["file"],
                         dialogue=s.get("dialogue_cn",""),
                         framing=s.get("framing",""), **a))

# 输出排序：风险高排前面
rows.sort(key=lambda x: (-x["static"], -x["has_d"], -x["micro"]))

print("="*100)
print("24 镜 prompt 表情审查报告")
print("="*100)
print(f"{'镜':<8}{'片':<10}{'景别':<10}{'<d>':<6}{'静态词':<8}{'微表情':<8}{'情绪弧':<8}{'问题摘要'}")
for r in rows:
    d = "是" if r["has_d"] else "否"
    summ = " ".join(r["issues"][:2]) if r["issues"] else ("微表情少" if r["micro"]<3 else "OK")
    if r["has_d"]:
        summ = "<d>标签字幕风险; " + summ
    print(f"{r['k']:<8}{r['film']:<10}{r['framing']:<10}{d:<6}{r['static']:<8}{r['micro']:<8}{r['arc']:<8}{summ}")

# 输出到 markdown 文件
out = os.path.join(ROOT, "_deliver", "prompt_表情审查_20260918.md")
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    f.write("# 24 镜 Prompt 表情审查报告\n\n")
    f.write("| 镜 | 片 | 景别 | `<d>`标签 | 静态词 | 微表情提示 | 情绪弧 | 问题摘要 |\n")
    f.write("|---|---|---|---|---|---|---|---|\n")
    for r in rows:
        d = "是" if r["has_d"] else "否"
        summ = " ".join(r["issues"][:2]) if r["issues"] else ("微表情提示偏少" if r["micro"]<3 else "OK")
        if r["has_d"]:
            summ = "`<d>`标签字幕风险；" + summ
        f.write(f"| {r['k']} | {r['film']} | {r['framing']} | {d} | {r['static']} | {r['micro']} | {r['arc']} | {summ} |\n")
    f.write("\n## 审查结论\n\n")
    f.write("1. **`<d>` 标签**：21/24 镜存在。该标签是 MiniMax H3 的 dialogue 指令，模型在驱动口型的同时，"
            "极易把标签内的中文字句渲染成屏幕字幕。建议全部替换为自然语言描述（如 `delivers the verdict in Chinese`）。\n\n")
    f.write("2. **表情僵硬根因**：\n")
    f.write("   - 大量 `spine straight / unnervingly calm / frozen in place / completely motionless` 等完全静态词；\n")
    f.write("   - 缺少 `jaw tighten / blink / swallow / lip tremble / muscle twitch / eyes narrow` 等微表情；\n")
    f.write("   - 缺少表情 transition（`flickering then vanishing / settles into / cracks`）。\n\n")
    f.write("3. **优化方向**：\n")
    f.write("   - 用'下颌收紧、嘴角微抽、缓慢吸气'替换'冷静/僵硬/不动'；\n")
    f.write("   - 给关键情绪转折加 transition；\n")
    f.write("   - 去掉 `<d>` 台词标签，依赖干声音频驱动口型。\n")
print(f"\n报告已写入：{out}")
