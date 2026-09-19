#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
试拍回收 + 审查页：把服务器上的复刻成片压成低带宽预览拉回本机，
和「同一时间窗的原片片段」并排放在一个 HTML 里做对照。

用法:  python3 collect_pilot.py
产物:  pilot/out/{orig,preview,stills}/... + pilot/out/审查页.html
"""
import html
import json
import os
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
PILOT = os.path.join(HERE, "pilot")
OUT = os.path.join(PILOT, "out")
BASE = os.path.dirname(HERE)                 # .../2026-09-19
KEY = "kehu"

REVIEW_TITLE = "试拍 4 镜 · 原片 vs 复刻 对照"


def run(cmd, check=True):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError("FAILED: %s\n%s" % (" ".join(cmd), r.stderr[-600:]))
    return r


def main():
    man = json.load(open(os.path.join(PILOT, "pilot.json")))
    DUR = man["duration"]
    os.makedirs(os.path.join(OUT, "orig"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "preview"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "stills"), exist_ok=True)

    keys = [s["key"] for s in man["shots"]]

    # ---------- 1. 本机切原片段（同一时间起点、同一时长）----------
    for s in man["shots"]:
        dst = os.path.join(OUT, "orig", s["key"] + ".mp4")
        run(["ffmpeg", "-y", "-loglevel", "error",
             "-ss", "%.3f" % s["t_start"], "-t", "%.3f" % DUR,
             "-i", os.path.join(BASE, s["video"] + ".mp4"),
             "-vf", "scale=384:-2", "-c:v", "libx264", "-crf", "30",
             "-preset", "veryfast", "-an", "-movflags", "+faststart", dst])
    print("[1/4] 原片片段 %d 条" % len(keys))

    # ---------- 2. 服务器端压复刻预览 ----------
    lst = " ".join("dy4_pilot/%s_00001_.mp4" % k for k in keys)
    script = (
        "cd /workspace/ComfyUI/output && "
        "for f in %s; do b=$(basename \"$f\" _00001_.mp4); "
        "[ -f \"$f\" ] || { echo \"MISS $f\"; continue; }; "
        "ffmpeg -y -loglevel error -i \"$f\" -vf scale=384:-2 "
        "-c:v libx264 -crf 30 -preset veryfast -c:a aac -b:a 48k "
        "-movflags +faststart /tmp/prev_${b}.mp4; "
        "ffmpeg -y -loglevel error -i \"$f\" -vf \"fps=1/1.5,scale=560:-2\" -q:v 3 "
        "/tmp/hi_${b}_%%02d.jpg; echo \"OK $b\"; done" % lst)
    r = run(["ssh", KEY, script], check=False)
    print("[2/4] 服务器压缩：")
    for ln in (r.stdout + r.stderr).splitlines():
        if ln.strip():
            print("      " + ln)

    # ---------- 3. 拉回本机 ----------
    run(["scp", "-q", "%s:/tmp/prev_*.mp4" % KEY, os.path.join(OUT, "preview") + "/"], check=False)
    run(["scp", "-q", "%s:/tmp/hi_*.jpg" % KEY, os.path.join(OUT, "stills") + "/"], check=False)
    got = sorted(os.listdir(os.path.join(OUT, "preview")))
    print("[3/4] 拉回预览 %d 个，静帧 %d 个"
          % (len(got), len(os.listdir(os.path.join(OUT, "stills")))))

    # ---------- 4. 生成对照页 ----------
    rows = []
    for s in man["shots"]:
        k = s["key"]
        prev = os.path.join(OUT, "preview", k + "_00001_.mp4")
        has = os.path.exists(prev)
        stills = sorted(f for f in os.listdir(os.path.join(OUT, "stills"))
                        if f.startswith("hi_" + k + "_"))
        beats = "".join(
            "<li><b>%s</b> · %s ｜ <span class='q'>%s</span></li>"
            % (html.escape(b.get("role", "")), html.escape(b.get("cam", "")),
               html.escape(b.get("text", "")))
            for b in s.get("beats", []))
        rows.append("""
<section class="shot">
  <h2>%s <span class="tag %s">%s</span> <span class="meta">%.2f–%.2fs · 源镜 %s · 语音 %.2fs + 补白 %.2fs</span></h2>
  <p class="line">「%s」</p>
  <div class="pair">
    <div><div class="cap">原片（同一时间窗 %.3fs）</div>
      <video autoplay loop muted playsinline src="orig/%s.mp4"></video></div>
    <div><div class="cap">复刻（107 帧 / 8 步 / %s）</div>
      %s</div>
  </div>
  <details><summary>拍点设计（%d 个）</summary><ul class="beats">%s</ul></details>
  %s
</section>""" % (
            html.escape(k), "plot" if s["kind"] == "剧情" else "prod", s["kind"],
            s["t_start"], s["t_end"], s["src_shots"], s["voice_dur"], s["pad_tail"],
            html.escape(s["dialogue"]),
            DUR, k,
            "ref 身份参考 + first 首帧 + last 末帧" if has else "（未回收到）",
            '<video autoplay loop muted playsinline src="preview/%s_00001_.mp4"></video>'
            % k if has else '<div class="miss">成片未回收到</div>',
            len(s.get("beats", [])), beats,
            ('<div class="stills">%s</div>' % "".join(
                '<img src="stills/%s">' % f for f in stills)) if stills else ""))

    doc = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%s</title>
<style>
:root{--bg:#f7f6f3;--panel:#fff;--ink:#1f1e1c;--dim:#6b6862;--line:#e2e0da;
--plot:#2f6fb5;--prod:#c0392b;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.6 -apple-system,"PingFang SC","Helvetica Neue",sans-serif;}
header{padding:26px 28px 18px;border-bottom:1px solid var(--line);background:var(--panel)}
h1{margin:0 0 6px;font-size:21px;letter-spacing:.3px}
header p{margin:0;color:var(--dim);font-size:13px}
main{padding:20px 28px 60px;max-width:1120px;margin:0 auto}
.shot{background:var(--panel);border:1px solid var(--line);border-radius:10px;
padding:16px 18px 14px;margin-bottom:20px}
.shot h2{margin:0 0 4px;font-size:16px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.tag{font-size:11px;padding:1px 8px;border-radius:9px;color:#fff;font-weight:600}
.tag.plot{background:var(--plot)} .tag.prod{background:var(--prod)}
.meta{color:var(--dim);font-weight:400;font-size:12px}
.line{margin:2px 0 12px;color:var(--dim);font-size:13px}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.cap{font-size:12px;color:var(--dim);margin-bottom:5px}
video{width:100%%;border-radius:7px;background:#000;display:block}
.miss{padding:40px 10px;text-align:center;color:var(--dim);border:1px dashed var(--line);border-radius:7px}
details{margin-top:11px;font-size:13px}
summary{cursor:pointer;color:var(--dim)}
ul.beats{margin:7px 0 0;padding-left:18px}
ul.beats li{margin:2px 0}
.q{color:#3b6b4a}
.stills{display:flex;gap:7px;margin-top:10px;overflow-x:auto}
.stills img{height:112px;border-radius:5px;flex:0 0 auto}
@media(max-width:720px){.pair{grid-template-columns:1fr}}
</style></head><body>
<header><h1>%s</h1>
<p>每条片各 1 剧情镜 + 1 产品镜 · 统一 107 帧 / 4.458s · 8 步 · Hybrid（ref + first + last 三图）·
干声取自原片直切 · 排 768×1344</p></header>
<main>%s</main></body></html>""" % (REVIEW_TITLE, REVIEW_TITLE, "".join(rows))

    p = os.path.join(OUT, "审查页.html")
    open(p, "w", encoding="utf-8").write(doc)
    print("[4/4] 审查页 → %s" % p)


if __name__ == "__main__":
    main()
