#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""拼片：373 镜 → 三部成片，与原片等长、原片音轨。

要点：
1. 每镜生成长度是**向上吸附**的（≥ 原片镜长），此处逐镜裁回原片精确镜长
2. 音轨直接用**原片完整音轨**（人声+环境音+BGM 全保留），不取 H3 输出音频
3. 字幕沿用原片 srt（词级时间戳，天然对齐）
"""
import json, os, glob, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "/Users/jianglong/Desktop/videoHub/videos/douyin_refs/2026-09-18"
SRC = f"{HERE}/out/full"
TMP = f"{HERE}/_concat"
DST = f"{HERE}/成片_full"
FF = "/usr/local/bin/ffmpeg"

KEY = {"01_报恩": ("dy1", "7661613126736204025"),
       "02_继母": ("dy2", "7686341460064787045"),
       "03_挑食": ("dy3", "7664454812574337402")}

def one(src, dst, dur):
    """裁回原片精确镜长 + 统一编码参数（保证 concat -c copy 可用）"""
    cmd = [FF, "-v", "error", "-y", "-i", src, "-t", f"{dur:.3f}",
           "-vf", "scale=768:1344,fps=24,setsar=1",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
           "-pix_fmt", "yuv420p", "-an", dst]
    return subprocess.run(cmd, capture_output=True).returncode == 0

def main():
    rows = json.load(open(f"{HERE}/shots_all.json", encoding="utf-8"))
    os.makedirs(TMP, exist_ok=True); os.makedirs(DST, exist_ok=True)
    report = {}
    for film, lst in rows.items():
        tag, vid = KEY[film]
        mp4 = f"{BASE}/{vid}.mp4"
        parts = []
        miss = []
        for r in lst:
            nm = f"{tag}_s{r['index']:03d}"
            g = glob.glob(f"{SRC}/{nm}*.mp4")
            if not g:
                miss.append(nm); continue
            d = f"{TMP}/{nm}.mp4"
            if one(sorted(g)[-1], d, r["dur"]):
                parts.append(d)
            else:
                miss.append(nm)
        if not parts:
            print(f"[{film}] 无可用镜，跳过"); continue
        lst_txt = f"{TMP}/{tag}_list.txt"
        open(lst_txt, "w").write("".join(f"file '{p}'\n" for p in parts))
        silent = f"{TMP}/{tag}_v.mp4"
        subprocess.run([FF, "-v", "error", "-y", "-f", "concat", "-safe", "0",
                        "-i", lst_txt, "-c", "copy", silent], capture_output=True)
        out = f"{DST}/{film}_百分百复刻.mp4"
        # 挂原片完整音轨（人声+环境音+BGM）
        subprocess.run([FF, "-v", "error", "-y", "-i", silent, "-i", mp4,
                        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
                        "-c:a", "aac", "-b:a", "192k", "-shortest", out],
                       capture_output=True)
        # 字幕沿用原片 srt
        srt = f"{BASE}/{vid}/{vid}.srt"
        if os.path.exists(srt):
            open(f"{DST}/{film}_百分百复刻.srt", "w", encoding="utf-8").write(
                open(srt, encoding="utf-8").read())
        dur = subprocess.run([FF, "-v", "error", "-i", out, "-f", "null", "-"],
                             capture_output=True, text=True)
        report[film] = dict(clips=len(parts), missing=miss,
                            out=out, target=sum(r["dur"] for r in lst))
        print(f"[{film}] {len(parts)} 镜 → {os.path.basename(out)}  (缺 {len(miss)} 镜)")
        if miss[:5]: print(f"     缺: {miss[:5]}")
    json.dump(report, open(f"{DST}/_report.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n[✓] 成片目录 {DST}")

if __name__ == "__main__":
    main()
