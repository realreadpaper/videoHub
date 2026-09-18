#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
角色身份串锁定补丁 —— 生成预览 diff（默认不写任何文件）

问题：H3/LTX 逐镜独立生成、无跨镜记忆。同一角色在片中先给"完整定义"
      （named + 五官 + 服装），后续镜头退化为"简写"（只有 the NN-year-old X in YYY）。
      模型每镜从零画人 → 简写镜次的角色长相完全自由发挥 → 换脸。

修法：为每部片每个角色固化一段 CANON 身份串（逐字取自片中已有的最完整定义），
      只在每镜该角色**首次出现**处注入。动作/机位/对白/时间码一律不动，
      "会随剧情变化"的服装状态与关键道具（玫瑰撕掉 / 领口解开 / 飞行风镜）保留在 CANON 之后。

用法：
  python3 fix_manifest_identity.py            # 预览 diff（dry-run）
  python3 fix_manifest_identity.py --apply    # 写出 manifest.identity_locked.json（不动原文件）
"""
import json, os, re, sys

ROOT = "/Users/hejianglong/Desktop/story/待生成_现代婚姻三部曲"
APPLY = "--apply" in sys.argv
WINDOW = 380

CANON = {
    "01_周星驰_三十八万八": {
        1: "a 30-year-old lean East Asian groom named A-XING, slightly messy parted black hair, "
           "sweating forehead, tired eyes with stubborn pride, wearing an ill-fitting rented black "
           "polyester wedding suit with a crooked bright red polyester necktie",
        2: "a 65-year-old frail stooped East Asian elderly father named OLD-LI, deep facial wrinkles, "
           "wispy grey hair, weathered trembling hands, wearing a faded navy blue zip-up windbreaker "
           "over a worn knitted sweater and dark cotton trousers",
        3: "a 55-year-old sharp-eyed domineering East Asian mother-in-law with tight permed black hair, "
           "wearing an opulent gaudy crimson and gold embroidered silk qipao dress",
        4: "a 28-year-old East Asian bride named JING-JING with heavy bridal makeup and a tiered white "
           "lace veil, wearing an ornate white gown",
    },
    "02_姜文_老子不娶了": {
        1: "a 35-year-old rugged masculine East Asian groom named DA-BIAO, sun-bronzed skin, sharp "
           "angular jawline, short buzz cut black hair, intense piercing falcon-like eyes, wearing an "
           "imposing dark olive-green heavy wool military trench coat over a bold crimson collared dress shirt",
        2: "a 62-year-old lean East Asian rural father named OLD-WU, sunburnt wrinkled face, white "
           "stubble, trembling calloused hands, wearing a traditional black quilted cotton coat and "
           "round wire-rim spectacles",
        3: "a 58-year-old shrewd rural East Asian father-in-law named MASTER-ZHANG, calculating narrowed "
           "eyes, wearing a dusty gray sheepskin coat over a dark navy Mao tunic jacket",
    },
    "03_奉俊昊_加名之夜": {
        # ⚠️ 原片 6 镜从未给新郎姓名与五官 → 全片唯一需要"补写设定"的角色（名字待爸爸拍板）
        1: "a 32-year-old slender East Asian groom named JIN-HO, calm composed features, neat short "
           "black hair, wearing rimless titanium spectacles and a tailored charcoal wool coat over a dark shirt",
        2: "a 28-year-old refined East Asian bride-to-be named EUN-HEE, delicate features, sleek low "
           "ponytail, wearing an elegant ivory turtleneck cashmere knit sweater and discreet pearl earrings",
        3: "a 56-year-old calculating East Asian mother-in-law named MADAM-PARK, sharp arched eyebrows, "
           "tight bun hairstyle, wearing a deep plum-purple wool shawl over a dark velour wrap dress",
    },
}

# ---- 判断"身份描述段"结束的词典 ----
ACT = set("""knocks raises opens steps turns bursts grips peels places delivers zips spreads nods
exhales taps sneers trembles whispers points barks slams pulls tears throws cowers cringes wraps
shields marches shouts straddles twists straps steers thrusts strides disappears holds roars glares
spits hollers yells stops pauses leans wipes closes lifts lowers walks runs drives flick flicked
uncrosses approaches bends straightens cradles revealing reading who both cinematic meanwhile
behind across reaches sits stands rests keeps begins starts continues sitting standing spine
glaring kneeling crouching leaning walking running slowly violently forcefully
vigorously silently gently firmly instantly quickly proudly calmly coldly quietly softly suddenly
carefully deliberately patiently""".split())
PART_ACT = set("""flashing gleaming glowing widening narrowing darting whipping billowing churning
dancing flickering streaming swelling brimming freezing trembling scrolling chewing smoking
holding clutching gripping staring gazing looking facing smiling""".split())
BODY = set("hands face fingers eyes profile neck arms palm knuckles gaze shoulders cheek forehead".split())
# 定语从句 / 分词短语：在段内出现即从该处截断（属于动作，不是身份）
CLAUSE_RE = re.compile(r"\b(who|which|that)\s+[a-z]|\b(his|her|their)\b[^,]{0,24}\b\w+ing\b")


STATE_PHRASE = re.compile(
    r"((?:gaudy\s+|plastic\s+|red\s+)*rose (?:torn off|pinned to his lapel(?: reading Groom)?)|"
    r"\w+\s+shirt collar unbuttoned|red tie loosened|aviator goggles(?: over his silver hair)?|"
    r"broken abacus|torn off|unbuttoned|loosened|billowing \w+ coat|"
    r"(?:clutching|holding|gripping|cradling)\s+[^,]{4,60})", re.I)


def clause_cut(raw):
    """段内定语从句 / 「his … <ing动词>」结构 → 返回截断偏移（该位置之后原文保留）。"""
    m = re.search(r"\b(who|which|that)\s+[a-z]", raw)
    if m:
        return m.start()
    for pm in re.finditer(r"\b(\w+ing)\b", raw):
        if pm.group(1).lower() in PART_ACT:
            pre = raw[max(0, pm.start() - 30):pm.start()]
            if re.search(r"\b(his|her|their)\b", pre):
                j = raw.rfind(" ", 0, pm.start())
                return j + 1 if j >= 0 else pm.start()
    return None



def is_action(seg):
    w = re.match(r"^([A-Za-z\-']+)", seg)
    if not w:
        return False
    t = w.group(1).lower()
    if t in ACT or t in PART_ACT:
        return True
    # "his/her/their <body> <ing-verb>" → 动作
    if re.match(r"^(his|her|their)\b", t) and re.search(r"\b\w+ing\b", seg):
        if not re.search(r"\b(wearing|dressed)\b", seg, re.I):
            return True
    return False


def find_span(prompt, pos, sno):
    win = prompt[pos: pos + WINDOW]
    s = pos
    # `<Subject N> (S1)'s face. <Subject N> (S1), a 30-year-old ...` → 保留 "'s face. <Subject N> (S1), " 前缀
    dot = re.match(r"^\s*'s\s+((?:\w+\s+){0,3}\w+)\s*\.\s*", win)
    if dot and any(w.lower() in BODY for w in dot.group(1).split()):
        s = pos + dot.end()
        m3 = re.match(r"^<Subject\s+\d+>\s*\(S\d+\)\s*,\s*", win[dot.end():])
        if m3:
            s += m3.end()
    limit = len(win)
    tc = re.search(r"\[\d\d:\d\d\.\d+", win)
    if tc:
        limit = min(limit, tc.start())
    for mm in re.finditer(r"<Subject\s+(\d+)>", win):
        if int(mm.group(1)) != sno:
            limit = min(limit, mm.start())
            break
    bounds = [0] + [m.end() for m in re.finditer(r"[,;]", win[:limit])] + [limit]
    for i in range(len(bounds) - 1):
        a, b = bounds[i], bounds[i + 1]
        raw = win[a:b]
        seg = raw.strip().strip(",;").strip()
        if i == 0 or not seg:
            continue
        if is_action(seg):
            return s, pos + a
        cc = clause_cut(raw)
        if cc is not None:
            return s, pos + a + cc
    return s, pos + limit


def state_tail(old):
    """保留会随剧情变化的服装状态 / 关键道具，放在 CANON 之后。"""
    keep = []
    for seg in re.split(r"[,;]", old):
        s = seg.strip().strip(",").strip()
        s = re.sub(r"^(and|with|plus)\s+", "", s, flags=re.I).strip()
        if not s:
            continue
        if re.match(r"^(wearing|dressed in|in)\b", s, re.I):
            m2 = re.search(r"\bwith\s+(.*)$", s, re.I)
            cand = m2.group(1).strip() if m2 else ""
            h2 = STATE_PHRASE.search(cand) if cand else None
            if h2 and len(cand) <= 120:
                c2 = cand[h2.start():].strip()
                if c2 not in keep:
                    keep.append(c2)
            continue
        if len(s) > 120:
            continue
        hit = STATE_PHRASE.search(s)
        if hit:
            s2 = s[hit.start():].strip()
            if s2 not in keep:
                keep.append(s2)
    return (", " + ", ".join(keep)) if keep else ""


def main():
    report, total, skipped = [], 0, []
    for film, table in CANON.items():
        m = json.load(open(os.path.join(ROOT, film, "manifest.json"), encoding="utf-8"))
        head = f"■ {film}  ({len(m['shots'])} 镜)"
        print("=" * 112); print(head); print("=" * 112)
        report += ["=" * 112, head, "=" * 112]
        new_shots = []
        for sh in m["shots"]:
            pr = sh["prompt"]
            seen, edits = set(), []
            for mm in re.finditer(r"<Subject\s+(\d+)>\s*\(S(\d+)\)", pr):
                sno = int(mm.group(1))
                if sno in seen or sno not in table:
                    continue
                # `'s <形容词> <身体部位>` 形式（身体局部镜）：此处无身份定义可注入
                nxt = pr[mm.end(): mm.end() + 80]
                msp = re.match(r"^\s*'s\s+((?:\w+\s+){0,3})", nxt)
                if msp and any(w.lower() in BODY for w in msp.group(1).split()):
                    if re.search(r"<Subject\s+%d>" % sno, nxt):
                        continue      # 本镜后面还有正式定义，继续扫描
                    seen.add(sno)
                    skipped.append((film, sh["no"], sno, "身体局部镜，全镜无身份定义"))
                    continue
                seen.add(sno)
                s, e = find_span(pr, mm.end(), sno)
                old = pr[s:e]
                if re.sub(r"\s+", " ", old).strip(" ,;") == table[sno]:
                    continue
                if not old.strip(" ,;"):
                    continue
                # 归还尾部空白 + 连接词，避免吃掉原文换行/and
                trail = ""
                for tm in re.finditer(r"(\s*(?:and|or)?\s*)$", old):
                    trail = tm.group(1)
                if trail.strip() in ("and", "or"):
                    trail = " " + trail.strip() + " "
                elif trail.strip() == "":
                    trail = trail if "\n" in trail else ""
                else:
                    trail = ""
                pre = pr[s:mm.end()]
                lead = "" if pr[:s].rstrip().endswith(",") else ", "
                new = pre + lead + table[sno] + state_tail(old) + trail
                edits.append((s, e, new, old, sno))
            if edits:
                buf, p = [], 0
                for s, e, new, old, sno in edits:
                    buf.append(pr[p:s]); buf.append(new); p = e
                    total += 1
                    ln = [f"  shot{sh['no']:02d} · Subject {sno}",
                          f"    −{re.sub(chr(10), ' ⏎ ', old)[:280]}",
                          f"    +{re.sub(chr(10), ' ⏎ ', new)[:280]}"]
                    print("\n".join(ln)); report += ln + [""]
                buf.append(pr[p:])
                sh2 = dict(sh); sh2["prompt"] = "".join(buf)
                new_shots.append(sh2)
            else:
                new_shots.append(sh)
        if APPLY:
            m2 = dict(m); m2["shots"] = new_shots
            m2["_identity_lock"] = ("canonical identity block injected per character; "
                                    "generated by _后期/fix_manifest_identity.py")
            op = os.path.join(ROOT, film, "manifest.identity_locked.json")
            json.dump(m2, open(op, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            print(f"  → 已写出 {op}"); report.append(f"  → 已写出 {op}")

    report.append("\n【跳过（无需注入）】")
    for f, n, sno, why in skipped:
        report.append(f"  {f} shot{n:02d} Subject {sno} — {why}")
    tail = f"\n合计改动 {total} 处身份描述段。" + ("" if APPLY else "  【预览模式 · 未写任何文件】")
    print(tail); report.append(tail)
    open(os.path.join(ROOT, "_后期", "角色一致性_补丁diff.txt"), "w", encoding="utf-8").write("\n".join(report))
    print(">>> _后期/角色一致性_补丁diff.txt")


if __name__ == "__main__":
    main()
