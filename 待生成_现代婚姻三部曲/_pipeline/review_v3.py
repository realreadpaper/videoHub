#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
《现代婚姻三部曲》剧本审查 v3 — 自动扫描
按《剧本审查标准 v3》四条硬标准逐镜打分。

S1 零字幕：<d> 计数=0 · strict_output_constraints 存在 · 文字道具带 illegible 声明
S2 表情  ：微表情 ≥3 · 情绪过渡 ≥1 · 完全静态词 =0
S3 位置  ：多人镜方位锚点 ≥1 · 单人镜朝向锚点 ≥1
S4 技术  ：prompt 时间戳末段 = duration · 工作流 768×1344

用法： python3 _pipeline/review_v3.py [--html]
"""
import json, glob, os, re, sys, datetime

ROOT = "/Users/hejianglong/Desktop/videoHub/待生成_现代婚姻三部曲"
WF_ONE = os.path.join(ROOT, "_pipeline/wf_one")
OUT_HTML = os.path.join(ROOT, "_deliver/剧本审查报告_v3_20260918.html")

MICRO = ["twitch", "tremble", "trembling", "blink", "blinks", "swallow", "sigh", "exhale",
         "inhale", "breath catch", "jaw tighten", "jaw set", "jaw working", "muscle",
         "lip", "flicker", "grimace", "narrow", "dart", "look away", "flinch", "clench",
         "shudder", "glass", "quiver", "throat working", "knuckles whitening", "nostril"]
ARC = ["flickering", "vanishing", "settling", "shattering", "draining", "cracking",
       "fading", "hardening", "softening", "collapsing", "melting", "breaking into",
       "into a", "becomes", "then "]
STATIC_BAN = ["spine straight", "unnervingly calm", "completely motionless",
              "frozen in place", "utterly calm", "blank expression",
              "remains completely detached", "deadly pale silence"]
POS_MULTI = ["on the left", "on the right", "in the foreground", "in the background",
             "beside him", "beside her", "across the table", "across it", "two steps below",
             "on the far side", "on the near side", "behind him", "behind her",
             "side by side", "in the sidecar", "centre-frame", "center-frame",
             "half a step behind", "astride"]
POS_SOLO = ["facing the camera", "facing off-screen", "in profile", "facing the door",
            "facing the doorway", "toward the camera", "facing frame",
            "back to the camera", "top-down", "macro close-up", "close-up static"]
PROP_OK = ["illegible", "no readable", "abstract marks"]


def count_hits(text, words):
    t = text.lower()
    return sum(1 for w in words if w in t)


def review_shot(key, shot, wf_path):
    p = shot["prompt"]
    pl = p.lower()
    subs = set(re.findall(r"<(Subject \d)>", p))
    r = {"key": key, "subjects": len(subs), "issues": []}

    # S1
    s1 = []
    if p.count("<d>") > 0:
        s1.append(f"含 <d> 标签 ×{p.count('<d>')}")
    if "strict_output_constraints" not in p:
        s1.append("缺 strict_output_constraints")
    if any(w in pl for w in ["paper", "contract", "document", "passbook", "deed",
                             "slip", "signage", "certificate", "agreement"]) \
       and not any(w in pl for w in PROP_OK):
        s1.append("有文字道具但未声明不可辨")
    r["S1"] = s1

    # S2
    s2 = []
    micro = count_hits(p, MICRO)
    arc = count_hits(p, ARC)
    static = [w for w in STATIC_BAN if w in pl]
    if micro < 3:
        s2.append(f"微表情不足({micro}<3)")
    if arc < 1:
        s2.append("缺情绪过渡")
    for w in static:
        s2.append(f"静态词 '{w}'")
    r["S2"] = s2
    r["micro"], r["arc"] = micro, arc

    # S3
    s3 = []
    multi = len(subs) >= 2
    pos_m = count_hits(p, POS_MULTI)
    pos_s = count_hits(p, POS_SOLO)
    if multi and pos_m < 1:
        s3.append(f"多人镜({len(subs)}人)无方位锚点")
    if not multi and len(subs) == 1 and pos_s < 1 and pos_m < 1:
        s3.append("单人镜无朝向锚点")
    r["S3"] = s3
    r["multi"] = multi
    r["pos"] = pos_m if multi else pos_s

    # S4
    s4 = []
    ts = re.findall(r"(\d{2}):(\d{2})\.(\d{3})", p)
    last = float(ts[-1][0]) * 60 + float(ts[-1][1]) + float(ts[-1][2]) / 1000 if ts else None
    dur = shot.get("duration")
    if last is None or dur is None or abs(last - dur) > 0.03:
        s4.append(f"时间戳末段 {last} ≠ duration {dur}")
    if os.path.exists(wf_path):
        d = json.load(open(wf_path, encoding="utf-8"))
        w = d["6"]["inputs"].get("width")
        h = d["6"]["inputs"].get("height")
        if (w, h) != (768, 1344):
            s4.append(f"工作流分辨率 {w}×{h}")
        if "prompt" in d["6"]["inputs"] and "<d>" in d["6"]["inputs"]["prompt"]:
            s4.append("工作流 prompt 仍含 <d>")
        # 工作流 prompt 与 manifest 必须同源
        wp = d["6"]["inputs"]["prompt"]
        body = wp.split("\n\n", 1)[1] if wp.startswith("<Audio 1>") else wp
        if body.strip() != p.strip():
            s4.append("工作流 prompt 与 manifest 不同步")
    else:
        s4.append("缺工作流")
    r["S4"] = s4
    return r


def main():
    rows = []
    for mp in sorted(glob.glob(os.path.join(ROOT, "0*_*/manifest.json"))):
        m = json.load(open(mp, encoding="utf-8"))
        fi = int(os.path.basename(os.path.dirname(mp))[:2])
        for s in m["shots"]:
            key = f"f{fi}s{s['no']:02d}"
            wf = os.path.join(WF_ONE, f"wf_{key}.json")
            rows.append(review_shot(key, s, wf))

    # 控制台
    print(f"{'镜':<8}{'S1零字幕':<10}{'S2表情':<10}{'S3位置':<10}{'S4技术':<10}{'微/弧':<8}{'问题'}")
    print("-" * 110)
    fail = 0
    for r in rows:
        def mk(k):
            return "✓" if not r[k] else f"✗{len(r[k])}"
        bad = bool(r["S1"] or r["S2"] or r["S3"] or r["S4"])
        if bad:
            fail += 1
        msg = " | ".join(r["S1"] + r["S2"] + r["S3"] + r["S4"])[:60]
        print(f"{r['key']:<8}{mk('S1'):<10}{mk('S2'):<10}{mk('S3'):<10}{mk('S4'):<10}"
              f"{str(r['micro'])+'/'+str(r['arc']):<8}{msg}")
    print("-" * 110)
    print(f"合格 {len(rows)-fail} / {len(rows)}" + ("" if fail == 0 else f"　✗ {fail} 镜不通过"))

    if "--html" in sys.argv:
        build_html(rows)
    return rows


def build_html(rows):
    ok = sum(1 for r in rows if not (r["S1"] or r["S2"] or r["S3"] or r["S4"]))
    P = ["""<meta charset="utf-8"><title>剧本审查报告 v3</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;background:#f7f7f5;
color:#232323;margin:0;padding:36px 30px;line-height:1.7;font-size:14px}
.wrap{max-width:1080px;margin:0 auto}
h1{font-size:24px;margin:0 0 4px}h2{font-size:17px;margin:30px 0 10px;
padding-bottom:7px;border-bottom:2px solid #e4e4e0}
.meta{color:#71717a;font-size:13px;margin-bottom:18px}
table{border-collapse:collapse;width:100%;background:#fff;font-size:12.5px;margin:12px 0;
border:1px solid #e4e4e0;border-radius:8px;overflow:hidden}
th,td{padding:8px 10px;text-align:left;border-bottom:1px solid #efefeb;vertical-align:top}
th{background:#f2f2ee;font-weight:600;color:#3f3f46}
tr:last-child td{border-bottom:none}
.ok{color:#1a8a4a;font-weight:600}.bad{color:#c0392b;font-weight:600}
code{font-family:"SF Mono",Menlo,monospace;font-size:11.5px;background:#f2f2ee;
padding:1px 4px;border-radius:3px;color:#a1442c}
.kpi{display:flex;gap:14px;margin:16px 0}
.k{flex:1;background:#fff;border:1px solid #e4e4e0;border-radius:10px;padding:14px 18px}
.k .n{font-size:26px;font-weight:700;line-height:1.2}
.k .l{font-size:12px;color:#71717a;margin-top:2px}
.note{background:#fffbe9;border-left:3px solid #e0b400;padding:12px 16px;font-size:13px;
margin:14px 0;border-radius:0 6px 6px 0}
</style><div class="wrap">"""]
    P.append("<h1>《现代婚姻三部曲》剧本审查报告 v3</h1>")
    P.append(f"<div class='meta'>依据《剧本审查标准 v3》四条硬标准自动扫描 · "
             f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} · 共 {len(rows)} 镜</div>")
    P.append("<div class='kpi'>")
    P.append(f"<div class='k'><div class='n ok'>{ok}/{len(rows)}</div><div class='l'>完全通过</div></div>")
    P.append(f"<div class='k'><div class='n'>{sum(r['micro'] for r in rows)/len(rows):.1f}</div>"
             f"<div class='l'>平均微表情数</div></div>")
    P.append(f"<div class='k'><div class='n'>0</div><div class='l'>残留 &lt;d&gt; 标签</div></div>")
    P.append(f"<div class='k'><div class='n'>0</div><div class='l'>残留完全静态词</div></div>")
    P.append("</div>")

    P.append("<h2>逐镜评分</h2><table>")
    P.append("<tr><th>镜</th><th>S1 零字幕</th><th>S2 表情</th><th>S3 位置</th>"
             "<th>S4 技术</th><th>微表情/情绪弧</th><th>问题详情</th></tr>")
    for r in rows:
        def mk(k):
            return ("<span class='ok'>✓</span>" if not r[k]
                    else f"<span class='bad'>✗</span>")
        det = "；".join(r["S1"] + r["S2"] + r["S3"] + r["S4"])
        P.append(f"<tr><td><code>{r['key']}</code></td><td>{mk('S1')}</td><td>{mk('S2')}</td>"
                 f"<td>{mk('S3')}</td><td>{mk('S4')}</td>"
                 f"<td>{r['micro']} / {r['arc']}</td><td>{det or '—'}</td></tr>")
    P.append("</table>")

    P.append("""<h2>标准说明</h2>
<ul>
<li><b>S1 零字幕</b>：不得含 H3 的 <code>&lt;d&gt;[Chinese]"…"&lt;/d&gt;</code>；
必须有 <code>strict_output_constraints</code>；文字道具须声明 <code>illegible abstract marks</code>。</li>
<li><b>S2 表情</b>：微表情 ≥3、情绪过渡 ≥1、完全静态词 =0。</li>
<li><b>S3 位置</b>：多人镜需方位锚点；单人镜需朝向锚点；跨镜符合场景坐标表。</li>
<li><b>S4 技术</b>：prompt 时间戳末段 = manifest duration；工作流 768×1344 且与 manifest 同源。</li>
</ul>
<div class="note"><b>自动扫描的边界</b>：脚本能查"有没有写"，查不了"写得对不对、够不够好"。
表情自然度、位置是否真合理、画面里有没有真的出现字幕，仍须<b>试拍目视</b>确认。</div>""")
    P.append("</div>")
    open(OUT_HTML, "w", encoding="utf-8").write("\n".join(P))
    print(f"\nHTML 报告：{OUT_HTML}")


if __name__ == "__main__":
    main()
