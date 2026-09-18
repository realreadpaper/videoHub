#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成《现代婚姻三部曲》逐镜重定时报告（浅色主题 HTML）"""
import json

DATA = json.load(open("/tmp/retime_data.json", encoding="utf-8"))
FPS = 24
DIRS = ["01_周星驰_三十八万八", "02_姜文_老子不娶了", "03_奉俊昊_加名之夜"]

# 逐镜判定依据（与 _后期/retime_shots.py 的 PLAN 表一致）
WHY = {
    "三十八万八": {
        1: "楼梯跟拍 · 双人 + 台词 + 父亲反应，持续运动，三拍点都实",
        2: "静态钢门，主体不动；给满窗后 5s 无指令必漂移",
        3: "婚房双主体 + 岳母发话 + 新娘无视，三段都有事发生",
        4: "手→脸→手三段运动 + 21 字台词，需要空间",
        5: "纯面部特写，单主体撑不满 15s；保留原 30/37/33 非等分节奏",
        6: "跑动 → 上车说台词 → 车开走，三个动作拍点",
        7: "车内固定机位，两人对坐，信息量有限",
        8: "收尾镜，长拉远需要留白，满窗是对的",
    },
    "老子不娶了": {
        1: "下车 + 台词 + 唢呐背景，三拍点",
        2: "27 字全片最长台词 + 抽烟铺垫 + 揭示，撑得住满窗",
        3: "算盘手部微距，三拍点但都很短",
        4: "敲烟锅 + 台词 + 背景嗑瓜子，单一动作",
        5: "砸桌 → 撕单 → 怒吼，三个爆发动作，需要连贯空间",
        6: "走出大院 + 风撕剪纸，两拍点",
        7: "点火 + 台词 + 起步，单一动作",
        8: "收尾镜，戈壁长拉远需要留白",
    },
    "加名之夜": {
        1: "零台词环境镜（溅水→滴桶→桌上文件），满窗后段无指令会漂移",
        2: "26 字长台词 + 滑笔 + 眼神，撑得住满窗",
        3: "喝咖啡 + 台词 + 眼神回避，三拍点",
        4: "沙发缝掏借据，两拍点",
        5: "手部微距三拍点 + 全片最重画面文字诱发项，短窗折中",
        6: "三人同框对峙，需要给三个人各留反应时间",
        7: "收拾走人 + 桶倒水，两拍点",
        8: "收尾镜，雨中走远需要留白",
    },
}

# 档位表
GRID = []
for n in range(13, 23):
    L = 17 * n + 5
    F = ((L - 1) // 8) * 8 + 1
    GRID.append((L, L / FPS, F, F / FPS, L - F))

TIER = {277: "C", 294: "C", 311: "C", 328: "B", 345: "B", 362: "A"}


def esc(x):
    return (str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


rows_html = []
tot_old = tot_new = 0
for d in DIRS:
    v = DATA[d]
    sub = []
    for r in v["rows"]:
        L = r["L"]
        t = TIER.get(L, "?")
        sub.append(f"""      <tr>
        <td class="no">{r['no']}</td>
        <td>{esc(r['framing'])}</td>
        <td class="num">362</td>
        <td class="num">{L}</td>
        <td class="num strong">{r['d']:.3f}</td>
        <td class="num dim">{r['F']}</td>
        <td class="tier t{t}">{t}</td>
        <td class="why">{esc(WHY[v['title']][r['no']])}</td>
      </tr>""")
    tot_old += 8 * 362
    tot_new += sum(r["L"] for r in v["rows"])
    rows_html.append(f"""    <h3>{esc(v['title'])} <span class="sub">／ 8 镜 · 成片 {sum(r['d'] for r in v['rows']):.2f}s</span></h3>
    <table>
      <thead><tr>
        <th>镜</th><th>景别</th><th>旧 H3 帧</th><th>新 H3 帧</th>
        <th>成片秒</th><th>裁后帧</th><th>档</th><th>判定依据</th>
      </tr></thead>
      <tbody>
{chr(10).join(sub)}
      </tbody>
    </table>""")

grid_html = "\n".join(
    f"""        <tr{' class="star"' if loss == 0 else ''}>
          <td class="num">{L}</td><td class="num">{hs:.3f}</td>
          <td class="num">{F}</td><td class="num strong">{fs:.3f}</td>
          <td class="num dim">{loss}</td>
          <td>{'★ 唯一无损档' if loss == 0 else ('地板（未启用）' if fs < 11 else '')}</td>
        </tr>"""
    for L, hs, F, fs, loss in GRID)


def draft(n): return 0.0243 * (n ** 1.362)
def refine(n): return 0.050 * (n ** 1.243)

co = sum(draft(362) + refine(362) for _ in range(24))
cn = sum(draft(r["L"]) + refine(r["L"]) for d in DIRS for r in DATA[d]["rows"])

HTML = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>逐镜重定时结论 · 现代婚姻三部曲</title>
<style>
  :root {{
    --bg:#f7f8fa; --card:#ffffff; --ink:#1c1f23; --ink2:#4a5158; --ink3:#7b848d;
    --line:#e3e7eb; --line2:#eef1f4;
    --red:#c0392b; --green:#1e7a4b; --amber:#a86400; --blue:#1a5fb4;
    --purple:#6b3fa0;
  }}
  * {{ box-sizing:border-box; }}
  body {{
    margin:0; padding:36px 28px 72px;
    background:var(--bg); color:var(--ink);
    font:15px/1.75 -apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
    -webkit-font-smoothing:antialiased;
  }}
  .wrap {{ max-width:1120px; margin:0 auto; }}
  header {{ border-bottom:2px solid var(--ink); padding-bottom:18px; margin-bottom:30px; }}
  h1 {{ font-size:27px; margin:0 0 8px; letter-spacing:-.3px; }}
  .meta {{ color:var(--ink3); font-size:13px; }}
  h2 {{
    font-size:19px; margin:38px 0 14px; padding-left:11px;
    border-left:4px solid var(--ink);
  }}
  h3 {{ font-size:15px; margin:26px 0 10px; color:var(--ink); }}
  h3 .sub {{ font-weight:400; color:var(--ink3); font-size:13px; }}
  p {{ margin:11px 0; color:var(--ink2); }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:20px 22px; margin:16px 0; }}
  .verdict {{ border-left:5px solid var(--green); }}
  .warn {{ border-left:5px solid var(--amber); background:#fffdf6; }}
  .danger {{ border-left:5px solid var(--red); background:#fffafa; }}
  .verdict b, .warn b, .danger b {{ color:var(--ink); }}
  table {{ width:100%; border-collapse:collapse; background:var(--card);
           border:1px solid var(--line); border-radius:8px; overflow:hidden;
           font-size:13.5px; margin:10px 0 4px; }}
  th {{ background:#f0f3f6; text-align:left; padding:9px 11px; font-weight:600;
        color:var(--ink2); font-size:12.5px; border-bottom:1px solid var(--line); white-space:nowrap; }}
  td {{ padding:8px 11px; border-bottom:1px solid var(--line2); color:var(--ink2); vertical-align:top; }}
  tr:last-child td {{ border-bottom:none; }}
  .num {{ text-align:right; font-variant-numeric:tabular-nums;
          font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12.5px; white-space:nowrap; }}
  .strong {{ color:var(--ink); font-weight:600; }}
  .dim {{ color:var(--ink3); }}
  .no {{ text-align:center; font-weight:600; color:var(--ink); width:38px; }}
  .why {{ font-size:12.5px; line-height:1.55; }}
  .tier {{ text-align:center; font-weight:700; width:34px; }}
  .tA {{ color:var(--red); }} .tB {{ color:var(--blue); }} .tC {{ color:var(--green); }}
  tr.star td {{ background:#f2f8f4; }}
  code {{ background:#eef1f4; padding:1px 5px; border-radius:4px;
          font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12.5px; color:#334; }}
  pre {{ background:#f4f6f8; border:1px solid var(--line); border-radius:8px;
         padding:13px 15px; overflow-x:auto; font-size:12.5px; line-height:1.6;
         font-family:ui-monospace,SFMono-Regular,Menlo,monospace; color:var(--ink); margin:12px 0; }}
  .kpi {{ display:flex; gap:14px; flex-wrap:wrap; margin:18px 0; }}
  .kpi div {{ flex:1; min-width:150px; background:var(--card); border:1px solid var(--line);
              border-radius:10px; padding:14px 16px; }}
  .kpi .v {{ font-size:23px; font-weight:700; color:var(--ink); font-variant-numeric:tabular-nums; }}
  .kpi .l {{ font-size:12px; color:var(--ink3); margin-top:3px; }}
  ul {{ margin:10px 0; padding-left:20px; color:var(--ink2); }}
  li {{ margin:6px 0; }}
  .ok {{ color:var(--green); font-weight:600; }}
  .bad {{ color:var(--red); font-weight:600; }}
  .tag {{ display:inline-block; background:#eaf1fb; color:var(--blue);
          border-radius:4px; padding:1px 7px; font-size:11.5px; font-weight:600; margin-right:5px; }}
  .tag.g {{ background:#eaf5ee; color:var(--green); }}
  .tag.r {{ background:#fbeceb; color:var(--red); }}
  footer {{ margin-top:44px; padding-top:16px; border-top:1px solid var(--line);
            color:var(--ink3); font-size:12.5px; }}
</style>
</head>
<body>
<div class="wrap">

<header>
  <h1>逐镜重定时结论 · 《现代婚姻三部曲》24 镜</h1>
  <div class="meta">2026-09-18 · 渲染端 A100-PCIE-40GB (SM 8.0) · H3 两阶段管线 · fps 24</div>
</header>

<div class="card verdict">
  <p style="margin:0"><b>结论：你担心的"强制割裂"是真的，但病根不是 15 秒太长，是"每镜都写死 15 秒"。</b>
  24 镜里只有 <b>6 镜</b>的内容真正撑得住 15 秒，其余 18 镜都在让模型自己编最后那几秒——
  编出来的部分跟下一镜接不上，就是割裂。已按"内容撑多久给多久"重排，
  成片时长落在 <b>11.375s – 15.042s</b>，全部踩在管线双重栅格的合法点上。</p>
</div>

<h2>一、为什么固定 15s 必然割裂</h2>

<p>H3 的工作方式是你给它一个时间窗，再用 prompt 里的三段时间戳告诉它"第 1 段演 A、第 2 段演 B、第 3 段演 C"。
三段写完，窗口还剩时间，模型<b>不会停</b>——它会顺着最后一拍的惯性继续往下演，
演什么由它自己决定。这部分是<b>无指令生成</b>，且每一镜各自编各自的，
剪在一起就是"上一镜的情绪没收住、下一镜的起点对不上"。</p>

<div class="card warn">
  <p style="margin:0"><b>判定规则（本次逐镜用的统一标尺）：</b></p>
  <ul style="margin-bottom:0">
    <li><b>拍点数</b> —— 这一镜有几个可分离的动作/信息拍点。1–2 拍点的镜给满窗，多出来的必然是编的。</li>
    <li><b>台词量</b> —— 按 5 字/秒估，看台词放进对应段落还剩多少呼吸。零台词镜最危险。</li>
    <li><b>主体是否运动</b> —— 纯静态单主体（一张脸、一扇门、一双手）撑不满 15s；持续运动或多人同框才撑得住。</li>
  </ul>
</div>

<h2>二、时长的物理边界：两道栅格叠在一起</h2>

<p>时长不是想填多少就填多少，这条管线上有两道硬栅格，随便写个 13.0 秒会静默变成别的值，字幕轴跟着全错。</p>

<div class="card">
  <p><b>① H3 <code>MiniMaxH3AudioConditioningT8.length</code></b><br>
  <code>min=5, step=17</code>，tooltip 原文 <i>"24fps; snapped up to the 17n+5 H3 grid"</i>
  → 合法值只能是 <code>5, 22, 39, …, 328, 345, 362</code>（即 17n+5）。填写值会被<b>向上吸附</b>到最近档。</p>
  <p style="margin-bottom:0"><b>② LTX Stage2 <code>MiniMaxH3SolEngineDraftToLTXT8Advanced.frame_policy</code></b><br>
  默认 <code>trim_to_8n_plus_1</code>（已在服务器 <code>/object_info</code> 上核实）：
  只裁不补，把 ① 的帧数<b>向下</b>取到最近的 8m+1。</p>
</div>

<table>
  <thead><tr>
    <th>H3 帧（17n+5）</th><th>H3 秒</th><th>成片帧（8m+1）</th>
    <th>成片秒</th><th>裁掉</th><th>备注</th>
  </tr></thead>
  <tbody>
{grid_html}
  </tbody>
</table>

<p class="dim" style="font-size:13px">10–15 秒区间内只有上面这 8 档可用。
其中 <b>345 帧（14.375s）</b>是唯一"双对齐无损"档——H3 输出 345 帧，LTX 裁完还是 345 帧，一帧不丢。
其余各档都要被裁掉 1–7 帧（0.042–0.292s），剪辑无感，但字幕轴必须按<b>裁后</b>的成片时长算。</p>

<h2>三、24 镜新排期</h2>

<p>档位含义：<span class="tag r">A</span>满窗 15.042s（内容撑得住）
<span class="tag">B</span>13.375 / 14.375s（接近满窗）
<span class="tag g">C</span>11.375 – 12.708s（主体单一，给满窗会编）</p>

{chr(10).join(rows_html)}

<h2>四、边界条件怎么保证稳定</h2>

<p>三道防线，缺一不可。前两道是<b>写的时候</b>拦，第三道是<b>跑完之后</b>拦。</p>

<div class="card">
  <p><b>① 只能取档位值，不许填任意秒数</b><br>
  排期直接写死在 <code>_后期/retime_shots.py</code> 的 <code>PLAN</code> 表里，
  值只能是 <code>17n+5</code> 的帧数。填 <code>13.0</code> 这种数会被 H3 吸附到 328（13.667s）、
  再被 LTX 裁到 321（13.375s）——你以为的 13.0 实际是 13.375。</p>

  <p><b>② 写回前跑硬校验，不合规直接退出码 2</b><br>
  <code>audit()</code> 逐镜检查四项，任何一项不过就整体失败、<b>一个字都不写</b>：</p>
  <ul>
    <li><code>h3_length</code> 必须 ∈ 17n+5</li>
    <li><code>duration_frames</code> 必须等于 <code>trim_to_8n_plus_1(h3_length)</code></li>
    <li>成片秒数必须 ∈ [10.0, 15.05]</li>
    <li>prompt 三段时间戳必须严格递增，且末段终点 == H3 全长</li>
  </ul>
  <p style="margin-bottom:0">本次执行结果：<span class="ok">✔ 边界校验通过：全部 24 镜 h3_length ∈ 17n+5、成片时长 ∈ [10.0, 15.05]s、时间戳覆盖到 H3 全长</span></p>
</div>

<div class="card">
  <p style="margin-bottom:0"><b>③ 字幕时间轴按 ffprobe 实测累加，不按 manifest 推算</b><br>
  <code>_后期/make_subs.py</code> 的口径一直是：字幕绝对时间 = <b>Σ 前序镜 ffprobe 实测时长</b> + 镜内时间窗。
  这次把兜底值从写死的 <code>15.04</code> 改成 manifest 的逐镜 <code>duration</code>，
  这样即使某镜底片还没拉回来，误差也只是那一镜的 0.29s 上限，不会 24 镜累积成 7 秒。</p>
</div>

<h2>五、代价与收益</h2>

<div class="kpi">
  <div><div class="v">{tot_old} → {tot_new}</div><div class="l">H3 生成总帧（−{100*(tot_old-tot_new)/tot_old:.1f}%）</div></div>
  <div><div class="v">361.0 → 320.0</div><div class="l">三部曲成片总秒数</div></div>
  <div><div class="v">{co/60:.1f} → {cn/60:.1f} min</div><div class="l">A100 热态机时（−{100*(co-cn)/co:.1f}%）</div></div>
  <div><div class="v">{(co-cn)/3600*2.60:.2f} 元</div><div class="l">按 2.60 元/卡时省下</div></div>
</div>

<p class="dim" style="font-size:13px">机时按 A100 热态批处理口径估算（草稿 <code>0.0243·n^1.362</code> + 精修 <code>0.050·n^1.243</code> 秒，n 为帧数），
不含冷启与权重装卸。省机时是<b>副产品</b>，不是目的——真正的好处是 18 个镜不再有"模型自己编的尾巴"。</p>

<h2>六、改了哪些文件</h2>

<table>
  <thead><tr><th>文件</th><th>改动</th><th>验证</th></tr></thead>
  <tbody>
    <tr><td><code>_后期/retime_shots.py</code></td>
        <td>新增（可复现重定时 + 硬校验）</td>
        <td><code>python3 _后期/retime_shots.py --also-locked</code></td></tr>
    <tr><td><code>0*/manifest.json</code></td>
        <td>逐镜写入 <code>h3_length</code> / <code>duration</code> / <code>duration_frames</code>，三段时间戳按新时长重排</td>
        <td>备份在 <code>manifest.json.orig_retime</code></td></tr>
    <tr><td><code>0*/manifest.identity_locked.json</code></td>
        <td>同上（身份补丁版同步重定时，避免两套 manifest 打架）</td>
        <td>备份在 <code>manifest.identity_locked.json.orig_retime</code></td></tr>
    <tr><td><code>0*/10_run_film.py</code></td>
        <td><code>H3_LENGTH</code> 降级为缺省值；<code>stage1_draft()</code> 改读 <code>shot["h3_length"]</code> 并传给 <code>6.length</code>；汇总行改显示区间</td>
        <td><code>python3 -m py_compile</code> 三份均通过</td></tr>
    <tr><td><code>_后期/make_subs.py</code></td>
        <td>兜底时长 15.04 → manifest 逐镜 <code>duration</code></td>
        <td><code>python3 -m py_compile</code> 通过</td></tr>
  </tbody>
</table>

<h2>七、还没解决、且比时长更靠前的问题</h2>

<div class="card danger">
  <p style="margin-top:0"><b>重定时只治了"割裂"这一种病。上一轮审核出的四个硬伤仍然挂在这里，且优先级都在时长之上：</b></p>
  <ul>
    <li><span class="bad">跑不起来</span> —— <code>10_run_film.py</code> 依赖的 <code>/workspace/h3scripts/80_run_workflow_remote.py</code> 在 A100 上<b>全盘不存在</b>，第一镜就会崩。</li>
    <li><span class="bad">显存不够</span> —— ComfyUI 常驻已占 29.5 / 40 GB，剩 10 GB，单套权重就要 21 GB。</li>
    <li><span class="bad">换脸</span> —— Stage2 走官方 Sigma 0.91 起步 = 把刚锁定的脸用 91% 噪声重画；保脸版工作流（0.5 起步）在服务器上现成，<b>换掉零成本</b>。</li>
    <li><span class="bad">画面乱码</span> —— 12 镜要求画面长出文字，其中片3镜5 是微距 + 明确数字 + 手写体，用满屏像素写模型最不会写的东西；每镜结尾又写着 <code>no on-screen text</code>，两条互斥指令。</li>
  </ul>
  <p style="margin-bottom:0">另外 <code>manifest.identity_locked.json</code> 的身份补丁<b>根本没被加载</b>
  ——<code>10_run_film.py</code> 第 48 行读的是 <code>manifest.json</code>。</p>
</div>

<footer>
  重定时口径与校验逻辑全部落在 <code>_后期/retime_shots.py</code>，可重复执行；
  原始 manifest 已备份为 <code>*.orig_retime</code>，随时 <code>cp</code> 回来。
</footer>

</div>
</body>
</html>
"""

open("/Users/hejianglong/Desktop/story/待生成_现代婚姻三部曲/01_重定时结论_20260918.html", "w", encoding="utf-8").write(HTML)
print("written", len(HTML))
