#!/usr/bin/env python3
# -*- coding: utf-8 -*- """生成分镜确认表 HTML（浅色主题）。"""
import json, os, html
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIRS = [("01_周星驰_三十八万八","f1","周星驰 · 市井荒诞"),
        ("02_姜文_老子不娶了","f2","姜文 · 雄性荷尔蒙"),
        ("03_奉俊昊_加名之夜","f3","奉俊昊 · 阴冷悬疑")]
PILOT = {"f1s02":"道具/产品镜","f2s05":"情感转折镜","f3s06":"对话镜（三人同框）"}
TEXT_RISK = {("f1",1),("f1",2),("f2",2),("f3",1),("f3",2),("f3",4),("f3",5)}

rows = []
for d, fk, style in DIRS:
    man = json.load(open(os.path.join(ROOT, d, "manifest.json"), encoding="utf-8"))
    for s in man["shots"]:
        k = "%ss%02d" % (fk, s["no"])
        risk = []
        if (fk, s["no"]) in TEXT_RISK: risk.append("文字道具（已降为不可辨）")
        if not (s.get("dialogue_cn") or "").strip(): risk.append("零台词·纯环境")
        if s["no"] == 6 and fk == "f3": risk.append("三人同框·一致性最难")
        if s["h3_length"] == 362: risk.append("满窗 15.042s")
        rows.append(dict(k=k, no=s["no"], fk=fk, style=style, title=man["film_title"],
                         framing=s["framing"], dur=s["duration"], L=s["h3_length"],
                         char=s["character"], dlg=(s.get("dialogue_cn") or "").strip(),
                         pilot=PILOT.get(k, ""), risk=risk))

def esc(x): return html.escape(str(x))
tr = []
cur = None
for r in rows:
    if r["fk"] != cur:
        cur = r["fk"]
        tr.append('<tr class="filmhead"><td colspan="8">%s &nbsp;·&nbsp; %s &nbsp;·&nbsp; 共 8 镜</td></tr>'
                  % (esc(r["title"]), esc(r["style"])))
    pilot = '<span class="pilot">★ 试拍 · %s</span>' % esc(r["pilot"]) if r["pilot"] else ""
    risk = "".join('<span class="rk">%s</span>' % esc(x) for x in r["risk"]) or '<span class="ok">—</span>'
    dlg = esc(r["dlg"]) if r["dlg"] else '<span class="mute">（无台词）</span>'
    tr.append(
        '<tr><td class="c">%s</td><td class="c b">%02d</td><td>%s</td>'
        '<td class="c">%.3fs</td><td class="c">%d</td><td>%s</td><td>%s</td><td>%s</td></tr>'
        % (r["k"], r["no"], esc(r["framing"]), r["dur"], r["L"], esc(r["char"]), dlg,
           (pilot + risk) if r["pilot"] else risk))

HTML = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>现代婚姻三部曲 · 分镜确认表</title><style>
:root{--bg:#f7f8fa;--card:#fff;--line:#e3e6ea;--tx:#1f2328;--tx2:#5b6570;--acc:#c0392b;--acc2:#1e6fbf;}
*{box-sizing:border-box}
body{margin:0;padding:32px 28px;background:var(--bg);color:var(--tx);
 font:14px/1.65 -apple-system,"PingFang SC","Helvetica Neue",Arial,sans-serif;}
.wrap{max-width:1280px;margin:0 auto}
h1{font-size:24px;margin:0 0 6px}
.sub{color:var(--tx2);margin:0 0 22px;font-size:13px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:20px;margin-bottom:18px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{background:#eef1f4;text-align:left;padding:9px 10px;font-weight:600;border-bottom:2px solid var(--line);white-space:nowrap}
td{padding:9px 10px;border-bottom:1px solid #f0f2f4;vertical-align:top}
tr:hover td{background:#fafbfc}
.filmhead td{background:linear-gradient(90deg,#fff5f4,#fff);font-weight:700;font-size:14px;
 padding:12px 10px;border-left:4px solid var(--acc);color:var(--acc)}
.c{text-align:center;white-space:nowrap}
.b{font-weight:700;font-size:15px}
.mute{color:#9aa3ad}
.pilot{display:inline-block;background:var(--acc);color:#fff;padding:1px 8px;border-radius:4px;
 font-size:12px;font-weight:600;margin-right:6px}
.rk{display:inline-block;background:#fff3e0;color:#a05a00;border:1px solid #f0d9b5;
 padding:1px 7px;border-radius:4px;font-size:12px;margin:1px 3px 1px 0}
.ok{color:#9aa3ad}
.note{background:#fffdf5;border:1px solid #f0e3b8;border-radius:8px;padding:14px 16px;font-size:13px}
.note b{color:#8a6d00}
code{background:#f2f4f6;padding:1px 5px;border-radius:3px;font-size:12px}
</style></head><body><div class="wrap">
<h1>现代婚姻三部曲 · 分镜确认表</h1>
<p class="sub">生成于 2026-09-18 · 24 镜 · 用于开拍前确认（SOP 第①步）· 时长已按 17n+5 / 8n+1 双重栅格锁定</p>
<div class="card"><table>
<tr><th>Key</th><th>镜</th><th>景别 / 内容</th><th>成片时长</th><th>H3帧</th><th>角色</th><th>台词</th><th>试拍 / 风险</th></tr>
__ROWS__
</table></div>
<div class="note">
<b>说明</b><br>
· <b>成片时长</b> = H3 帧经 LTX <code>trim_to_8n_plus_1</code> 裁剪后的实际秒数，<b>不等于</b> H3 帧数÷24。字幕轴必须按成片时长算。<br>
· <b>试拍 3 镜</b>（★）已按 SOP 第②步挑定，原则是挑<b>最难</b>的不是最好看的：
  <code>f1s02</code> 道具特写+推近读字（禁字最难）、<code>f2s05</code> 情感转折点、<code>f3s06</code> 三人同框对话（一致性最难）。<br>
· <b>文字道具</b> 7 镜已按"不保证可读"降级为"字迹不可辨"，同时每镜末尾注入 <code>strict_output_constraints</code> 强制禁字段。<br>
· <b>零台词</b> 3 镜（f3s01 / f3s05 / f3s07）使用等长静音轨锁定窗口，不触发 H3 自配音。
</div></div></body></html>"""
HTML = HTML.replace("__ROWS__", "\n".join(tr))

out = os.path.join(ROOT, "01_分镜确认表_20260918.html")
open(out, "w", encoding="utf-8").write(HTML)
print("已生成:", out, "共 %d 镜" % len(rows))
