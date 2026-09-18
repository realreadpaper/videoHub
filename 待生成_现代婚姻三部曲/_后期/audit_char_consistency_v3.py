#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
角色一致性静态审查 v3 —— 只看「静态身份锚点」，剥离动作/机位/对白

原理：H3+LTX 逐镜独立生成、无跨镜记忆。同一角色跨镜"像不像"只取决于
静态身份锚点是否逐字复述：
    ① 姓名 named X   ② 年龄 NN-year-old   ③ 族裔
    ④ 角色词(groom/bride/mother-in-law...)  ⑤ 面部锚点(hair/eyes/jawline/features)
    ⑥ 服装 wearing/in ...   ⑦ 配件(spectacles/earrings/ring/veil...)
动作、机位、时间码、对白不参与判定（各镜本来就不同）。

输出：每个角色 × 每个镜头的锚点覆盖矩阵 + 缺口清单
"""
import json, re, os
from collections import defaultdict

ROOT = "/Users/hejianglong/Desktop/story/待生成_现代婚姻三部曲"
FILMS = [("01", "01_周星驰_三十八万八"), ("02", "02_姜文_老子不娶了"), ("03", "03_奉俊昊_加名之夜")]
OUT = []

FACE_KW = ["hair", "eyes", "jawline", "features", "complexion", "skin", "stubble",
           "beard", "brow", "cheekbone", "face", "forehead"]
ACC_KW = ["spectacle", "glasses", "earring", "ring", "veil", "makeup", "lipstick",
          "necklace", "goggle", "tie", "watch", "scarf", "hat", "cap", "shawl"]
ROLE_KW = """groom bride mother-in-law father-in-law father mother son daughter
bridesmaid waiter landlord clerk stranger boss uncle auntie
motherinlaw fatherinlaw bridetobe""".split()


def P(s=""):
    print(s); OUT.append(s)


def anchors(prompt, pos, span=300):
    """从 <Subject N> 位置向后 span 字符内，抽静态锚点"""
    seg = prompt[pos: pos + span]
    # 截到第一个时间码 / 段末（避免跨到下一镜描述或后期形容词）
    cut = re.search(r"\[\d\d:\d\d\.\d+\s*[–-]", seg)
    if cut:
        seg = seg[:cut.start()]
    seg = re.sub(r"\s+", " ", seg)
    name = re.search(r"\bnamed\s+([A-Z][A-Z0-9\-']{2,})", seg)
    age = re.search(r"\b(\d{1,2})[- ]year[- ]old", seg)
    ethnic = "East Asian" if "East Asian" in seg else ""
    role = ""
    for kw in ROLE_KW:
        if re.search(r"\b" + re.escape(kw) + r"\b", seg, re.I):
            role = kw; break
    face = sorted({k for k in FACE_KW if re.search(r"\b" + k + r"\b", seg, re.I)})
    acc = sorted({k for k in ACC_KW if re.search(r"\b" + k + r"\b", seg, re.I)})
    gar = ""
    gm = re.search(r"(?:wearing|dressed in|in)\s+(?:an?\s+|the\s+)?([^,\.]{4,90})", seg)
    if gm:
        gar = re.sub(r"\s+", " ", gm.group(1)).strip()
    # 定义形态：FULL=带 named；SHORT=只给 the NN-year-old ... in ...
    form = "FULL" if name else ("MID" if age else "SHORT")
    return dict(name=name.group(1) if name else "", age=age.group(1) if age else "",
                ethnic=ethnic, role=role, face=face, acc=acc, gar=gar, form=form, seg=seg)


for tag, dirname in FILMS:
    m = json.load(open(os.path.join(ROOT, dirname, "manifest.json"), encoding="utf-8"))
    shots = m["shots"]
    P("=" * 112)
    P(f"【{tag}】{m['film_title']} · {m['director_style']} · {len(shots)} 镜 × {m.get('shot_duration_sec')}s")
    P("=" * 112)

    mat = defaultdict(dict)   # sno -> shot_no -> anchors
    order = defaultdict(list)
    for sh in shots:
        pr = sh["prompt"]
        got = set()
        for mm in re.finditer(r"<Subject\s+(\d+)>", pr):
            sno = int(mm.group(1))
            if sno in got:
                continue
            got.add(sno)
            a = anchors(pr, mm.start())
            mat[sno][sh["no"]] = a
            order[sno].append(sh["no"])

    # ===== 锚点覆盖矩阵 =====
    for sno in sorted(mat):
        shotlist = sorted(mat[sno])
        P(f"\n▌Subject {sno}  出现镜次: {shotlist}")
        base = None
        # 基准 = form 最全、字段最多的那一镜
        cand = [(s, mat[sno][s]) for s in shotlist]
        cand.sort(key=lambda x: (x[1]["form"] == "FULL", len(x[1]["face"]) + len(x[1]["acc"]), len(x[1]["seg"])), reverse=True)
        base_shot, base = cand[0]
        P(f"  基准镜: shot{base_shot:02d}  [{base['form']}]  name={base['name'] or '∅'} age={base['age'] or '∅'} "
          f"role={base['role'] or '∅'}")
        P(f"  基准身份串: {base['seg'][:230]}")
        P(f"  {'镜':>4} {'形态':>5} {'姓名':>12} {'年龄':>4}  {'缺面部锚点':<28} {'缺配件':<22} 服装写法")
        for s in shotlist:
            a = mat[sno][s]
            miss_face = [k for k in base["face"] if k not in a["face"]]
            miss_acc = [k for k in base["acc"] if k not in a["acc"]]
            warn = ""
            if a["form"] != "FULL" and base["form"] == "FULL":
                warn = " ⚠️"
            if a["name"] and base["name"] and a["name"] != base["name"]:
                warn += " ⚠️姓名"
            if a["age"] and base["age"] and a["age"] != base["age"] and int(a["age"]) < 100:
                warn += " ⚠️年龄"
            P(f"  {s:>4} {a['form']:>5} {a['name'] or '∅':>12} {a['age'] or '∅':>4}  "
              f"{(','.join(miss_face) or '齐全'):<28} {(','.join(miss_acc) or '齐全'):<22} "
              f"{a['gar'][:46] or '∅'}{warn}")

        # ===== 定级 =====
        fulls = sum(1 for s in shotlist if mat[sno][s]["form"] == "FULL")
        shorts = sum(1 for s in shotlist if mat[sno][s]["form"] == "SHORT")
        noname = sum(1 for s in shotlist if not mat[sno][s]["name"])
        P(f"  → 形态分布: FULL={fulls} / MID={sum(1 for s in shotlist if mat[sno][s]['form']=='MID')} / SHORT={shorts}"
          f"   无姓名镜次={noname}/{len(shotlist)}")
        if fulls < len(shotlist) and fulls > 0:
            P(f"  → 🔴 高危：同一角色存在 {len(shotlist)-fulls} 个镜头使用简写定义（缺人脸锚点）→ 换脸")
        elif fulls == 0:
            P(f"  → 🟠 中危：全片无一次带 named 的完整定义，角色锚点全靠年龄+服装")
        else:
            P(f"  → ✅ 全部镜头均使用完整定义")

    # ===== 跨片角色token 冲突检查 =====
    P("\n── 片内 Subject 号 ↔ 固定角色 映射核对 ──")
    for sno in sorted(mat):
        names = {mat[sno][s]["name"] for s in mat[sno] if mat[sno][s]["name"]}
        ages = {mat[sno][s]["age"] for s in mat[sno] if mat[sno][s]["age"]}
        roles = {mat[sno][s]["role"] for s in mat[sno] if mat[sno][s]["role"]}
        f = ""
        if len(names) > 1: f += " ✘人名不一"
        if len(ages) > 1: f += " ✘年龄不一"
        if len(roles) > 1: f += " ✘角色词不一"
        P(f"  Subject {sno}: 人名={sorted(names) or ['∅']} 年龄={sorted(ages) or ['∅']} 角色={sorted(roles) or ['∅']}{f}")

    # ===== 未被任何镜头定义的角色 =====
    P("\n── character 元数据 vs prompt 实际 ──")
    for sh in shots:
        cf = sorted({int(x.group(1)) for x in re.finditer(r"<Subject\s+(\d+)>", sh.get("character", ""))})
        pr = sorted({int(x.group(1)) for x in re.finditer(r"<Subject\s+(\d+)>", sh["prompt"])})
        if cf != pr:
            P(f"  · shot{sh['no']:02d}: 字段={cf} prompt={pr}  field=\"{sh.get('character','')}\"")

outp = os.path.join(ROOT, "_后期", "角色一致性审查_锚点矩阵.txt")
open(outp, "w", encoding="utf-8").write("\n".join(OUT))
print(f"\n>>> {outp}")
