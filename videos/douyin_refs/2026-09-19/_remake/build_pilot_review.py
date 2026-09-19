#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成试拍审查页（HTML）：原片 vs 复刻并排 + 输入三图 + 静帧可点开 + 客观指标表。

用法: <带 PIL+numpy 的 python> build_pilot_review.py
读  : pilot/pilot.json, pilot/out/{orig,preview,stills}, pilot/{ref,first,last}
写  : pilot/out/审查页.html
"""
import html
import json
import os
import subprocess

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
PILOT = os.path.join(HERE, "pilot")
OUT = os.path.join(PILOT, "out")
BASE = os.path.dirname(HERE)
PROD_SRC = os.path.normpath(os.path.join(BASE, "..", "..", "..",
                                         "C9D9F4F4735AD97DE259A3A3A0B02009.jpg"))
SZ = (96, 168)


def gray(a):
    return a @ np.array([0.299, 0.587, 0.114], dtype=np.float32)


_TMPD = os.path.join(OUT, "_rtmp")


def frame_at(src, t, sz=(560, 980)):
    """抽单帧 —— 走临时文件，比 pipe 稳（ffmpeg 无扩展名时 image2 会失败）。"""
    os.makedirs(_TMPD, exist_ok=True)
    dst = os.path.join(_TMPD, "t.jpg")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "%.4f" % t, "-i", src,
                    "-frames:v", "1", "-vf", "scale=%d:%d" % sz, "-q:v", "3", dst],
                   check=True, capture_output=True)
    return np.asarray(Image.open(dst).convert("RGB"), dtype=np.float32)


def metrics(man):
    """和 probe_pilot.py 同一套口径，供页面展示。"""
    out = {}
    for s in man["shots"]:
        k = s["key"]
        mp4 = os.path.join(OUT, "preview", "prev_%s.mp4" % k)
        if not os.path.exists(mp4):
            continue
        D = man["duration"]
        f0 = frame_at(mp4, 0.0, SZ)
        g0 = np.asarray(Image.open(os.path.join(PILOT, "first", k + ".jpg"))
                        .convert("RGB").resize(SZ), dtype=np.float32)
        lock = float(np.abs(gray(f0) - gray(g0)).mean())
        fs = [frame_at(mp4, t, SZ) for t in (0.3, 1.5, 2.7, 3.9)]
        mv = [float(np.abs(gray(fs[i]) - gray(fs[i - 1])).mean()) for i in range(1, 4)]
        f44 = frame_at(mp4, D - 0.18, SZ)
        tail = float(np.abs(gray(f44) - gray(fs[-1])).mean())
        r, g, b = f0[..., 0], f0[..., 1], f0[..., 2]
        mid = frame_at(mp4, D * 0.5, SZ)
        r2, g2, b2 = mid[..., 0], mid[..., 1], mid[..., 2]
        redf = float(((r > 85) & (r < 215) & (g < 95) & (b < 95) & (r > g * 1.75) & (r > b * 1.6)).mean())
        redm = float(((r2 > 85) & (r2 < 215) & (g2 < 95) & (b2 < 95) & (r2 > g2 * 1.75) & (r2 > b2 * 1.6)).mean())
        out[k] = {"lock": lock, "mv": mv, "tail": tail, "red": max(redf, redm)}
    return out


def main():
    man = json.load(open(os.path.join(PILOT, "pilot.json")))
    D = man["duration"]
    M = metrics(man)

    rows = []
    for s in man["shots"]:
        k = s["key"]
        m = M.get(k)
        prev = os.path.join(OUT, "preview", "prev_%s.mp4" % k)
        stills = sorted(f for f in os.listdir(os.path.join(OUT, "stills"))
                        if f.startswith("hi_" + k + "_"))
        beats = "".join(
            "<li><span class='t'>%s</span> <b>%s</b> ｜ %s</li>"
            % (html.escape(b.get("t", "")), html.escape(b.get("role", "")),
               html.escape(b.get("cam", "")))
            for b in s.get("beats", []))
        mrow = ""
        if m:
            mrow = """<table class="mx">
<tr><th>首帧是否贴合 first_frame</th><th>段内运动量（0.3/1.5/2.7/3.9s）</th>
<th>末尾 0.5s 是否僵住</th><th>深红像素占比</th></tr>
<tr><td>MAE %(lock).1f %(lockv)s</td><td>%(mv)s</td>
<td>%(tail).1f %(tailv)s</td><td>%(red).1f%%</td></tr></table>""" % {
                "lock": m["lock"],
                "lockv": "（基本没锁，H3 跟 prompt 走）" if m["lock"] > 35 else "（贴住了）",
                "mv": " ".join("%.1f" % x for x in m["mv"]),
                "tail": m["tail"],
                "tailv": "（仍在动 ✓）" if m["tail"] > 3 else "（偏静）",
                "red": m["red"] * 100}
        rows.append("""
<section class="shot">
  <h2>%(key)s <span class="tag %(cls)s">%(kind)s</span>
      <span class="meta">原片 %(t0).2f–%(t1).2fs · 覆盖源镜 %(src)s · 语音 %(vd).2fs + 补白 %(pad).2fs · 107 帧 / 8 步</span></h2>
  <p class="line">「%(dlg)s」</p>
  <div class="pair">
    <div><div class="cap">▸ 原片（同一时间起点，截 %(dur).3fs）</div>
      <video autoplay loop muted playsinline controls src="orig/%(key)s.mp4"></video></div>
    <div><div class="cap">▸ 复刻（768×1344 · 8 步）</div>
      %(vtag)s</div>
  </div>
  <div class="ins">
    <span class="icap">喂给 H3 的三张图：</span>
    <figure><img src="../ref/%(key)s.jpg"><figcaption>ref 身份/产品</figcaption></figure>
    <figure><img src="../first/%(key)s.jpg"><figcaption>first 首帧</figcaption></figure>
    <figure><img src="../last/%(key)s.jpg"><figcaption>last 末帧</figcaption></figure>
  </div>
  %(mx)s
  <details><summary>拍点设计（%(nb)d 个，含镜内调度）</summary><ul class="beats">%(beats)s</ul></details>
  %(st)s
</section>""" % {
            "key": html.escape(k), "cls": "plot" if s["kind"] == "剧情" else "prod",
            "kind": s["kind"], "t0": s["t_start"], "t1": s["t_end"], "src": s["src_shots"],
            "vd": s["voice_dur"], "pad": s["pad_tail"], "dlg": html.escape(s["dialogue"]),
            "dur": D,
            "vtag": ('<video autoplay loop muted playsinline controls '
                     'src="preview/prev_%s.mp4"></video>' % k) if os.path.exists(prev)
                    else '<div class="miss">未回收到</div>',
            "mx": mrow, "nb": len(s.get("beats", [])), "beats": beats,
            "st": ('<div class="stills">%s</div>' % "".join(
                '<a href="stills/%s" target="_blank"><img src="stills/%s"></a>' % (f, f)
                for f in stills)) if stills else ""})

    doc = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>试拍 2 片 × 2 镜 · 原片 vs 复刻</title>
<style>
:root{--bg:#f7f6f3;--panel:#fff;--ink:#1f1e1c;--dim:#6b6862;--line:#e2e0da;
--plot:#2f6fb5;--prod:#c0392b;--ok:#1D9E75;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.6 -apple-system,"PingFang SC","Helvetica Neue",sans-serif;}
header{padding:26px 28px 20px;border-bottom:1px solid var(--line);background:var(--panel)}
h1{margin:0 0 8px;font-size:21px}
header p{margin:4px 0;color:var(--dim);font-size:13px}
header b{color:var(--ink)}
main{padding:20px 28px 70px;max-width:1180px;margin:0 auto}
.shot{background:var(--panel);border:1px solid var(--line);border-radius:10px;
padding:16px 18px 14px;margin-bottom:22px}
.shot h2{margin:0 0 4px;font-size:16px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.tag{font-size:11px;padding:1px 8px;border-radius:9px;color:#fff;font-weight:600}
.tag.plot{background:var(--plot)} .tag.prod{background:var(--prod)}
.meta{color:var(--dim);font-weight:400;font-size:12px}
.line{margin:2px 0 12px;color:var(--dim);font-size:13px}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.cap{font-size:12px;color:var(--dim);margin-bottom:5px}
video{width:100%%;border-radius:7px;background:#000;display:block}
.miss{padding:40px 10px;text-align:center;color:var(--dim);border:1px dashed var(--line);border-radius:7px}
.ins{display:flex;align-items:flex-end;gap:10px;margin-top:12px;flex-wrap:wrap}
.icap{font-size:12px;color:var(--dim)}
.ins figure{margin:0}
.ins img{height:86px;border-radius:5px;border:1px solid var(--line);display:block}
.ins figcaption{font-size:11px;color:var(--dim);text-align:center;margin-top:3px}
table.mx{width:100%%;border-collapse:collapse;margin-top:12px;font-size:12.5px}
table.mx th{background:#f2f1ee;color:var(--dim);font-weight:600;text-align:left;
padding:6px 9px;border:1px solid var(--line)}
table.mx td{padding:6px 9px;border:1px solid var(--line)}
details{margin-top:11px;font-size:13px}
summary{cursor:pointer;color:var(--dim)}
ul.beats{margin:7px 0 0;padding-left:18px}
ul.beats li{margin:3px 0;color:#3b3a37}
.t{display:inline-block;min-width:78px;color:#8a877f;font-variant-numeric:tabular-nums}
.stills{display:flex;gap:8px;margin-top:12px;overflow-x:auto;padding-bottom:4px}
.stills img{height:170px;border-radius:5px;border:1px solid var(--line);flex:0 0 auto}
@media(max-width:720px){.pair{grid-template-columns:1fr}}
</style></head><body>
<header><h1>试拍 · 2 片 × 2 镜（1 剧情 + 1 产品）</h1>
<p><b>04 面试三试</b>（后门对峙 / 食堂厨房）· <b>05 相亲测试</b>（餐馆揭穿 / 家庭厨房）</p>
<p>统一 <b>107 帧 / 4.458s</b> · <b>8 步</b> · Hybrid（ref + first + last 三图）·
干声 = 原片按台词句直切（非 TTS）· 排 768×1344 · 双卡并行挂钟 <b>8 分 12 秒</b></p>
<p>左侧是原片同一时间窗，右侧是复刻 —— <b>它们时长完全一样，可以直接比信息密度</b>。</p></header>
<main>%s</main></body></html>""" % "".join(rows)

    p = os.path.join(OUT, "审查页.html")
    open(p, "w", encoding="utf-8").write(doc)
    print("→ %s  (%.0f KB)" % (p, os.path.getsize(p) / 1024))


if __name__ == "__main__":
    main()
