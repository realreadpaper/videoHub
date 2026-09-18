#!/bin/bash
# v3 交付流水线：取回 48 镜 → 逐镜规格核对 → 拼两部成片（30fps/720×1280）
# → 原片同窗重剪版 → 逐镜左右对照版（左=生成，右=原片，便于决定哪镜要重生成）
set -e
H3=/Users/hejianglong/Desktop/videoHub/h3-films
DL=$H3/_deliver/v3
SRV="kehu:/workspace/ComfyUI/output/MiniMaxH3/v3run"
mkdir -p "$DL/shots/film1" "$DL/shots/film2" "$DL/orig/film1" "$DL/orig/film2"

# ① 取回（v3run 下的 f1sNN_*.mp4 / f2sNN_*.mp4）
for f in $(ssh kehu 'ls /workspace/ComfyUI/output/MiniMaxH3/v3run/'); do
  key=$(echo "$f" | cut -d_ -f1)          # f1s01
  film=film${key:1:1}; no=${key:3:2}
  scp -q "$SRV/${f%.mp4}_"*.mp4 "$DL/shots/$film/shot$no.mp4" 2>/dev/null || \
    scp -q "$SRV/$f" "$DL/shots/$film/shot$no.mp4"
done

# ② 原片同窗切段 + 统一转码（720×1280 / 30fps / aac48k）
python3 - <<'PYEOF'
import json, os, subprocess
H3 = "/Users/hejianglong/Desktop/videoHub/h3-films"
DL = H3 + "/_deliver/v3"
REFS = {"film1": "/Users/hejianglong/Desktop/videoHub/videos/douyin-ad/ref/7661791104643797617.mp4",
        "film2": "/Users/hejianglong/Desktop/videoHub/videos/douyin-ad-2/references/homecoref.mp4"}
REFS["film2"] = "/Users/hejianglong/Desktop/videoHub/videos/douyin-ad-2/references/homecook/source.mp4"
VF = "scale=720:1280,fps=30,setsar=1"  # 768x1344 与原片 720x1282 都强制到 720x1280（比例差<1%）
for film in ("film1", "film2"):
    lines = json.load(open(H3 + "/_lines_rhythm/" + film + "_shot_lines.json", encoding="utf-8"))
    for w in lines["shots"]:
        no = "shot%02d" % w["no"]
        # 生成镜统一转码
        g = DL + "/shots/%s/%s.mp4" % (film, no)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", g, "-vf", VF,
                        "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                        DL + "/shots/%s/%s_720.mp4" % (film, no)], check=True)
        # 原片同窗
        subprocess.run(["ffmpeg", "-v", "error", "-y",
                        "-ss", "%.3f" % w["t0"], "-t", "%.3f" % (w["t1"] - w["t0"]),
                        "-i", REFS[film], "-vf", VF,
                        "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                        DL + "/orig/%s/%s_720.mp4" % (film, no)], check=True)
    print(film, "per-shot done")
PYEOF

# ③ 拼成片 + 原片重剪版 + 左右对照版
for film in film1 film2; do
  cd "$DL/shots/$film"
  printf "file '%s'\n" "$PWD"/shot??_720.mp4 | sort > list.txt
  ffmpeg -v error -y -f concat -safe 0 -i list.txt -c copy "$DL/成片_${film}.mp4"
  cd "$DL/orig/$film"
  printf "file '%s'\n" "$PWD"/shot??_720.mp4 | sort > list.txt
  ffmpeg -v error -y -f concat -safe 0 -i list.txt -c copy "$DL/原片重剪_${film}.mp4"
  # 逐镜对照（左生成右原片）
  mkdir -p "$DL/cmp/$film"
  for g in "$DL/shots/$film"/shot??_720.mp4; do
    b=$(basename "$g" _720.mp4)
    ffmpeg -v error -y -i "$g" -i "$DL/orig/$film/${b}_720.mp4" \
      -filter_complex "[0:v][1:v]hstack[v]" -map "[v]" -map 0:a \
      -c:v libx264 -crf 18 -pix_fmt yuv420p -c:a aac -b:a 160k "$DL/cmp/$film/${b}_cmp.mp4"
  done
  cd "$DL/cmp/$film"
  printf "file '%s'\n" "$PWD"/shot??_cmp.mp4 | sort > list.txt
  ffmpeg -v error -y -f concat -safe 0 -i list.txt -c copy "$DL/对照_左生成右原片_${film}.mp4"
done
echo "=== 交付完成 ==="
ls -la "$DL" | grep -v "^d"
