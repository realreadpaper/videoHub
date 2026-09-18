#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
三部曲 manifest 角色一致性静态审查 v2（不涉及渲染、不连远端）

核心逻辑：H3/LTX 管线**逐镜独立生成、无跨镜记忆**，同一角色在不同镜头里
"长得像不像"完全取决于 prompt 里对它的描述文本"是不是同一段字"。
所以本脚本的重点是：抽取每个 <Subject N> 的**身份定义串**，跨镜逐字比对。

检查项：
  A. 同一 Subject 号跨镜的 identity 定义串 —— 逐字 diff + 相似度
  B. identity 串长度差异（描述详略悬殊 = 换脸高危）
  C. character 元数据字段 vs prompt 实际出现（仅元数据准确性，不影响生成）
  D. 同一人名被多个 Subject 号指代（身份互换）
  E. 服装/道具/年龄等硬属性跨镜冲突
  F. dialogue_cn 字段 vs prompt 内 <d>[Chinese] 对白逐字对账（口型/字幕一致性）
  G. 画面文字诱发项 + 负向提示词覆盖
  H. Prop 编号跨镜指代同一物是否描述一致
"""
import json, re, os, difflib
from collections import defaultdict

ROOT = "/Users/hejianglong/Desktop/story/待生成_现代婚姻三部曲"
FILMS = [
    ("01", "01_周星驰_三十八万八"),
    ("02", "02_姜文_老子不娶了"),
    ("03", "03_奉俊昊_加名之夜"),
]
OUT = []
# 镜头语言里的通用词，不是角色名
STOP = {"ARRI", "ALEXA", "N/A", "MS", "CU", "MCU", "WS", "LS", "MLS", "RMB", "H3", "LTX"}


def P(s=""):
    print(s); OUT.append(s)


SUBJ_RE = re.compile(r"<Subject\s+(\d+)>\s*(?:\(S(\d+)\))?")
NAME_RE = re.compile(r"\bnamed\s+([A-Z][A-Z0-9\-']{2,})|,?\s*a\s+\d{1,2}[- ]year[- ]old[^,]{0,40}?\s([A-Z][A-Z0-9\-']{2,})\b")
AGE_RE = re.compile(r"\b(\d{1,2})[- ]year[- ]old")
PROP_RE = re.compile(r"<Prop\s+(\d+)>")


def identity_of(prompt, start):
    """从 <Subject N> 处向后截取身份定义串：到第一个句号（含缩写保护）为止。"""
    seg = prompt[start:]
    # 以句号 + 空格 + 大写 或 换行 作为段结束
    m = re.search(r"\.(?=\s+[A-Z<])|\.\n", seg)
    if not m:
        m = re.search(r"\n", seg)
    end = m.end() if m else min(len(seg), 200)
    return re.sub(r"\s+", " ", seg[:end]).strip().rstrip(". ")


def norm_key(s):
    """用于比对：去标点、小写、压空白"""
    return re.sub(r"[^a-z0-9\u4e00-\u9fff ]", "", s.lower()).strip()


for tag, dirname in FILMS:
    mpath = os.path.join(ROOT, dirname, "manifest.json")
    m = json.load(open(mpath, encoding="utf-8"))
    shots = m["shots"]
    P("=" * 104)
    P(f"【{tag}】{m['film_title']} · {m['director_style']} · seed={m.get('seed')} · "
      f"{len(shots)} 镜 × {m.get('shot_duration_sec')}s · {m.get('resolution_stage2')}")
    P("=" * 104)

    subj_ident = defaultdict(list)   # sno -> [(shot_no, identity_str, age, garment)]
    name_map = defaultdict(set)
    prop_desc = defaultdict(list)
    mism_A, mism_B, mism_D, mism_E, mism_F = [], [], [], [], []

    for sh in shots:
        no, pr = sh["no"], sh.get("prompt", "")
        # ---- 每个 Subject 的 identity
        seen = set()
        for mm in SUBJ_RE.finditer(pr):
            sno = int(mm.group(1))
            idn = identity_of(pr, mm.start())
            if (sno, idn) in seen:
                continue
            seen.add((sno, idn))
            age = AGE_RE.search(idn)
            gar = re.search(r"wearing\s+([^,]{0,70})", idn)
            subj_ident[sno].append((no, idn, age.group(1) if age else "", (gar.group(1).strip() if gar else "")))
            nm = re.search(r"\bnamed\s+([A-Z][A-Z0-9\-']{2,})", idn)
            if not nm:
                nm = re.search(r"\b([A-Z][A-Z0-9]+(?:-[A-Z0-9]+)+)\b", idn)   # 连字符风格名
            if nm and nm.group(1) not in STOP:
                name_map[nm.group(1)].add(sno)

        # ---- C. character 字段
        cf = set(int(x.group(1)) for x in SUBJ_RE.finditer(sh.get("character", "")))
        prt = set(int(x.group(1)) for x in SUBJ_RE.finditer(pr))
        if cf - prt:
            mism_A.append((no, sorted(cf), sorted(prt), sh.get("character", ""), "字段声明了角色但 prompt 里没有"))
        if prt - cf:
            mism_A.append((no, sorted(cf), sorted(prt), sh.get("character", ""), "prompt 有角色但字段没列（同框配角）"))

        # ---- F. 对白对账
        d_cn = (sh.get("dialogue_cn") or "").strip()
        d_pr = re.findall(r'<d>\[Chinese\]\s*"(.*?)"\s*</d>', pr, flags=re.S)
        d_pr = [re.sub(r"\s+", " ", x).strip() for x in d_pr]
        if d_cn and not d_pr:
            mism_F.append((no, "字段有对白，prompt 内无 <d> 标记", d_cn, "—"))
        elif d_cn and d_pr:
            a, b = norm_key(d_cn), norm_key(" ".join(d_pr))
            if a != b:
                r = difflib.SequenceMatcher(None, a, b).ratio()
                mism_F.append((no, f"对白不一致 相似度={r:.2f}", d_cn, " | ".join(d_pr)))
        elif not d_cn and d_pr:
            mism_F.append((no, "prompt 内模板对白但字段为空", "—", " | ".join(d_pr)))

        # ---- Prop 描述
        for pm in re.finditer(r"<Prop\s+(\d+)>", pr):
            pno = int(pm.group(1))
            seg = pr[pm.start(): pm.start() + 130]
            prop_desc[pno].append((no, re.sub(r"\s+", " ", seg).strip()))

    # ===== B. 同 Subject 跨镜 identity 逐字比对 =====
    P("\n── B. 同一 Subject 号跨镜「身份定义串」逐字比对（换脸风险核心）──")
    for sno in sorted(subj_ident):
        rows = subj_ident[sno]
        if len(rows) < 2:
            P(f"\n  Subject {sno} —— 仅出现在 shot{rows[0][0]}，无跨镜比对必要")
            P(f"     定义: {rows[0][1][:150]}")
            continue
        P(f"\n  Subject {sno} —— 出现在 shot {[r[0] for r in rows]}（共 {len(rows)} 次定义）")
        # 以最长的一条为基准
        base = max(rows, key=lambda r: len(r[1]))
        for no, idn, age, gar in rows:
            ratio = difflib.SequenceMatcher(None, norm_key(base[1]), norm_key(idn)).ratio()
            mark = "≡" if ratio > 0.95 else ("≈" if ratio > 0.80 else "✘")
            P(f"     [{mark}] shot{no:02d}  相似度={ratio:.2f}  长度={len(idn):3d}  年龄={age or '∅'}")
        # 打印逐字 diff（基准 vs 最不像的那条）
        worst = min(rows, key=lambda r: difflib.SequenceMatcher(None, norm_key(base[1]), norm_key(r[1])).ratio())
        r0 = difflib.SequenceMatcher(None, norm_key(base[1]), norm_key(worst[1])).ratio()
        if r0 < 0.95:
            P(f"     ── 基准(镜{base[0]:02d}) vs 最不像(镜{worst[0]:02d}) 逐字差异 ──")
            P(f"        基准: {base[1]}")
            P(f"        差异: {worst[1]}")
            sm = difflib.SequenceMatcher(None, norm_key(base[1]), norm_key(worst[1]))
            ops = []
            for op, i1, i2, j1, j2 in sm.get_opcodes():
                if op == "equal":
                    continue
                ops.append(f"    {op:8s} 基准[{norm_key(base[1])[i1:i2]!r}] -> 镜{worst[0]:02d}[{norm_key(worst[1])[j1:j2]!r}]")
            for o in ops[:14]:
                P(o)

    # ===== D. 人名冲突 =====
    P("\n── D. 同一人名 ↔ 多个 Subject 号（身份互换）──")
    bad = {n: s for n, s in name_map.items() if len(s) > 1}
    if not bad:
        P("  ✅ 每个人名只绑定一个 Subject 号")
    for n, s in sorted(bad.items()):
        P(f"  ✘ 人名 {n} 被 Subject {sorted(s)} 共用")

    # ===== A/C. 元数据 =====
    P("\n── A/C. character 元数据字段 vs prompt 实际出现（仅影响元数据可读性，不影响出片）──")
    if not mism_A:
        P("  ✅ 全部一致")
    for no, cf, prt, raw, why in mism_A:
        P(f"  · shot{no:02d}: 字段={cf} prompt={prt} — {why}  field=\"{raw}\"")

    # ===== F. 对白 =====
    P("\n── F. dialogue_cn 字段 vs prompt 内 <d> 对白逐字对账 ──")
    if not mism_F:
        P("  ✅ 全部逐字一致")
    for no, why, a, b in mism_F:
        P(f"  ✘ shot{no:02d}: {why}")
        P(f"      字段: {a}")
        P(f"      prompt: {b}")

    # ===== E. 硬属性冲突 =====
    P("\n── E. 硬属性（年龄/服装）跨镜冲突 ──")
    hard = 0
    for sno in sorted(subj_ident):
        rows = subj_ident[sno]
        ages = {r[2] for r in rows if r[2]}
        gars = {re.sub(r'^(an?|the)\s+', '', r[3].lower())[:38] for r in rows if r[3]}
        if len(ages) > 1:
            P(f"  ✘ Subject {sno} 年龄跨镜不一: {sorted(ages)}  出现在 shot{[r[0] for r in rows]}")
            hard += 1
        if len(gars) > 1:
            P(f"  · Subject {sno} 服装描述跨镜有差异（{len(gars)} 种）：")
            for g in sorted(gars):
                P(f"      - {g}")
            hard += 1
    if not hard:
        P("  ✅ 无冲突")

    # ===== G. 画面文字 =====
    P("\n── G. 画面文字诱发项 / 负向提示词 ──")
    supp = 0
    for sh in shots:
        pr = re.sub(r"<d>.*?</d>", "", sh.get("prompt", ""), flags=re.S)
        cn = [c for c in re.findall(r"[\u4e00-\u9fff]{2,}", pr) if c != "中文"]
        if cn:
            supp += 1
            P(f"  · shot{sh['no']:02d} 对白区外中文: {cn[:6]}")
    need = len(shots)
    for kw in ["no subtitles", "no captions", "no on-screen text", "no watermark", "no logo"]:
        c = sum(len(re.findall(re.escape(kw), s.get("prompt", ""))) for s in shots)
        P(f"  {'✅' if c >= need else '✘'} 负向词 \"{kw}\": {c}/{need} 镜")
    P(f"  {'✅ 对白区外无中文字面' if not supp else ''}")

    # ===== H. Prop =====
    P("\n── H. Prop 编号跨镜指代 ──")
    for pno in sorted(prop_desc):
        rows = prop_desc[pno]
        shots_of = [r[0] for r in rows]
        P(f"  <Prop {pno}> 出现于 shot{shots_of}")
        for no, seg in rows:
            P(f"      shot{no:02d}: {seg[:118]}")

# ===== 汇总 =====
P("\n" + "=" * 104)
P("汇总：以上为静态审查原始结论。逐字差异 = 换脸风险，需在开跑前统一为同一段描述文本。")
P("=" * 104)

outpath = os.path.join(ROOT, "_后期", "角色一致性审查_原始抽取_v2.txt")
open(outpath, "w", encoding="utf-8").write("\n".join(OUT))
print(f"\n>>> 已写出 {outpath}")
