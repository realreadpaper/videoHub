#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复 f3s06 的两个问题：
1. 去掉 <d> 标签，避免 H3 把台词渲染成画面字幕
2. 增强表情描述，避免人物僵硬

用法： python3 fix_f3s06_prompt.py
"""
import json, os

ROOT = "/Users/hejianglong/Desktop/videoHub/待生成_现代婚姻三部曲"
WF = os.path.join(ROOT, "_pipeline/wf_one/wf_f3s06.json")
MANIFEST = os.path.join(ROOT, "03_奉俊昊_加名之夜/manifest.json")

d = json.load(open(WF, encoding="utf-8"))
prompt = d["6"]["inputs"]["prompt"]

# ---- 替换第一段 ----
old1 = (
    "[00:00.000 – 00:05.042] Medium symmetrical shot across the formica table. "
    "In the foreground center sits <Subject 1> (S1), the 32-year-old slender groom in charcoal wool coat, "
    "spine straight and unnervingly calm, his rimless spectacles gleaming under the bare bulb."
)
new1 = (
    "[00:00.000 – 00:05.042] Medium symmetrical shot across the formica table. "
    "In the foreground center sits <Subject 1> (S1), the 32-year-old slender groom in charcoal wool coat. "
    "He sits very still, shoulders relaxed, but his jaw is subtly tightened and a faint muscle ticks along his cheek. "
    "His rimless spectacles catch the bare bulb light as he slowly inhales, eyes cold and steady."
)

# ---- 替换第二段：去掉 <d> 标签 ----
old2 = (
    '[00:05.042 – 00:10.042] <Subject 1> (S1) delicately flattens <Prop 2>, the private debt paper, with two fingers, '
    'places it squarely on top of the co-ownership agreement, and delivers an icy, detached verdict: '
    '<d>[Chinese] "原来你们要的定心丸，是一百二十万的替死鬼。"</d>'
)
new2 = (
    "[00:05.042 – 00:10.042] <Subject 1> (S1) delicately flattens <Prop 2>, the private debt paper, with two fingers, "
    "places it squarely on top of the co-ownership agreement, and delivers an icy verdict in Chinese. "
    "His lips move with measured precision, a brief, cold half-smile flickering at one corner of his mouth before vanishing as he studies their faces."
)

# ---- 替换第三段：让母亲和女儿有具体微表情，不要 frozen in place ----
old3 = (
    "[00:10.042 – 00:15.083] Beside his chair rests a black leather briefcase. "
    "Across the table, on the left sits <Subject 3> (S3), the 56-year-old mother in plum shawl, "
    "and on the right sits <Subject 2> (S2), the 28-year-old bride in ivory knit sweater, "
    "both freezing in place as all color drains from their faces into deathly pale silence, "
    "their social masks completely shattered, cinematic 16:9 widescreen, ARRI Alexa look, shallow depth of field, "
    "fine film grain, naturalistic lighting, photorealistic, no subtitles, no captions, no on-screen text, no watermark, no logo."
)
new3 = (
    "[00:10.042 – 00:15.083] Beside his chair rests a black leather briefcase. "
    "Across the table, <Subject 3> (S3) on the left blinks rapidly, her mouth slightly open, color draining from her cheeks, "
    "while <Subject 2> (S2) on the right looks away with a visible swallow and a trembling lower lip, both women's social masks cracking. "
    "<Subject 1> (S1) holds his breath for a beat, then exhales slowly, his expression settling into merciless clarity. "
    "cinematic 16:9 widescreen, ARRI Alexa look, shallow depth of field, fine film grain, naturalistic lighting, photorealistic, "
    "no subtitles, no captions, no on-screen text, no watermark, no logo."
)

assert old1 in prompt, "old1 not found"
assert old2 in prompt, "old2 not found"
assert old3 in prompt, "old3 not found"

prompt = prompt.replace(old1, new1).replace(old2, new2).replace(old3, new3)

if "<d>" in prompt:
    print("警告：prompt 里仍有 <d> 标签")
    raise SystemExit(1)

# 同步更新 manifest 里的 prompt（保持源一致）
m = json.load(open(MANIFEST, encoding="utf-8"))
shot = m["shots"][5]  # shot06 index 5
assert shot["file"] == "shot06_chilling_confrontation_table"
shot["prompt"] = prompt

# 写回
d["6"]["inputs"]["prompt"] = prompt
json.dump(d, open(WF, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(m, open(MANIFEST, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

print("✓ f3s06 prompt 已更新")
print("  变化：")
print("    1. 去掉 <d> 标签（原台词不再写入画面）")
print("    2. 增加下颌收紧/脸颊肌肉跳动/缓慢吸气呼气")
print("    3. 母亲/新娘增加眨眼/张口/吞咽/嘴唇颤抖等微表情")
print("    4. 新郎增加冷笑一闪而过、表情 settle 到冷酷清明")
print()
print("修改文件：")
print("  ", WF)
print("  ", MANIFEST)
