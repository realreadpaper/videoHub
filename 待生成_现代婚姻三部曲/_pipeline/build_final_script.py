#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成《现代婚姻三部曲》成品剧本（定稿 v2）Markdown + HTML。"""
import json, os, html

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILMS = [
 ("01_周星驰_三十八万八", "f1", "《三十八万八》", "周星驰 · 市井荒诞",
  "迎亲当天被临时加价三十八万八的「停车费」：老父亲掏空存折仍不够，新郎阿星先大笑后落泪，撕碎胸花，拉上父亲自驾川藏线。",
  [("阿星 A-XING", "S1", "30 岁新郎，瘦削、汗湿额头、眼里带倔。租来的黑西装 + 歪红领带"),
   ("老李 OLD-LI", "S2", "65 岁父亲，佝偻、手抖、灰白发。褪色藏蓝冲锋衣，胸前紧抱红绒布袋"),
   ("丈母娘", "S3", "55 岁，烫发、大红金旗袍，双臂抱胸"),
   ("静静 JING-JING", "S4", "28 岁新娘，浓妆白纱，全程刷手机")],
  [(1,"楼梯间·汗","中近景 MCU","阿星捧着微蔫的玫瑰回头安慰父亲；两步之下，老李紧抱红绒布袋跟上，汗从鬓角淌下。"),
   (2,"防盗门·纸条","近景 CU","铁门上褪色的红双喜剪纸。阿星敲门递红包，猫眼滑开，一张纸条从门缝塞出，他的笑瞬间冻住。"),
   (3,"闺房·丈母娘","中景 MS","粉色气球婚床上静静低头刷手机；右侧丈母娘旗袍抱胸，指门叫价。吊扇在头顶转。"),
   (4,"父亲·存折","特写 CU","进屋后，老李解开胸前的红绒布袋，展开茶渍手帕里包着的两万存折，抬头卑微哀求。围观者窃语。"),
   (5,"阿星·笑与泪","面部特写 CU","先是爆发大笑，笑到眼眶发红，一把扯碎胸前的塑料红胸花。"),
   (6,"楼下·调头","全景 WS","扯掉领带扔在地上，拉起父亲下楼离开筒子楼。"),
   (7,"高速·车窗风","中景 MS","白色轿车疾驰，风灌进车窗，父亲安静地剥橘子。"),
   (8,"高原·日落","中远景→全景","海拔公路边停车，雪山在橙紫暮色中发亮。父子分食一只橘子。")]),

 ("02_姜文_老子不娶了", "f2", "《老子不娶了》", "姜文 · 雄性荷尔蒙",
  "北方大院迎亲，老丈人在红木桌上用毛笔追加二十万「下车礼」。老父亲拨算盘算到珠子崩飞，儿子大彪掀翻八仙桌，撕碎双喜，扶爹骑挎斗摩托走人。",
  [("大彪", "S1", "30 岁新郎，寸头、黑皮夹克、皮靴。雄性、干脆、爆发力强"),
   ("老父亲", "S2", "62 岁，佝偻、指甲缝带泥。拨了一辈子算盘"),
   ("老丈人", "S3", "58 岁，中山装、旱烟袋、红木桌后的当家人")],
  [(1,"大院·唢呐","中景 MS","皮靴砸在青砖上，大彪冲唢呐班吼：往死里吹。红双喜贴在土墙。"),
   (2,"红木桌·契约","中近景 MCU","老丈人抽烟，红纸契约上毛笔字淋漓，慢悠悠追加二十万下车礼。"),
   (3,"算盘·崩珠","特写 CU","父亲的手拨算盘，一颗算盘珠突然崩飞弹出，木框开裂。"),
   (4,"旱烟袋·通牒","中景 MS","旱烟袋敲在红木桌上：规矩不能坏，差一分不出门坎。"),
   (5,"掀桌","面部特写→中景","大彪双目通红，一把掀翻八仙桌，碗碟与算盘齐飞。"),
   (6,"撕双喜","全景 WS","撕碎墙上的红双喜剪纸，扶起父亲大步走出院门。"),
   (7,"挎斗摩托","中景 MS","长江 750 挎斗摩托点火，父亲坐进挎斗吼：油门拧到底。"),
   (8,"戈壁·日落","远景→全景","摩托在戈壁公路上远去，太阳照常升起。")]),

 ("03_奉俊昊_加名之夜", "f3", "《加名之夜》", "奉俊昊 · 阴冷悬疑",
  "雨夜的半地下室，丈母娘以「定心丸」为名要求房产加名。新郎振浩捡打火机时从沙发缝里摸出一沓欠条——一百二十万的债，正等着被一并过户到他名下。",
  [("振浩", "S1", "32 岁新郎，清瘦、炭灰羊毛大衣、无边眼镜。冷静、克制"),
   ("恩熙 EN-XI", "S2", "28 岁新娘，低马尾、米色针织衫。眼神回避"),
   ("何女士 MADAM-HE", "S3", "56 岁丈母娘，尖眉、紧发髻、红宝石戒指。精算")],
  [(1,"半地下室·水桶","中景 MS","雨夜。天花板裂缝的水一滴滴落进红塑料桶，水面已齐桶沿。矮桌上摊着房产加名协议。"),
   (2,"红宝石·钢笔","中近景 MCU","丈母娘转着钢笔，把加名协议推过来：女人要的是一份定心丸。"),
   (3,"咖啡·倒影","特写 CU","恩熙搅咖啡，杯中倒影晃动，始终不看他。"),
   (4,"沙发缝·欠条","特写 CU","俯身捡掉落的银色打火机，指尖从沙发缝里抽出一沓发黄折叠欠条。"),
   (5,"微距·欠条与手印","微距特写","推近：手写墨迹与一排排鲜红手印。死寂。"),
   (6,"桌·对峙","中景 MS","三人同框。振浩把欠条压在加名协议上，说出冰冷结论。椅子旁放着黑色公文包。"),
   (7,"门锁·倾倒","中景 MS","钢门重重合上。屋内红桶忽然倾倒，积水漫开。"),
   (8,"夜雨·伞","中远景→全景","撑伞走入雨夜街道，车灯与雨刷交替扫过。")]),
]

CHANGES = [
 ("P0","片1 镜6","走！爸，我带你去看真正的海！","走！爸，我带你去看真正的天地！",
  "结局是高原雪山，且主题为自驾川藏线——到不了海。改台词比改结局便宜得多。"),
 ("P0","片2 镜2","除了那三十万，进屋前再撂二十万下车礼，给小勇凑个全款。",
  "除了那三十万彩礼，进屋前再撂二十万下车礼——我得给小勇买房凑全款。",
  "「三十万」性质全片未交代，「小勇」无身份说明，而这句正是加价二十万的唯一动机。"),
 ("P0","片3 镜8","雨……终于停不下来了。","雨……终于淋不到我了。",
  "「终于」＝好事达成，「停不下来」＝坏事持续，语义打架；且与「解脱」情绪、仍在下雨的画面双冲突。"),
 ("P0","片3 镜1","水一滴滴落进红塑料桶","水一滴滴落进水面已齐桶沿的红塑料桶",
  "靠滴水接满一桶需数小时，而剧情内只有几分钟。把「满」前置，镜7 的倾倒才成立。"),
 ("P1","片1 镜3","不拿出这三十八万八，我家静静绝不下轿！","不拿出这三十八万八，我家静静绝不出这个门！",
  "场景是娘家闺房，新娘尚未出门，谈不上「下轿」。"),
 ("P1","片1 镜4","拉开内胸口袋取存折","解开胸前的红绒布袋取存折",
  "镜1 起紧抱的红绒布袋在镜4 凭空消失。改回绒布袋，保住道具的情感重量。"),
 ("P1","片1 镜4","（无过渡）","补入「被勉强让进喜房后」",
  "镜2 还在门外被塞纸条，镜4 已在屋内掏存折，中间过程缺失。"),
 ("P1","片2 镜6","爹，把算盘收好","爹，把算盘拿好",
  "镜3 算盘已崩珠开裂，「收好」用于完好之物。"),
 ("P1","片3 镜2/3","MADAM-PARK / EUN-HEE","MADAM-HE（何女士）/ EN-XI（恩熙）",
  "韩式命名与人民币、房产加名的中文语境撕裂。"),
 ("P1","片3 镜5","五个红手印对应两个人的名字","一排排红手印",
  "5 个手印 vs 2 个人，关系说不清。去掉具体数字。"),
 ("P1","片3 镜6","（公文包未铺垫）","补入「椅子旁放着黑色公文包」",
  "镜7 拉上的公文包此前 6 镜从未出现。"),
]

def build():
    md = []
    md.append("# 《现代婚姻三部曲》成品剧本 · 定稿 v2")
    md.append("")
    md.append("> 生成于 2026-09-18 · 在 v1 基础上完成剧本逻辑审查后的修正 · **共 3 部 × 8 镜 = 24 镜**")
    md.append(">")
    md.append("> **生产约束（已写死在流水线里，不可绕过）**")
    md.append("> 1. **两段流水线**：Stage1 全部 24 镜草稿跑完 → 强制释放显存 → 才加载 Stage2 权重精修。绝不逐镜交替。")
    md.append("> 2. **零字幕**：成片不烧字幕，字幕以独立 `.srt`/`.vtt` 交付；画面内所有文字道具一律降级为「字迹不可辨」，每镜末尾注入 `strict_output_constraints` 强制段。")
    md.append("> 3. **时长栅格**：H3 `length` ∈ 17n+5，LTX 再裁到 8n+1。成片时长 ≠ H3 帧数÷24，字幕轴必须按成片时长算。")
    md.append("")
    md.append("---")
    md.append("")

    total_s = 0
    for d, fk, title, style, synopsis, cast, shots in FILMS:
        man = json.load(open(os.path.join(ROOT, d, "manifest.json"), encoding="utf-8"))
        by_no = {s["no"]: s for s in man["shots"]}
        film_s = sum(s["duration"] for s in man["shots"])
        total_s += film_s
        md.append("## %s｜%s" % (title, style))
        md.append("")
        md.append("**一句话**：%s" % synopsis)
        md.append("")
        md.append("**成片时长**：%.3f 秒（8 镜）｜**画幅**：1344×768（16:9）竖屏转横屏 ｜**帧率**：24 fps" % film_s)
        md.append("")
        md.append("**人物表**")
        md.append("")
        md.append("| 角色 | 代号 | 外形与气质 |")
        md.append("|---|---|---|")
        for nm, sid, desc in cast:
            md.append("| %s | %s | %s |" % (nm, sid, desc))
        md.append("")
        md.append("**分镜表**")
        md.append("")
        md.append("| 镜 | Key | 场景 | 景别 | 成片时长 | H3 帧 | 角色 | 画面要点 | 台词 |")
        md.append("|---|---|---|---|---|---|---|---|---|")
        for no, scene, framing, desc in shots:
            s = by_no[no]
            dlg = (s.get("dialogue_cn") or "").strip()
            dlg = dlg if dlg else "—"
            md.append("| %d | `%ss%02d` | %s | %s | %.3fs | %d | %s | %s | %s |" % (
                no, fk, no, scene, framing, s["duration"], s["h3_length"],
                s["character"].replace("|", "/"), desc, dlg))
        md.append("")
        md.append("---")
        md.append("")

    md.append("## 本轮修改记录（v1 → v2）")
    md.append("")
    md.append("| 级别 | 位置 | 原文 | 改为 | 为什么 |")
    md.append("|---|---|---|---|---|")
    for lv, loc, old, new, why in CHANGES:
        md.append("| %s | %s | %s | %s | %s |" % (lv, loc, old, new, why))
    md.append("")
    md.append("### 明确不改的三条")
    md.append("")
    md.append("1. **片2 新娘全片缺席** —— 纯雄性视角（大院/唢呐/摩托/戈壁）是风格选择，硬加反而破坏调性。")
    md.append("2. **片1 与片2 结构雷同** —— 都是「加价 → 父亲卑微 → 爆发 → 逃离 → 日落远景」。先保单片成立，差异化留到下一轮。")
    md.append("3. **片3 镜4 的打火机** —— 偶然发现秘密正是奉俊昊式的冷峻偶然性，生活里也说得通。")
    md.append("")
    md.append("---")
    md.append("")
    md.append("**全三片合计 %.2f 秒｜24 镜｜预计机时约 52 分钟（A100 热态批处理口径）**" % total_s)

    out_md = os.path.join(ROOT, "03_成品剧本_定稿_v2_20260918.md")
    open(out_md, "w", encoding="utf-8").write("\n".join(md))
    print("Markdown:", out_md)

    # ── HTML ──
    def e(x): return html.escape(str(x))
    H = ["<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>",
         "<title>现代婚姻三部曲 · 成品剧本定稿 v2</title><style>",
         ":root{--bg:#f7f8fa;--card:#fff;--line:#e3e6ea;--tx:#1f2328;--tx2:#5b6570;--acc:#c0392b;--p0:#c0392b;--p1:#b7791f}",
         "*{box-sizing:border-box}body{margin:0;padding:34px 30px;background:var(--bg);color:var(--tx);",
         "font:14px/1.72 -apple-system,'PingFang SC','Helvetica Neue',Arial,sans-serif}",
         ".wrap{max-width:1360px;margin:0 auto}h1{font-size:26px;margin:0 0 8px}",
         ".sub{color:var(--tx2);margin:0 0 20px;font-size:13px}",
         ".card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:22px 24px;margin-bottom:20px}",
         ".card h2{font-size:20px;margin:0 0 4px;color:var(--acc)}",
         ".style{color:var(--tx2);font-size:13px;margin:0 0 12px}",
         ".syn{background:#fafbfc;border-left:3px solid var(--acc);padding:10px 14px;margin:10px 0 16px;font-size:13.5px}",
         ".meta{font-size:12.5px;color:var(--tx2);margin-bottom:14px}",
         "table{width:100%;border-collapse:collapse;font-size:13px;margin-bottom:8px}",
         "th{background:#eef1f4;text-align:left;padding:9px 10px;font-weight:600;border-bottom:2px solid var(--line);white-space:nowrap}",
         "td{padding:9px 10px;border-bottom:1px solid #f0f2f4;vertical-align:top}",
         "tr:hover td{background:#fafbfc}",
         ".c{text-align:center;white-space:nowrap}",
         "code{background:#f2f4f6;padding:1px 5px;border-radius:3px;font-size:12px}",
         ".dlg{color:var(--acc);font-weight:600}",
         ".mute{color:#9aa3ad}",
         ".lv{display:inline-block;color:#fff;padding:1px 7px;border-radius:4px;font-size:11.5px;font-weight:700}",
         ".p0{background:var(--p0)}.p1{background:var(--p1)}",
         ".old{color:#a04040;text-decoration:line-through}",
         ".new{color:#1a7a45;font-weight:600}",
         ".note{background:#fffdf5;border:1px solid #f0e3b8;border-radius:8px;padding:14px 16px;font-size:13px}",
         ".note b{color:#8a6d00}",
         "ol{padding-left:20px}</style></head><body><div class='wrap'>",
         "<h1>《现代婚姻三部曲》成品剧本 · 定稿 v2</h1>",
         "<p class='sub'>2026-09-18 · 逻辑审查后修正 · 3 部 × 8 镜 = 24 镜</p>",
         "<div class='note'><b>生产约束（已写死在流水线，不可绕过）</b><ol>",
         "<li><b>两段流水线</b>：Stage1 全部 24 镜草稿跑完 → 强制释放显存 → 才加载 Stage2 权重精修。绝不逐镜交替。</li>",
         "<li><b>零字幕</b>：成片不烧字幕，字幕独立外挂；画面内所有文字道具降级为「字迹不可辨」，每镜末尾注入 <code>strict_output_constraints</code> 强制段。</li>",
         "<li><b>时长栅格</b>：H3 <code>length</code> ∈ 17n+5，LTX 再裁到 8n+1。<b>成片时长 ≠ H3 帧数÷24</b>，字幕轴必须按成片时长算。</li>",
         "</ol></div>"]

    for d, fk, title, style, synopsis, cast, shots in FILMS:
        man = json.load(open(os.path.join(ROOT, d, "manifest.json"), encoding="utf-8"))
        by_no = {s["no"]: s for s in man["shots"]}
        film_s = sum(s["duration"] for s in man["shots"])
        H.append("<div class='card'>")
        H.append("<h2>%s</h2><p class='style'>%s</p>" % (e(title), e(style)))
        H.append("<div class='syn'>%s</div>" % e(synopsis))
        H.append("<p class='meta'>成片 %.3f 秒 · 1344×768 横屏 · 24 fps</p>" % film_s)
        H.append("<table><tr><th>角色</th><th>代号</th><th>外形与气质</th></tr>")
        for nm, sid, desc in cast:
            H.append("<tr><td><b>%s</b></td><td class='c'>%s</td><td>%s</td></tr>" % (e(nm), e(sid), e(desc)))
        H.append("</table>")
        H.append("<table><tr><th>镜</th><th>Key</th><th>场景</th><th>景别</th><th>时长</th><th>H3帧</th><th>画面要点</th><th>台词</th></tr>")
        for no, scene, framing, desc in shots:
            s = by_no[no]
            dlg = (s.get("dialogue_cn") or "").strip()
            dlgcell = "<span class='dlg'>%s</span>" % e(dlg) if dlg else "<span class='mute'>—</span>"
            H.append("<tr><td class='c'><b>%d</b></td><td class='c'><code>%ss%02d</code></td>"
                     "<td>%s</td><td class='c'>%s</td><td class='c'>%.3fs</td><td class='c'>%d</td>"
                     "<td>%s</td><td>%s</td></tr>"
                     % (no, fk, no, e(scene), e(framing), s["duration"], s["h3_length"], e(desc), dlgcell))
        H.append("</table></div>")

    H.append("<div class='card'><h2 style='color:#1f2328'>本轮修改记录（v1 → v2）</h2>")
    H.append("<table><tr><th style='width:50px'>级别</th><th style='width:110px'>位置</th><th>原文</th><th>改为</th><th>为什么</th></tr>")
    for lv, loc, old, new, why in CHANGES:
        H.append("<tr><td class='c'><span class='lv %s'>%s</span></td><td>%s</td>"
                 "<td><span class='old'>%s</span></td><td><span class='new'>%s</span></td><td>%s</td></tr>"
                 % (lv.lower(), lv, e(loc), e(old), e(new), e(why)))
    H.append("</table>")
    H.append("<div class='note' style='margin-top:16px'><b>明确不改的三条</b><ol>"
             "<li><b>片2 新娘全片缺席</b> —— 纯雄性视角（大院/唢呐/摩托/戈壁）是风格选择，硬加反而破坏调性。</li>"
             "<li><b>片1 与片2 结构雷同</b> —— 都是「加价 → 父亲卑微 → 爆发 → 逃离 → 日落远景」。先保单片成立，差异化留到下一轮。</li>"
             "<li><b>片3 镜4 的打火机</b> —— 偶然发现秘密正是奉俊昊式的冷峻偶然性，生活里也说得通。</li>"
             "</ol></div></div>")
    H.append("</div></body></html>")

    out_html = os.path.join(ROOT, "03_成品剧本_定稿_v2_20260918.html")
    open(out_html, "w", encoding="utf-8").write("\n".join(H))
    print("HTML    :", out_html)
    print("全三片合计 %.2f 秒" % total_s)

build()
