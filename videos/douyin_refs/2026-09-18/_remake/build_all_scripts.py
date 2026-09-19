#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""三部片「逐镜时间轴剧本」+ 时间轴自动审核。

每镜 length = 原片真实镜长**向上吸附**到 H3 栅格（17n+5 帧 @24fps），
不再一律 14.75s —— 这是"百分百复刻"且不拖沓的根。
"""
import json, os, re

BASE = "/Users/jianglong/Desktop/videoHub/videos/douyin_refs/2026-09-18"
OUT = f"{BASE}/_remake"

# ---- 栅格：H3 length ∈ 17n+5；★ 向上吸附（≥ 原片镜长，尾音不被切）----
GRID = [(n, 17 * n + 5, (17 * n + 5) / 24) for n in range(1, 25)]
def snap(dur):
    up = [g for g in GRID if g[2] >= dur - 1e-6]
    return up[0] if up else GRID[-1]
def cost(frames):   # 全流程秒（107/226/354 帧三点实测拟合）
    return max(0.0, 0.812 * frames + 0.002129 * frames * frames - 1.3)

# ---- 报恩逐镜说话人（精确标注）----
SPEAKER_DY1 = {
    1:"父亲",2:"父亲",3:"父亲",4:"小周(少年)",5:"父亲",6:"小周(少年)",7:"小周(少年)",8:"小周(少年)",9:"小周(少年)",
    10:"老赵",11:"老赵",12:"老赵→小周",13:"老赵",14:"老赵",15:"老赵",16:"老赵",17:"老赵",18:"老赵",19:"老赵→小周",
    20:"老赵",21:"小周→老赵",22:"老赵",23:"客人",24:"老赵",25:"老赵",26:"老赵",27:"老赵",28:"老赵",29:"老赵",
    30:"老赵",31:"老赵",32:"老赵",33:"客人",34:"客人→小周",35:"小周→老赵",36:"老赵",37:"老赵",38:"老赵",
    39:"店员",40:"店员",41:"店员",42:"店员",43:"厨师",44:"店员→周总",45:"周总",46:"助理",47:"助理→周总",48:"周总",
    49:"助理→周总",50:"周总",51:"周总→老赵",52:"老赵→周总",53:"周总→老赵",54:"老赵",55:"周总",56:"周总",57:"周总",
    58:"周总",59:"周总",60:"周总",61:"周总",62:"周总",63:"周总→老赵",64:"老赵→周总",65:"周总",66:"周总",67:"周总",
    68:"周总",69:"周总(转口播)",70:"口播",71:"口播",72:"口播",73:"口播",74:"口播",75:"口播",76:"口播",77:"口播",
    78:"口播",79:"口播",80:"老赵",81:"口播",82:"口播",83:"口播",84:"口播",85:"口播",86:"口播",
    87:"周总",88:"周总",89:"周总",90:"周总",91:"周总",92:"老赵",93:"周总",94:"周总",95:"老赵→周总",96:"老赵",
    97:"周总→老赵",98:"老赵",99:"老赵(收尾)",
}

# ---- 三部定义：段落（起秒, 止秒, 标签, 功能, 场景, 默认说话人）----
FILMS = [
 dict(key="01_报恩", vid="7661613126736204025", dur=295.7, spk=SPEAKER_DY1, segs=[
   (0,14,"① 弃","父亲当街驱逐，男孩一无所有","夜色旧巷/家门口，冷调","父亲→小周"),
   (14,47,"② 收","老赵带他进屋、擦药、端出红烧肉","餐馆后门→店内，暖光","老赵→小周"),
   (47,82,"③ 传","留下帮工，教刀工、教这包酱","厨房灶台，烟火气","老赵"),
   (82,101,"④ 出去","男孩要出去闯，老赵塞酱送别","店门口，黄昏","老赵→小周"),
   (101,124,"⑤ 成","十年后成周总，店里十年只用同一款酱","明亮餐馆，客人满座","店员/周总"),
   (124,178,"⑥ 回","回老店看叔，用同一包酱做给叔吃","老店灶台，旧而温暖","周总→老赵"),
   (178,259,"⑦ 产品段","自然切口播：电饭锅做排骨 + 9.9 五包","厨房演示，产品特写","口播"),
   (259,999,"⑧ 接","当年您接我进来，现在换我接您走","老店门口，夕阳","周总→老赵"),
 ]),
 dict(key="02_继母", vid="7686341460064787045", dur=287.7, spk={}, segs=[
   (0,45,"① 立恨","继母使唤继女拖地洗衣、拒绝生日请求、抢走50块","清晨客厅/院子，冷白光","莫姨→小优"),
   (45,72,"② 孤立","女孩打给亲妈被挂断，双向被弃","房间/阳台，暖弱光","小优→亲妈"),
   (72,107,"③ 反转启动","莫姨独自去找曹阿姨求教，想亲手给她做一份","曹阿姨家厨房，暖光","莫姨→曹阿姨"),
   (107,220,"④ 学艺(产品段)","曹阿姨教红烧肉 → 产品用法 → 9.9 七包","厨房灶台，产品特写","曹阿姨→莫姨"),
   (220,260,"⑤ 揭底","老公发现订蛋糕+学做菜；小优是你女儿也是我闺女","客厅/门口，暖光","爸爸→莫姨"),
   (260,999,"⑥ 情感落点","生日桌前，阿姨怎么还叫阿姨 → 谢谢妈妈","生日餐桌，烛光","小优→莫姨"),
 ]),
 dict(key="03_挑食", vid="7664454812574337402", dur=297.0, spk={}, segs=[
   (0,25,"① 冲突建立","女儿不吃饭、三个月换9个厨师、顾总发火","豪宅餐厅，冷调","顾总→管事"),
   (25,53,"② 意外英雄登场","女儿偷跑出门，被陌生小伙一块饼救了","街边/路边摊，自然光","女儿→小伙"),
   (53,95,"③ 被质疑","到顾宅被管事主厨围攻：来路不明、路边摊","顾宅厨房，硬光","管事/主厨→小伙"),
   (95,121,"④ 权威反转","顾总查出小伙迟到是因扶起晕倒的女儿","监控/走廊，冷调","顾总"),
   (121,139,"⑤ 赌局","她吃你留，她不吃你也走","餐厅，对峙","顾总→小伙"),
   (139,177,"⑥ 打脸","只倒一包酱，老厨师嘲：学15年颠勺不如一包酱","厨房灶台","老厨师→小伙"),
   (177,217,"⑦ 验证","女儿吃光，半年第一次自己动筷子","餐厅，暖光","女儿→顾总"),
   (217,285,"⑧ 产品段","奶奶背书 + 电饭煲演示 + 9.9 七包","厨房演示，产品特写","奶奶"),
   (285,999,"⑨ 情感收尾","拉钩，你负责吃饭我负责做饭","餐厅门口，夕阳","女儿→小伙"),
 ]),
]

def load(vid):
    b = f"{BASE}/{vid}"
    shots = json.load(open(f"{b}/shots.json"))
    shots = shots if isinstance(shots, list) else shots.get("shots", shots)
    framing = json.load(open(f"{b}/framing.json"))
    lines = {}
    for ln in open(f"{b}/shots.md", encoding="utf-8"):
        m = re.match(r"\|\s*(\d+)\s*\|\s*([\d:.]+)\s*\|\s*([\d.]+)s\s*\|\s*(.*?)\s*\|", ln)
        if m:
            lines[int(m.group(1))] = m.group(4).strip()
    return shots, {float(k): v for k, v in framing.items()}, lines

def seg_of(t, segs):
    for lo, hi, tag, func, scene, spk in segs:
        if lo <= t < hi:
            return tag, func, scene, spk
    return segs[-1][2], segs[-1][3], segs[-1][4], segs[-1][5]

def build(film):
    shots, fkeys, lines = load(film["vid"])
    rows = []
    for s in shots:
        i = s["index"]; st = s["start"]; du = s["duration"]
        n, frames, sec = snap(du)
        fk = min(fkeys, key=lambda k: abs(k - s["mid"])) if fkeys else None
        fr = fkeys.get(fk, {})
        tag, func, scene, dspk = seg_of(st, film["segs"])
        rows.append(dict(index=i, start=st, end=st+du, dur=du, frames=frames,
                         sec=round(sec,3), n=n, framing=fr.get("framing",""),
                         kf=fr.get("file",""), speaker=film["spk"].get(i) or dspk,
                         line=lines.get(i,""), seg=tag, func=func, scene=scene))
    return rows

def audit(rows, film):
    """时间轴审核：连续性 / 栅格合法 / 时长收敛 / 成片精确"""
    issues = []
    # 1 连续性：相邻镜无缝无重叠
    for a, b in zip(rows, rows[1:]):
        gap = b["start"] - a["end"]
        if abs(gap) > 0.02:
            issues.append(f"镜{a['index']}→{b['index']} 时间轴{'断裂' if gap>0 else '重叠'} {gap:+.3f}s")
    # 2 栅格合法
    for r in rows:
        if (r["frames"] - 5) % 17 != 0:
            issues.append(f"镜{r['index']} 帧数 {r['frames']} 不在 17n+5 栅格")
    # 3 生成长度 ≥ 原片镜长（尾音不被切）
    for r in rows:
        if r["sec"] + 1e-6 < r["dur"]:
            issues.append(f"镜{r['index']} 生成 {r['sec']}s < 原片 {r['dur']:.3f}s（尾音会被切）")
    # 4 收尾对齐
    tail = rows[-1]["end"]
    if abs(tail - film["dur"]) > 0.5:
        issues.append(f"末镜收尾 {tail:.2f}s ≠ 原片 {film['dur']}s（差 {tail-film['dur']:+.2f}s）")
    return issues

def write_md(film, rows, issues):
    n = len(rows); gen = sum(r["sec"] for r in rows); gpu = sum(cost(r["frames"]) for r in rows)
    L = [f"# 逐镜时间轴剧本 · {film['key']}", "",
         f"> 原片 `{film['vid']}` · 时长 **{film['dur']}s** · **{n} 镜** · 平均 {film['dur']/n:.2f}s/镜",
         "> 每镜时长**锁死为原片镜长**（向上吸附 H3 栅格 17n+5 @24fps），不许注水。",
         "> 声音：**沿用原片音轨**（逐镜切片驱动口型，成片直接挂原片完整音轨）。",
         "> 画面：原片该镜关键帧作 ref_image（裁底部 10% 防字幕），构图/人物/服装全部照抄。", "",
         f"生成总长 **{gen:.1f}s** → 拼片逐镜裁回原片镜长，**成片精确 {film['dur']}s**",
         f"GPU 机时 **{gpu/3600:.2f}h**（双卡挂钟 ≈ {gpu/3600/1.95:.2f}h）", "",
         "## 时间轴审核", ""]
    if issues:
        L.append(f"**发现 {len(issues)} 处问题：**")
        L += [f"- ⚠ {x}" for x in issues[:20]]
    else:
        L.append("✅ 连续性 / 栅格合法 / 长度收敛 / 收尾对齐 **全部通过**")
    L += ["", "## 段落总览", "", "| 段 | 时间 | 功能 | 场景 | 镜号 |", "|---|---|---|---|---|"]
    for lo, hi, tag, func, scene, spk in film["segs"]:
        ids = [str(r["index"]) for r in rows if r["seg"] == tag]
        tstr = f"{lo}–{hi}s" if hi < 900 else f"{lo}s–结尾"
        L.append(f"| {tag} | {tstr} | {func} | {scene} | {ids[0]}–{ids[-1]}" if ids else f"| {tag} | {tstr} | | | |")
    L += ["", "## 逐镜表", "",
          "| 镜 | 起止 | 时长 | 帧数/秒 | 景别 | 说话人 | 台词 | 段落 | 参考帧 |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        m1, s1 = divmod(r["start"], 60); m2, s2 = divmod(r["end"], 60)
        L.append(f"| {r['index']} | {int(m1):02d}:{s1:05.2f}–{int(m2):02d}:{s2:05.2f} | {r['dur']:.2f}s | "
                 f"{r['frames']}帧/{r['sec']}s | {r['framing']} | {r['speaker']} | {r['line']} | "
                 f"{r['seg']} | `{r['kf']}` |")
    p = f"{OUT}/剧本_{film['key']}_逐镜时间轴.md"
    open(p, "w", encoding="utf-8").write("\n".join(L) + "\n")
    return p, gen, gpu, issues

def main():
    allrows = {}
    report = ["# 时间轴审核报告 · 三部全量", ""]
    tot_gpu = 0; tot_shots = 0
    for f in FILMS:
        rows = build(f)
        iss = audit(rows, f)
        p, gen, gpu, iss = write_md(f, rows, iss)
        allrows[f["key"]] = rows
        tot_gpu += gpu; tot_shots += len(rows)
        frames = [r["frames"] for r in rows]
        report += [f"## {f['key']}（{f['vid']}）", "",
                   f"- 镜数 **{len(rows)}** · 原片 {f['dur']}s · 平均 {f['dur']/len(rows):.2f}s/镜",
                   f"- 帧数区间 {min(frames)}–{max(frames)}（均值 {sum(frames)//len(frames)}）",
                   f"- 生成总长 {gen:.1f}s → 成片裁回 **{f['dur']}s**",
                   f"- GPU 机时 {gpu/3600:.2f}h",
                   f"- 审核：**{'✅ 通过' if not iss else f'⚠ {len(iss)} 处'}**"]
        if iss:
            report += [f"  - {x}" for x in iss[:10]]
        report.append("")
    report += [f"## 合计", "",
               f"- 总镜数 **{tot_shots}**",
               f"- GPU 总机时 **{tot_gpu/3600:.2f}h** → 双卡挂钟 ≈ **{tot_gpu/3600/1.95:.2f}h**",
               f"- 成片总时长 {sum(f['dur'] for f in FILMS):.1f}s（三部各与原片等长）",
               f"- 对照：按旧做法每镜 14.75s 出 {tot_shots} 镜需 {tot_shots*558/3600/1.95:.1f}h（双卡）"]
    rp = f"{OUT}/审核_时间轴_三部.md"
    open(rp, "w", encoding="utf-8").write("\n".join(report) + "\n")
    json.dump(allrows, open(f"{OUT}/shots_all.json","w",encoding="utf-8"), ensure_ascii=False)
    print("\n".join(report[-8:]))
    for f in FILMS:
        print(f"[✓] 剧本_{f['key']}_逐镜时间轴.md  ({len(allrows[f['key']])} 镜)")
    print(f"[✓] {rp}")
    print(f"[✓] shots_all.json（{tot_shots} 镜生产数据）")

if __name__ == "__main__":
    main()
