#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文字诱发项降级 + 强制禁字段注入。生成每片唯一权威 manifest.json。"""
import json, os, shutil, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARC  = os.path.join(ROOT, "_archive", "2026-09-18_pre_notext")
DIRS = ["01_周星驰_三十八万八", "02_姜文_老子不娶了", "03_奉俊昊_加名之夜"]

# 精确替换：把「要求画出可读字符」改成「只可辨性质、不可辨内容」
SUBS = [
    # 片1 镜1/镜2 胸花
    ("a gaudy plastic red rose pinned to his lapel reading Groom,",
     "a gaudy plastic red rose pinned to his lapel,"),
    # 片1 镜2 纸条推近（出现两次：段落 + 时间戳段）
    ("onto the handwritten paper slip reading thirty-eight thousand eight hundred yuan parking fee.",
     "onto the handwritten paper slip, its ink strokes rendering as completely illegible abstract marks with no readable characters or digits anywhere on it."),
    # 片2 镜2 毛笔字契约
    ("the bold black brush calligraphy reading twenty thousand entry fee.",
     "the bold black brush strokes of Chinese calligraphy on red paper, rendering as completely illegible abstract ink marks with no readable characters."),
    # 片3 镜1
    ("a printed legal property co-ownership agreement document",
     "a legal property co-ownership agreement document"),
    # 片3 镜2
    ("the printed legal property co-ownership agreement,",
     "the legal property co-ownership agreement,"),
    # 片3 镜4
    ("a thick folded packet of damp yellowed handwritten debt notices tied",
     "a thick folded packet of damp yellowed handwritten debt notices, every stroke rendering as completely illegible abstract ink marks, tied"),
    # 片3 镜5（最重：微距 + 明确数字 + 手写体）
    ('the bold handwritten loan figure: "1,200,000 RMB", stamped with five vivid crimson thumbprints',
     'the bold handwritten ink strokes on the loan paper, stamped with five vivid crimson thumbprints, every character and digit rendering as completely illegible abstract marks'),
]

# 独立强制段：不写在描述里当形容词，单独成段压在最后
NO_TEXT_CLAUSE = (
    "\n\nstrict_output_constraints: Absolutely no subtitles, no captions, no burned-in text, "
    "no on-screen text of any kind, no watermark, no logo, no timestamp, no UI overlay, no lower-third. "
    "Any paper, document, lettering, signage, label or screen appearing in frame must render as "
    "completely illegible abstract marks — no readable characters, digits or words in any language whatsoever. "
    "Text-bearing props are set dressing only and must never be legible."
)

def main():
    os.makedirs(ARC, exist_ok=True)
    total_sub, total_clause = 0, 0
    for d in DIRS:
        src = os.path.join(ROOT, d, "manifest.json")
        man = json.load(open(src, encoding="utf-8"))
        # 归档老版本（含 identity_locked 中间态）
        for name in ("manifest.json", "manifest.identity_locked.json"):
            p = os.path.join(ROOT, d, name)
            if os.path.exists(p):
                shutil.copy2(p, os.path.join(ARC, "%s__%s" % (d, name)))
        for s in man["shots"]:
            p = s["prompt"]
            for old, new in SUBS:
                if old in p:
                    n = p.count(old)
                    p = p.replace(old, new)
                    total_sub += n
                    print("   %s 镜%s  替换 x%d : %s..." % (d[:2], s["no"], n, old[:52]))
            # 幂等：已有强制段就不重复加
            if "strict_output_constraints:" not in p:
                p = p.rstrip() + NO_TEXT_CLAUSE
                total_clause += 1
            s["prompt"] = p
        # 记录本轮处置
        man["notext_patch"] = {
            "applied": "2026-09-18",
            "policy": "文字道具降级为不可辨 + 每镜末尾强制禁字段",
            "clause_chars": len(NO_TEXT_CLAUSE),
        }
        json.dump(man, open(src, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        # 清掉从未被加载的中间态
        mid = os.path.join(ROOT, d, "manifest.identity_locked.json")
        if os.path.exists(mid):
            os.remove(mid); print("   删除中间态 manifest.identity_locked.json（从未被加载）")
        for f in os.listdir(os.path.join(ROOT, d)):
            if f.endswith(".orig_retime"):
                os.remove(os.path.join(ROOT, d, f)); print("   删除备份", f)
    print("\n替换 %d 处 / 注入禁字段 %d 镜 / 归档至 _archive/2026-09-18_pre_notext/" % (total_sub, total_clause))
    # 残留复查
    import re
    bad = 0
    for d in DIRS:
        man = json.load(open(os.path.join(ROOT, d, "manifest.json"), encoding="utf-8"))
        for s in man["shots"]:
            p = s["prompt"]
            for pat in [r'reading [A-Za-z"\d]', r'calligraphy reading', r'figure: "']:
                if re.search(pat, p):
                    print("   !! 残留 %s 镜%s: %s" % (d[:2], s["no"], pat)); bad += 1
    print("残留检查：", "干净" if bad == 0 else "%d 处需人工处理" % bad)

main()
