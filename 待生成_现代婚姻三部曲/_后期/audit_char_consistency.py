#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
静态审查：三部曲 manifest 的角色一致性风险扫描（不涉及渲染/远端）
输出：控制台报告 + _后期/角色一致性审查_原始抽取.txt
检查项：
  A. character 字段 vs prompt 内实际出现的 Subject token
  B. 同一 <Subject N> 在不同镜头中的人名/外貌定义是否漂移
  C. 同一人名被不同 Subject 序号指代（身份互换风险）
  D. 后缀残留（ENV/HANDS/DEPARTURE 等）与命名规范
  E. Prop / 道具编号一致性
  F. 画面文字诱发项（可能生成硬字幕/水印）
"""
import json, re, sys, os
from collections import defaultdict, Counter

ROOT = "/Users/hejianglong/Desktop/story/待生成_现代婚姻三部曲"
FILMS = [
    ("01", "01_周星驰_三十八万八"),
    ("02", "02_姜文_老子不娶了"),
    ("03", "03_奉俊昊_加名之夜"),
]

SUBJ_RE = re.compile(r"<Subject\s+(\d+)>\s*(?:\(S(\d+)\))?")
NAME_HINT_RE = re.compile(r"named\s+([A-Z][A-Z\-']{2,})")
AGE_RE = re.compile(r"\b(\d{1,2})[- ]year[- ]old")
OUT = []


def P(s=""):
    print(s)
    OUT.append(s)


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


for tag, dirname in FILMS:
    mpath = os.path.join(ROOT, dirname, "manifest.json")
    if not os.path.exists(mpath):
        P(f"!! 缺失 {mpath}")
        continue
    m = json.load(open(mpath, encoding="utf-8"))
    P("=" * 100)
    P(f"【{tag}】{m['film_title']} / {m['director_style']}  seed={m.get('seed')} "
      f"stage1={m.get('resolution_stage1')} stage2={m.get('resolution_stage2')} "
      f"h3_length={m.get('h3_length')} refined={m.get('refined_frames')}")
    P("=" * 100)

    # ---- 跨镜聚合
    subj_def = defaultdict(list)      # subj_no -> [(shot_no, name, age, garb_words, full_snippet)]
    name_to_subj = defaultdict(set)   # name -> {subj_no}
    subj_to_name = defaultdict(set)
    props = defaultdict(set)          # prop_no -> {shot_no}
    char_field_mismatch = []
    suffix_notes = defaultdict(list)

    for sh in m["shots"]:
        no = sh["no"]
        pr = sh.get("prompt", "")
        cfield = sh.get("character", "")

        # A. character 字段里的 token
        cf_tokens = set()
        for mm in SUBJ_RE.finditer(cfield):
            cf_tokens.add(int(mm.group(1)))
        # prompt 内的 token
        pr_tokens = set()
        for mm in SUBJ_RE.finditer(pr):
            pr_tokens.add(int(mm.group(1)))
        if cf_tokens != pr_tokens:
            char_field_mismatch.append(
                (no, sorted(cf_tokens), sorted(pr_tokens), cfield))

        # B. 每个 subject 定义片段
        for mm in SUBJ_RE.finditer(pr):
            sn = int(mm.group(1))
            seg = pr[mm.start(): mm.start() + 260]
            nm = NAME_HINT_RE.search(seg)
            ag = AGE_RE.search(seg)
            name = nm.group(1) if nm else ""
            age = ag.group(1) if ag else ""
            # 服装关键词（取 wearing/ wearing 后 6 词）
            gar = ""
            gm = re.search(r"wearing\s+([^,\.]{0,80})", seg)
            if gm:
                gar = norm(gm.group(1))[:60]
            if not name:
                # 尝试 Chinese-like 大写名
                nm2 = re.search(r"\b([A-Z][A-Z\-]{2,}(?:-[A-Z]+)?)\b", seg)
                if nm2 and nm2.group(1) not in ("N/A",):
                    name = nm2.group(1) + "?"
            subj_def[sn].append((no, name, age, gar, norm(seg)))
            if name:
                name_to_subj[name.rstrip("?")].add(sn)
                subj_to_name[sn].add(name)

        # D. 后缀
        for mm in re.finditer(r"\(S\d+\)\s*\(([A-Z_]+)\)", pr):
            suffix_notes[mm.group(1)].append(no)
        for mm in re.finditer(r"\(S\d+\)", cfield):
            pass
        extra = re.findall(r"\((ENV|HANDS|DEPARTURE|PROP|SILENT|NO_DIALOG)\)", cfield)
        for e in extra:
            suffix_notes["charfield:" + e].append(no)

        # E. Prop
        for mm in re.finditer(r"<Prop\s+(\d+)>", pr):
            props[int(mm.group(1))].add(no)

    # ---- 输出 A
    P("\n--- A. character 字段 vs prompt 内 Subject token ---")
    if not char_field_mismatch:
        P("   ✅ 全部一致")
    for no, cf, prt, raw in char_field_mismatch:
        P(f"   ⚠️ shot{no:02d}: character字段={cf}  prompt内={prt}   raw=\"{raw}\"")

    # ---- 输出 B
    P("\n--- B. 同一 Subject 序号的定义漂移 ---")
    for sn in sorted(subj_def):
        rows = subj_def[sn]
        names = {r[1] for r in rows if r[1]}
        ages = {r[2] for r in rows if r[2]}
        garments = {r[3] for r in rows if r[3]}
        shots = sorted({r[0] for r in rows})
        flag = ""
        if len(names) > 1:
            flag += " ⚠️ 人名不一"
        if len(ages) > 1:
            flag += " ⚠️ 年龄不一"
        if len(garments) > 1:
            flag += " ⚠️ 服装描述不一"
        P(f"   Subject {sn}: 出现于 shot{shots}  人名={sorted(names) or '∅'}  年龄={sorted(ages) or '∅'}{flag}")
        for g in sorted(garments):
            P(f"       · 服装: {g}")

    # ---- 输出 C
    P("\n--- C. 同一人名 ↔ 多个 Subject 序号（身份互换风险）---")
    bad = {n: s for n, s in name_to_subj.items() if len(s) > 1}
    if not bad:
        P("   ✅ 没有人名跨序号复用")
    for n, s in sorted(bad.items()):
        P(f"   ⚠️ 人名 {n} 被用于 Subject {sorted(s)}")

    # ---- 输出 D
    P("\n--- D. 后缀与命名规范 ---")
    P(f"   出现的后缀: {dict(suffix_notes) if suffix_notes else '∅（全部为纯 (Sx)）'}")

    # ---- 输出 E
    P("\n--- E. Prop 编号分布 ---")
    for pn in sorted(props):
        P(f"   <Prop {pn}> 出现于 shot{sorted(props[pn])}")

    # ---- 输出 F：画面文字诱发 / 中文字面
    P("\n--- F. 可能诱发画面文字的写法 ---")
    hits = 0
    for sh in m["shots"]:
        pr = sh["prompt"]
        outside = pr
        # 去掉 <d>...</d> 对白后再找中文
        outside = re.sub(r"<d>.*?</d>", "", outside, flags=re.S)
        cn = re.findall(r"[\u4e00-\u9fff]{2,}", outside)
        cn = [c for c in cn if c not in ("中文",)]
        if cn:
            hits += 1
            P(f"   ⚠️ shot{sh['no']:02d} 对白区外出现中文: {cn[:8]}")
    # 负向提示词统一性
    neg = Counter()
    for sh in m["shots"]:
        for item in re.findall(r"no (?:subtitles|captions|on-screen text|watermark|logo)", sh["prompt"]):
            neg[item] += 1
    if not hits:
        P("   ✅ 对白区外无中文字面")
    P(f"   负向提示词覆盖: {dict(neg)} （应每镜 5 项 × {len(m['shots'])} 镜）")

    # ---- 逐镜一行速览
    P("\n--- 逐镜速览 ---")
    for sh in m["shots"]:
        P(f"   shot{sh['no']:02d} | {sh['framing']} | {sh['duration']}s | char=\"{sh.get('character','')}\" | file={sh.get('file')} "
          f"| 对白={'有' if sh.get('dialogue_cn') else '无'}")

outpath = os.path.join(ROOT, "_后期", "角色一致性审查_原始抽取.txt")
os.makedirs(os.path.dirname(outpath), exist_ok=True)
open(outpath, "w", encoding="utf-8").write("\n".join(OUT))
print(f"\n\n>>> 已写出 {outpath}")
