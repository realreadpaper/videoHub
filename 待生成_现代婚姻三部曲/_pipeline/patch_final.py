#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""成品剧本落地：把审查结论（P0 5 处 + P1 6 处）写进 manifest。
台词级改动会标记 need_tts，供后续重生成干声。"""
import json, os, shutil, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARC  = os.path.join(ROOT, "_archive", "2026-09-18_pre_final")
DIRS = {"01_周星驰_三十八万八": "f1", "02_姜文_老子不娶了": "f2", "03_奉俊昊_加名之夜": "f3"}

# ── 台词级（dialogue_cn 与 prompt 里的 <d> 标签同步改）──
DLG = {
 ("f1", 3): ("不拿出这三十八万八，我家静静绝不下轿！",
             "不拿出这三十八万八，我家静静绝不出这个门！",
             "P1 用语与场景不符：新娘仍在娘家闺房，未上轿"),
 ("f1", 6): ("走！爸，我带你去看真正的海！",
             "走！爸，我带你去看真正的天地！",
             "P0 承诺与兑现不符：结局是高原雪山，且主题为川藏线，到不了海"),
 ("f2", 2): ("除了那三十万，进屋前再撂二十万下车礼，给小勇凑个全款。",
             "除了那三十万彩礼，进屋前再撂二十万下车礼——我得给小勇买房凑全款。",
             "P0 前置交代缺失：三十万性质不明 + 小勇无身份，而这是加价唯一动机"),
 ("f2", 6): ("爹，把算盘收好，咱们爷俩走大路！",
             "爹，把算盘拿好，咱们爷俩走大路！",
             "P1 用词：算盘镜3 已崩裂，「收好」用于完好之物"),
 ("f3", 8): ("雨……终于停不下来了。",
             "雨……终于淋不到我了。",
             "P0 病句：终于(好事达成)与停不下来(坏事持续)矛盾，且与 liberation 情绪、雨中画面双冲突"),
}

# ── 描述级（只改 prompt，不动画面成本）──
PRM = [
 # 片3 镜1：水桶物理 —— 把「满」前置，镜7 的倾倒才成立
 ("f3", 1, "into a faded red plastic bucket on the linoleum floor",
            "into a faded red plastic bucket already brimming to the rim on the linoleum floor",
            "P0 物理时间不成立：滴水数小时才能接满，剧情内只有几分钟"),
 # 片3 镜5：五个手印 vs 两个人 —— 去掉具体数字
 ("f3", 5, "stamped with five vivid crimson thumbprints, every character and digit rendering as completely illegible abstract marks matching the bride and mother's names.",
            "stamped with row upon row of crimson thumbprints, every character and digit rendering as completely illegible abstract marks, bearing the bride's and her mother's names.",
            "P1 数量不自洽：5 个手印对应 2 个人的名字，关系说不清"),
 # 片3 镜2/镜3：命名中韩混用 —— 统一为中文语境
 ("f3", 2, "named MADAM-PARK", "named MADAM-HE",
            "P1 命名体系：韩姓「朴」与人民币/房产加名的中文语境撕裂"),
 ("f3", 3, "named EUN-HEE", "named EN-XI",
            "P1 命名体系：韩式罗马音，与中文语境不一致"),
 # 片1 镜4：道具链 —— 从绒布袋取，而不是内胸口袋（绒布袋是镜1 起的情感道具）
 ("f1", 4, "carefully unzips an inner chest pocket and unfolds a faded tea-stained cotton handkerchief",
            "carefully unties the small red velvet pouch at his chest and unfolds a faded tea-stained cotton handkerchief",
            "P1 道具连续性：镜1 起紧抱的红绒布袋在镜4 凭空消失"),
 # 片1 镜4：补进屋过渡（镜2 在门外，镜4 已在屋内）
 ("f1", 4, "Top-down macro close-up with slow steady push-in.",
            "Having been reluctantly let into the bridal chamber. Top-down macro close-up with slow steady push-in.",
            "P1 过程缺失：镜2 门外被塞纸条，镜4 已在屋内掏存折，中间无交代"),
 # 片3 镜6：补公文包铺垫（镜7 要拉上它）
 ("f3", 6, "[00:10.042 – 00:15.083] Across the table",
            "[00:10.042 – 00:15.083] Beside his chair rests a black leather briefcase. Across the table",
            "P1 道具未铺垫：镜7 拉上的公文包此前 6 镜从未出现"),
]

def main():
    os.makedirs(ARC, exist_ok=True)
    need_tts, n_dlg, n_prm = [], 0, 0
    for d, fk in DIRS.items():
        p = os.path.join(ROOT, d, "manifest.json")
        man = json.load(open(p, encoding="utf-8"))
        shutil.copy2(p, os.path.join(ARC, "%s__manifest.json" % d))
        for s in man["shots"]:
            key = (fk, s["no"]); pr = s["prompt"]
            if key in DLG:
                old, new, why = DLG[key]
                if s.get("dialogue_cn", "").strip() == old:
                    s["dialogue_cn"] = new
                if old in pr:
                    pr = pr.replace(old, new); n_dlg += 1
                    need_tts.append("%ss%02d" % (fk, s["no"]))
                    print("  [台词] %ss%02d  %s" % (fk, s["no"], why[:40]))
                else:
                    print("  !! 台词未命中 %ss%02d" % key)
            for kf, kno, old, new, why in PRM:
                if (kf, kno) == key and old in pr:
                    pr = pr.replace(old, new); n_prm += 1
                    print("  [描述] %ss%02d  %s" % (kf, kno, why[:40]))
                elif (kf, kno) == key:
                    print("  !! 描述未命中 %ss%02d: %s" % (kf, kno, old[:50]))
            s["prompt"] = pr
        man["final_patch"] = {"applied": "2026-09-18", "dialogue": n_dlg, "prompt": n_prm,
                              "need_tts": need_tts}
        json.dump(man, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n台词 %d 处 / 描述 %d 处；需重出干声: %s" % (n_dlg, n_prm, ",".join(need_tts)))
    # 复查
    bad = 0
    for d, fk in DIRS.items():
        man = json.load(open(os.path.join(ROOT, d, "manifest.json"), encoding="utf-8"))
        for s in man["shots"]:
            pr = s["prompt"]
            for old, _, _ in DLG.values():
                if old in pr: print("  !! 残留旧台词 %ss%02d" % (fk, s["no"])); bad += 1
            for _, _, old, new, _ in PRM:
                if old in pr and old not in new:  # new 含 old 的属误报
                    print("  !! 残留旧描述 %ss%02d" % (fk, s["no"])); bad += 1
            if "strict_output_constraints:" not in pr:
                print("  !! 禁字段丢失 %ss%02d" % (fk, s["no"])); bad += 1
            if len(re.findall(r"\[\d{2}:\d{2}\.\d{3}\s*[–-]\s*\d{2}:\d{2}\.\d{3}\]", pr)) != 3:
                print("  !! 时间戳异常 %ss%02d" % (fk, s["no"])); bad += 1
    print("复查：", "全部通过" if bad == 0 else "%d 处异常" % bad)

main()
