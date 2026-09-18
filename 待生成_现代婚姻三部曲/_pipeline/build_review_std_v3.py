#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成《剧本审查标准 v3》HTML（浅色主题）"""
import os, datetime

ROOT = "/Users/hejianglong/Desktop/videoHub/待生成_现代婚姻三部曲"
OUT = os.path.join(ROOT, "05_剧本审查标准_v3_20260918.html")

HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>剧本审查标准 v3</title>
<style>
:root{--bg:#f7f7f5;--card:#fff;--line:#e4e4e0;--ink:#232323;--sub:#71717a;--red:#c0392b;--green:#1a8a4a;--amber:#b8860b;--blue:#2b5cd9}
*{box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Helvetica Neue",sans-serif;
background:var(--bg);color:var(--ink);margin:0;padding:40px 32px;line-height:1.72;font-size:14px}
.wrap{max-width:960px;margin:0 auto}
h1{font-size:26px;margin:0 0 6px;letter-spacing:-.3px}
h2{font-size:18px;margin:38px 0 12px;padding-bottom:8px;border-bottom:2px solid var(--line)}
h3{font-size:15px;margin:22px 0 8px}
.meta{color:var(--sub);font-size:13px;margin-bottom:8px}
.lead{background:#fff;border:1px solid var(--line);border-radius:10px;padding:16px 20px;margin:16px 0 8px}
.lead b{color:var(--red)}
table{border-collapse:collapse;width:100%;background:var(--card);font-size:13px;margin:12px 0;
border:1px solid var(--line);border-radius:8px;overflow:hidden}
th,td{padding:9px 12px;text-align:left;border-bottom:1px solid #efefeb;vertical-align:top}
th{background:#f2f2ee;font-weight:600;font-size:12.5px;color:#3f3f46}
tr:last-child td{border-bottom:none}
code{font-family:"SF Mono",Menlo,Consolas,monospace;font-size:12px;background:#f2f2ee;
padding:1px 5px;border-radius:4px;color:#a1442c;word-break:break-all}
.badge{display:inline-block;font-size:11px;font-weight:600;padding:2px 8px;border-radius:10px;margin-right:6px}
.b-red{background:#fdecea;color:var(--red)}
.b-green{background:#e9f6ee;color:var(--green)}
.b-amber{background:#fdf6e3;color:var(--amber)}
.b-blue{background:#eef4ff;color:var(--blue)}
.std{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--red);
border-radius:0 10px 10px 0;padding:16px 20px;margin:16px 0}
.std.g{border-left-color:var(--green)}
.std.a{border-left-color:var(--amber)}
.std.b{border-left-color:var(--blue)}
.std h3{margin-top:0}
ul,ol{margin:8px 0;padding-left:22px}
li{margin:4px 0}
.pass{color:var(--green);font-weight:600}
.fail{color:var(--red);font-weight:600}
.note{background:#fffbe9;border-left:3px solid #e0b400;padding:12px 16px;font-size:13px;
margin:14px 0;border-radius:0 6px 6px 0}
.tpl{background:#fafaf9;border:1px dashed #d4d4d0;border-radius:8px;padding:14px 18px;
font-family:"SF Mono",Menlo,monospace;font-size:12px;white-space:pre-wrap;line-height:1.7;color:#3f3f46}
.chk{list-style:none;padding-left:0}
.chk li{padding-left:26px;position:relative}
.chk li:before{content:"☐";position:absolute;left:6px;color:var(--sub)}
</style></head><body><div class="wrap">

<h1>《现代婚姻三部曲》剧本审查标准 v3</h1>
<div class="meta">生效 2026-09-18 · 替代 v2 · 适用于全部 24 镜 · 硬性标准，不通过不得烧卡</div>

<div class="lead">
本版由 <b>f3s06 实拍事故</b> 倒逼而来：画面出现「原来你们要的定心丸」屏幕字幕，
且人物表情僵硬。<br>
根因查证后确立四条硬标准——<b>每条都有可执行的判定方法</b>，不靠"看着还行"。
</div>

<h2>一、四条硬标准</h2>

<div class="std">
<h3><span class="badge b-red">S1</span>零字幕 — 画面里不得出现任何可读文字</h3>
<b>判定口径</b>：<br>
① 不得含 MiniMax H3 的 <code>&lt;d&gt;[Chinese] "…"&lt;/d&gt;</code> 结构化台词标签。
该标签会被模型当作"要渲染的画面文字"直接画进画面（尾部自然语言禁令压不过它）。<br>
② prompt 尾部必须带 <code>strict_output_constraints</code> 强制段。<br>
③ 文字承载道具（协议、纸条、对联、契约、招牌）必须显式写明
<code>rendering as completely illegible abstract marks</code>。<br>
④ 避开"要写字的纸"构图：笔尖停在签名虚线、镜头正对合同正文等会诱发乱码。<br>
<br>
<b>合格线</b>：<code>&lt;d&gt;</code> 计数 = 0；禁字段存在；文字道具全部带不可辨声明。<br>
<b>违反案例</b>：f3s06 原版含 <code>&lt;d&gt;[Chinese] "原来你们要的定心丸…"&lt;/d&gt;</code> → 字幕上屏。
</div>

<div class="std g">
<h3><span class="badge b-green">S2</span>表情到位 — 人物不得是木乃伊</h3>
<b>判定口径</b>（每镜逐条计数）：<br>
① <b>微表情 ≥ 3 处</b>：从 <code>jaw tighten / muscle twitch / blink rapidly / visible swallow /
lip tremble / eyes narrow / brow furrow / nostril flare / breath catch</code> 中取值。<br>
② <b>情绪过渡 ≥ 1 处</b>：用 transition 句式——
<code>flickering then vanishing / settles into / cracks into / drains from</code>。<br>
③ <b>禁用完全静态词</b>：<code>spine straight / unnervingly calm / completely motionless /
frozen in place / utterly calm / blank expression</code>。<br>
④ 情绪要写成"<b>表面 X 但内在 Y</b>"（如 shoulders squared but a muscle ticking in his jaw），
而不是单纯"冷静"。<br>
<br>
<b>合格线</b>：微表情 ≥ 3 且情绪过渡 ≥ 1 且静态词 = 0。<br>
<b>原理</b>：H3 是音频驱动视频，干声决定口型，但面部肌肉与神态完全由 prompt 文字决定。
prompt 全是"冷静/不动"，生成出来就是木头人。
</div>

<div class="std a">
<h3><span class="badge b-amber">S3</span>位置逻辑 — 同场景跨镜必须空间自洽</h3>
<b>判定口径</b>：<br>
① <b>多人同框镜必须给显式方位锚点</b>：
<code>on the left / on the right / in the foreground / in the background / beside / across the table /
two steps below</code>。<br>
② <b>跨镜一致</b>：同一场景内，角色的左右/前后关系在全片中不得跳变。
（母亲恒在左、新娘恒在右、新郎恒在对面）<br>
③ <b>单人镜必须给朝向</b>：<code>facing the doorway / in profile turned left / facing the camera</code>，
否则与前镜无法衔接。<br>
④ <b>视线方向服从对话对象</b>：说话者必须看向对方所在的方向；被说者若不在画内，
需写明 <code>looking off-screen toward the left</code>。<br>
<br>
<b>合格线</b>：多人镜方位词 ≥ 1 且与场景坐标表一致；单人镜朝向词 ≥ 1。<br>
<b>违反案例</b>：24 镜中 21 镜多人同框却零方位描述 → 每镜随机摆位，剪辑后人物"瞬移"。
</div>

<div class="std b">
<h3><span class="badge b-blue">S4</span>技术对齐 — 时长/分辨率/音轨/道具</h3>
<ul>
<li>时长 = H3 帧数 ÷ 24（一步直出**不经** LTX trim），prompt 时间戳末段须等于该值</li>
<li>分辨率 768×1344；音轨为原声锁干声（aac 2ch）</li>
<li>关键道具须用 <code>&lt;Prop N&gt;</code> 锚定，人物用 <code>&lt;Subject N&gt;</code> 锚定</li>
<li>产品/道具镜须满足画字像素门槛（产品占画面 ≥ 70%）</li>
</ul>
</div>

<h2>二、场景空间坐标表（S3 的判定基准）</h2>
<p class="meta">同一场景内的角色方位以此表为准，任何镜不得违反。</p>

<h3>片1《三十八万八》</h3>
<table>
<tr><th>角色</th><th>楼梯间 s01</th><th>闺房 s03</th><th>车内 s07/s08</th></tr>
<tr><td>阿星 S1</td><td>上方，背对镜头向上走</td><td>—（在门外）</td><td>驾驶座（左）</td></tr>
<tr><td>老李 S2</td><td><b>两步之下</b>，下方跟随</td><td>—（在门外）</td><td>副驾（右）</td></tr>
<tr><td>丈母娘 S3</td><td>—</td><td><b>画面右侧</b>站立，面向门口</td><td>—</td></tr>
<tr><td>静静 S4</td><td>—</td><td><b>画面左侧</b>床上坐，低头刷手机</td><td>—</td></tr>
</table>

<h3>片2《老子不娶了》</h3>
<table>
<tr><th>角色</th><th>堂屋 s02–s05</th><th>院门 s06</th><th>挎斗摩托 s07/s08</th></tr>
<tr><td>大彪 S1</td><td>桌前<b>站立</b>，面向红木桌</td><td>扶父<b>向外</b>走</td><td>跨坐主位（左）</td></tr>
<tr><td>老父亲 S2</td><td>桌<b>侧</b>，手拨算盘</td><td>被扶，在<b>右侧</b></td><td>坐<b>右侧挎斗</b></td></tr>
<tr><td>老丈人 S3</td><td><b>红木桌后</b>主位，当家人</td><td>—</td><td>—</td></tr>
</table>

<h3>片3《加名之夜》</h3>
<table>
<tr><th>角色</th><th>餐桌场景 s02/s03/s06</th></tr>
<tr><td>振浩 S1</td><td><b>前景正中</b>，背对／侧对镜头，<b>面朝母亲与新娘</b></td></tr>
<tr><td>丈母娘 S3</td><td>对面<b>左侧</b></td></tr>
<tr><td>恩熙 S2</td><td>对面<b>右侧</b></td></tr>
</table>
<div class="note"><b>要点</b>：s02 母亲单人镜 → 她必须<b>看向画面右前方</b>（振浩在右侧）；
s03 新娘镜 → 新郎出现在<b>背景右侧</b>；s06 三人同框 → 严格按上表摆位。
三镜连起来看，观众的空间感才立得住。</div>

<h2>三、审查流程（三关）</h2>
<table>
<tr><th>关</th><th>时机</th><th>手段</th><th>不通过怎么办</th></tr>
<tr><td><b>第一关</b> 自动扫描</td><td>改完 prompt，烧卡前</td>
<td><code>_pipeline/review_v3.py</code> 四条标准逐镜打分</td>
<td>任一 ✗ 即拦下，改完重扫</td></tr>
<tr><td><b>第二关</b> 试拍目视</td><td>每片挑 1 镜出片后</td>
<td>抽帧看：屏幕字幕／表情／位置／道具文字</td>
<td>不合格 → 定位到具体 prompt 句子 → 改 → 只重跑该镜</td></tr>
<tr><td><b>第三关</b> 复盘写回</td><td>每轮结束</td>
<td>结论写入 <code>AGENTS.md</code></td>
<td>形成"第 3 轮起问题在验证阶段就被拦住"</td></tr>
</table>

<h2>四、烧卡前检查清单</h2>
<ul class="chk">
<li>全部 prompt 的 <code>&lt;d&gt;</code> 计数 = 0</li>
<li>每镜尾部有 <code>strict_output_constraints</code></li>
<li>文字承载道具均标 <code>illegible abstract marks</code></li>
<li>每镜微表情提示 ≥ 3</li>
<li>每镜情绪过渡句式 ≥ 1</li>
<li>完全静态词 0 处</li>
<li>多人镜方位锚点 ≥ 1，且符合场景坐标表</li>
<li>单人镜朝向锚点 ≥ 1</li>
<li>说话者视线指向对话对象</li>
<li>prompt 时间戳末段 = manifest duration</li>
<li>工作流分辨率 768×1344、音轨为原声干声</li>
<li>服务器显存/内存已 free，队列为空</li>
</ul>

<h2>五、审查报告模板</h2>
<div class="tpl">## 第 N 轮剧本审查（YYYY-MM-DD）

### 自动扫描结果
| 镜 | S1 零字幕 | S2 表情 | S3 位置 | S4 技术 |
|---|---|---|---|---|
| f1s01 | ✓ | ✓ | ✓ | ✓ |
...

### 人工目视
- 屏幕字幕：无 / 有（位置与内容）
- 表情：自然 / 僵硬（哪个角色）
- 位置：自洽 / 跳变（哪两镜之间）
- 道具文字：不可辨 / 可读

### 本轮修复
| 问题 | 定位到 prompt 的哪一句 | 改法 | 是否重跑 |
|---|---|---|---|

### 写回 AGENTS.md
（结论 + 新增坑位）</div>

<div class="meta" style="margin-top:36px">生成于 __TS__ · 依据 f3s06 实拍事故复盘</div>
</div></body></html>"""

HTML = HTML.replace("__TS__", datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
open(OUT, "w", encoding="utf-8").write(HTML)
print("✓", OUT)
