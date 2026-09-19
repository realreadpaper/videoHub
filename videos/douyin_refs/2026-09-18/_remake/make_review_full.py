#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成「原片 vs 复刻」并排审查页（用于目视确认画面/口型/节奏是否对得上）。"""
import json, os, glob, subprocess, html

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "/Users/jianglong/Desktop/videoHub/videos/douyin_refs/2026-09-18"
CHK = f"{HERE}/_chk"
FF = "/usr/local/bin/ffmpeg"
KEY = {"01_报恩": ("dy1", "7661613126736204025"),
       "02_继母": ("dy2", "7686341460064787045"),
       "03_挑食": ("dy3", "7664454812574337402")}

def main():
    rows = json.load(open(f"{HERE}/shots_all.json", encoding="utf-8"))
    os.makedirs(CHK, exist_ok=True)
    idx = {f"{tag}_{r['index']:03d}": (film, r) for film, (tag, _) in KEY.items()
           for r in rows[film]}
    gots = [os.path.basename(p).replace("_00001_.mp4", "")
            for p in sorted(glob.glob(f"{HERE}/out/full/*_00001_.mp4"))]
    cards = []
    for nm in gots:
        if nm not in idx: continue
        film, r = idx[nm]
        tag, vid = KEY[film]
        mp4 = f"{BASE}/{vid}.mp4"
        orig = f"{CHK}/{nm}_原片.mp4"
        if not os.path.exists(orig):
            subprocess.run([FF, "-v", "error", "-y", "-ss", f"{r['start']:.3f}",
                            "-t", f"{r['dur']:.3f}", "-i", mp4,
                            "-vf", "scale=768:1344:force_original_aspect_ratio=increase,crop=768:1344",
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                            "-c:a", "aac", "-b:a", "128k", orig], capture_output=True)
        cards.append((nm, film, r, orig, f"{HERE}/out/full/{nm}_00001_.mp4"))

    L = ["<!doctype html><meta charset='utf-8'>",
         "<title>复刻审查 · 原片 vs 生成</title>",
         "<style>body{font-family:-apple-system,'PingFang SC',sans-serif;background:#fafafa;color:#1a1a1a;margin:0;padding:24px}"
         "h1{font-size:18px;margin:0 0 4px}h2{font-size:15px;margin:28px 0 10px}"
         ".sub{color:#666;font-size:13px;margin-bottom:18px}"
         ".card{background:#fff;border:1px solid #e5e5e5;border-radius:12px;padding:14px;margin-bottom:16px}"
         ".row{display:flex;gap:14px;flex-wrap:wrap}.cell{flex:1;min-width:200px}"
         "video{width:100%;border-radius:8px;background:#000;display:block}"
         ".tag{font-size:12px;color:#666;margin:6px 0 4px}"
         ".meta{font-size:12px;color:#777;line-height:1.7;margin-top:8px}"
         "code{background:#f2f2f2;padding:1px 5px;border-radius:4px}</style>",
         "<h1>复刻审查 · 原片 vs 生成</h1>",
         "<div class='sub'>左侧为原片该镜，右侧为 AI 重绘结果。重点看：构图是否一致、人物是否同一、口型是否跟原声。</div>"]
    for nm, film, r, orig, gen in cards:
        L += ["<div class='card'>",
              f"<h2>{film} · 镜 {r['index']} <span style='font-weight:400;color:#888'>（{r['seg']}）</span></h2>",
              "<div class='row'>",
              f"<div class='cell'><div class='tag'>原片 {r['start']:.2f}s–{r['start']+r['dur']:.2f}s（{r['dur']:.2f}s）</div>"
              f"<video src='{os.path.basename(orig)}' controls loop muted playsinline></video></div>",
              f"<div class='cell'><div class='tag'>AI 重绘（{r['frames']}帧 / {r['sec']}s）</div>"
              f"<video src='{os.path.basename(gen)}' controls loop muted playsinline></video></div>",
              "</div>",
              f"<div class='meta'>说话人：<code>{html.escape(str(r['speaker']))}</code> · 景别：<code>{html.escape(str(r['framing']))}</code>"
              f" · 台词：{html.escape(str(r['line']) or '（无台词）')}</div>",
              "</div>"]
    L.append("</body>")
    p = f"{CHK}/复刻审查_原片对照.html"
    open(p, "w", encoding="utf-8").write("\n".join(L))
    print(f"[✓] {p}  ({len(cards)} 组对照)")

if __name__ == "__main__":
    main()
