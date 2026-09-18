#!/usr/bin/env python3
# -*- coding: utf-8 -*-
ISSUES = [
 ("P0","片1《三十八万八》","镜6 → 镜8","★★★ 承诺与兑现不符：说去看海，结局是雪山",
  "镜6 台词「走！爸，我带你去看真正的海！」，但镜8 结局是 <code>elevated plateau overlook ... Snow-capped mountains</code>——<b>高原雪山，没有海</b>。且剧本主题栏白纸黑字写「自驾川藏线」，川藏线更到不了海。这是全片情绪落点，观众会出戏。",
  "改台词（不动画面，成本最低）：<br><code>走！爸，我带你去看真正的天地！</code><br>或更周星驰：<code>走！爸，这三十八万八，咱爷俩自己花！</code><br><span class=mut>不建议改结局——雪山高原的视觉已完成度高，改画面要重跑整镜。</span>"),

 ("P0","片2《老子不娶了》","镜2","★★★ 「那三十万」从未交代，观众没有参照系",
  "台词「<b>除了那三十万</b>，进屋前再撂二十万下车礼」——三十万是什么？彩礼？已付？全片 8 镜<b>从头到尾没提过</b>。观众听到时无法判断加价的严重程度，戏剧张力折损一半。",
  "台词里自解释，加两个字即可：<br><code>除了那三十万彩礼，进屋前再撂二十万下车礼，给小勇凑个全款。</code>"),

 ("P0","片2《老子不娶了》","镜2","★★★ 「小勇」凭空出现，加价动机完全缺失",
  "「给<b>小勇</b>凑个全款」——小勇是谁？全片<b>无此角色、无铺垫、无身份说明</b>。而这句正是老丈人临时加二十万的<b>唯一动机</b>。动机不明，冲突就成了无理取闹。",
  "在台词里点明身份与用途：<br><code>除了那三十万彩礼，进屋前再撂二十万下车礼——我得给小勇买房凑全款。</code><br><span class=mut>「我得给」三字点出小勇是老丈人的儿子（新娘的弟弟），动机立刻成立。</span>"),

 ("P0","片3《加名之夜》","镜8","★★★ 病句：「雨……终于停不下来了。」",
  "语义自相矛盾：「<b>终于</b>」＝期待已久的好事达成；「<b>停不下来了</b>」＝坏事持续。二者不能并存。<br>更要命的是与情绪、画面双冲突：prompt 写 <code>profound liberation</code>（解脱），画面是 <code>rain-swept sidewalk</code>（雨还在下）。<br>观众听不懂，也感受不到解脱。",
  "保留「雨」的意象，改成说得通的解脱句：<br><code>雨……终于淋不到我了。</code><br>或更彻底：<code>雨……下吧，反正淋不到我了。</code>"),

 ("P0","片3《加名之夜》","镜1 → 镜7","★★ 水桶物理不成立：90 秒接满并倾倒",
  "镜1：水「一滴滴」滴进红塑料桶（<code>drips in steady rhythm</code>）。<br>镜7：桶「<b>已溢流并倾倒</b>」（<code>overflowing ... under the weight of accumulated rainwater</code>）。<br>中间剧情时间只有几分钟，靠滴水接满一桶要<b>数小时</b>。这个镜头是片子的收尾意象，穿帮会很显眼。",
  "把「满」前置到镜1，让倾倒自然成立：<br>镜1 改为 <code>drips ... into a faded red plastic bucket already brimming to the rim</code>（<b>水面已齐桶沿</b>）。<br>镜7 不改。"),

 ("P1","片1《三十八万八》","镜1 → 镜4","★★ 道具链断裂：红绒布袋凭空消失",
  "镜1 老李「<b>紧抱一个红色天鹅绒小袋</b>在胸前」（明显是装存折的，情感道具）。<br>镜4 掏存折时却是「拉开<b>内胸口袋</b>、展开一块茶渍手帕」——绒布袋<b>再没出现过</b>。",
  "让镜4 从绒布袋取，保住道具的情感重量：<br><code>carefully unties a small red velvet pouch and unfolds a faded tea-stained cotton handkerchief</code>"),

 ("P1","片1《三十八万八》","镜3","★★ 用语错：「绝不下轿」但新娘根本没上轿",
  "镜3 场景是<b>娘家闺房</b>（粉气球婚床、新娘在刷手机）。此时新娘<b>还没出门，何来「下轿」</b>？「下轿」是到了男方家才发生的动作。",
  "改成符合场景的威胁：<br><code>不拿出这三十八万八，我家静静绝不出这个门！</code>"),

 ("P1","片1《三十八万八》","镜2 → 镜4","★ 进屋过程缺失",
  "镜2 新郎还在<b>门外</b>敲门、被塞纸条；镜4 老父亲已经在<b>屋内</b>掏存折（背景还有围观者窃语、荧光灯）。中间「怎么进的门」完全没交代。",
  "镜4 首段加一句过渡即可：<br><code>Having been reluctantly let into the bridal bedroom, the weathered trembling hands of &lt;Subject 2&gt; ...</code>"),

 ("P1","片2《老子不娶了》","镜6","★ 「把算盘收好」——但算盘已经碎了",
  "镜3 算盘珠崩飞、<code>the fractured abacus frame</code>（框架已裂）。<br>镜6 大彪却喊「爹，<b>把算盘收好</b>」——「收好」用于完好之物，抱着个碎算盘说「收好」有点怪。",
  "换动词，碎物用「拿好/带上」：<br><code>爹，把算盘拿好，咱们爷俩走大路！</code>"),

 ("P1","片2《老子不娶了》","全片","★ 新娘全程缺席（S4 未定义）",
  "8 镜里<b>没有新娘这个角色</b>，只在镜4 台词「这闺女今天绝不出门坎」里被提到。对比片1 有 S4 静静、片3 有 S2 恩熙，片2 的「嫁闺女」却不见闺女。",
  "<span class=mut>建议<b>不改</b>——片2 是纯雄性视角（大院、唢呐、摩托、戈壁），新娘缺席是风格选择，硬加反而破坏调性。此处仅作标注。</span>"),

 ("P1","片3《加名之夜》","全片","★★ 角色命名中韩混用，设定不统一",
  "同一个故事里：新郎叫<b>振浩</b>（中文），新娘 <code>EUN-HEE</code>（韩式罗马音），丈母娘 <code>MADAM-PARK</code>（韩姓「朴」）。<br>但全片是<b>中文语境</b>：人民币 1,200,000、房产加名、民间借贷。设定是撕裂的。",
  "统一为中文语境（改动只在 prompt 描述，不动台词）：<br><code>MADAM-PARK</code> → <code>MADAM-HE</code>（何女士）<br><code>EUN-HEE</code> → <code>EN-XI</code>（恩熙）"),

 ("P1","片3《加名之夜》","镜5","★★ 五个手印 vs 两个人，关系说不清",
  "「<code>stamped with five vivid crimson thumbprints matching the bride and mother's names</code>」——<b>5 个手印</b>，却对应<b>新娘和母亲 2 个人</b>的名字。到底是 5 张借据各按一次？还是另有 3 个债务人？剧本没说。",
  "去掉具体数字，改为可自洽的表述：<br><code>stamped with row upon row of crimson thumbprints bearing the bride's and her mother's names</code>"),

 ("P1","片3《加名之夜》","镜4 / 镜7","★ 打火机与公文包均未铺垫",
  "镜4 新郎俯身捡「掉落的银色打火机」从而发现欠条——但全片没交代他抽烟，打火机来历突兀。<br>镜7 他「拉上<b>黑色皮质公文包</b>」——此前 6 镜从未出现过这个包。",
  "打火机<b>建议保留</b>（偶然发现秘密正是奉俊昊式的冷峻偶然性，生活里也说得通）。<br>公文包<b>需补铺垫</b>，镜6 末加一句：<code>beside his chair rests a black leather briefcase</code>"),

 ("P1","跨片 · 三部曲","片1 vs 片2","★★ 结构高度雷同，同质化",
  "两片骨架几乎一致：<b>迎亲被临时加价 → 老父亲卑微掏钱 → 男主爆发砸/撕 → 带父亲离开 → 载具狂飙 → 日落远景落幕</b>。差异只在载具（轿车 vs 挎斗摩托）和地貌（雪山 vs 戈壁）。放在同一部三部曲里连看，会觉得重复。",
  "<span class=mut>建议<b>本轮不改</b>，先保证单片成立。若要差异化，最小成本是把片2 镜8 的「日落」改成「夜色中车灯远去」，与片1 的暖橙日落拉开。</span>"),

 ("P2","片1《三十八万八》","镜1 → 镜8","· 时间跨度：正午 → 日落",
  "镜1 <code>dusty midday sunbeams</code>，镜8 <code>sunset</code>。中间是开车长途，时间跳跃合理。<b>可接受。</b>","—"),
 ("P2","片3《加名之夜》","镜7 → 镜8","· 从走廊直接切到街上",
  "镜7 新郎刚走出门到走廊，镜8 已在街上打伞走过。省略了下楼与出楼，短剧常见手法。<b>可接受。</b>","—"),
]

def cls(x): return {"P0":"p0","P1":"p1","P2":"p2"}[x]
rows=[]
for lv,film,loc,title,why,fix in ISSUES:
    rows.append("""<tr>
<td class="c"><span class="lv %s">%s</span></td>
<td class="nowrap">%s<br><span class="mut">%s</span></td>
<td><b>%s</b><div class="why">%s</div></td>
<td class="fix">%s</td></tr>""" % (cls(lv), lv, film, loc, title, why, fix))

n_p0 = sum(1 for i in ISSUES if i[0]=="P0")
n_p1 = sum(1 for i in ISSUES if i[0]=="P1")

HTML = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>现代婚姻三部曲 · 剧本与分镜逻辑审查</title><style>
:root{--bg:#f7f8fa;--card:#fff;--line:#e3e6ea;--tx:#1f2328;--tx2:#5b6570;--p0:#c0392b;--p1:#b7791f;--p2:#6b7280}
*{box-sizing:border-box}
body{margin:0;padding:32px 28px;background:var(--bg);color:var(--tx);
 font:14px/1.7 -apple-system,"PingFang SC","Helvetica Neue",Arial,sans-serif}
.wrap{max-width:1320px;margin:0 auto}
h1{font-size:24px;margin:0 0 6px}
.sub{color:var(--tx2);margin:0 0 20px;font-size:13px}
.sum{display:flex;gap:14px;margin-bottom:22px;flex-wrap:wrap}
.box{background:#fff;border:1px solid var(--line);border-radius:10px;padding:14px 20px;min-width:150px}
.box .n{font-size:26px;font-weight:700}
.box .l{font-size:12px;color:var(--tx2)}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
table{width:100%;border-collapse:collapse;font-size:13px}
th{background:#eef1f4;text-align:left;padding:10px;font-weight:600;border-bottom:2px solid var(--line)}
td{padding:12px 10px;border-bottom:1px solid #f0f2f4;vertical-align:top}
tr:hover td{background:#fafbfc}
.c{text-align:center}
.nowrap{white-space:nowrap;font-size:12px}
.lv{display:inline-block;color:#fff;padding:2px 9px;border-radius:5px;font-weight:700;font-size:12px}
.p0{background:var(--p0)} .p1{background:var(--p1)} .p2{background:var(--p2)}
.why{margin-top:6px;color:var(--tx2);font-size:12.5px;line-height:1.65}
.fix{background:#f6fbf7;font-size:12.5px}
.mut{color:#9aa3ad;font-size:11.5px}
code{background:#f2f4f6;padding:1px 5px;border-radius:3px;font-size:12px;
 font-family:"SF Mono",Menlo,Consolas,monospace;word-break:break-word}
.note{background:#fffdf5;border:1px solid #f0e3b8;border-radius:8px;padding:14px 16px;
 font-size:13px;margin-top:18px}
.note b{color:#8a6d00}
</style></head><body><div class="wrap">
<h1>现代婚姻三部曲 · 剧本与分镜逻辑审查</h1>
<p class="sub">2026-09-18 · 审查对象：3 部剧本原文（生成脚本_*.md）+ 24 镜 manifest · 维度：场景一致性 / 设定一致性 / 道具连续性 / 因果链 / 台词自洽</p>
<div class="sum">
<div class="box"><div class="n" style="color:var(--p0)">__P0__</div><div class="l">P0 必改（逻辑硬伤）</div></div>
<div class="box"><div class="n" style="color:var(--p1)">__P1__</div><div class="l">P1 建议改</div></div>
<div class="box"><div class="n" style="color:var(--p2)">__P2__</div><div class="l">P2 可接受</div></div>
<div class="box"><div class="n">24</div><div class="l">审查镜数</div></div>
</div>
<div class="card"><table>
<tr><th style="width:52px">级别</th><th style="width:150px">片 · 位置</th><th>问题</th><th style="width:38%">改法（可直接执行）</th></tr>
__ROWS__
</table></div>
<div class="note">
<b>结论：建议 P0 改完再开拍。</b><br>
5 处 P0 里有 3 处是<b>台词级</b>问题（片2 两处、片3 一处），改完需<b>重新生成对应镜的 TTS 干声</b>，成本极低；
另 2 处是<b>prompt 级</b>（片1 结局承诺、片3 水桶），改的是描述文字，不额外烧卡。<br><br>
<b>为什么必须改</b>：这 5 处都不是审美问题，而是<b>观众会当场出戏</b>的断裂——
说去看海却开到雪山、老丈人为一个没出现过的人加价、主角用病句说遗言、水桶在几分钟内自己接满。
短剧没有解释时间，一处不合理，整片的信任就没了。<br><br>
<b>P1 里我建议不改的两条</b>：片2 新娘缺席（纯雄性视角是风格，硬加破坏调性）、片1/片2 结构雷同（先保单片成立，差异化留到第二轮）。
</div>
</div></body></html>"""

HTML = (HTML.replace("__ROWS__", "\n".join(rows))
            .replace("__P0__", str(n_p0))
            .replace("__P1__", str(n_p1))
            .replace("__P2__", str(len(ISSUES)-n_p0-n_p1)))
out = "02_剧本逻辑审查_20260918.html"
open(out, "w", encoding="utf-8").write(HTML)
print("已生成:", out, "P0=%d P1=%d P2=%d" % (n_p0, n_p1, len(ISSUES)-n_p0-n_p1))
