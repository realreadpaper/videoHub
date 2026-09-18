#!/usr/bin/env bash
# 远端：等某片 20 镜「锁音轨草稿」(384x672) 全部就绪后，按镜序拼成低清预览版。
# 目的：精修(768x1344)每镜约 2.5 分钟，20 镜要等 50 分钟；先把草稿拼出来给用户抢先看内容、
#       听中文语音、查角色一致性——画面清晰度低，但语义与音轨与成片完全一致。
#
# 用法（远端）：setsid nohup bash concat_drafts.sh douyin-office film1 >/dev/null 2>&1 &
set -u
SLUG="${1:-douyin-office}"
FILM="${2:-film1}"
DRAFT=/workspace/ComfyUI/output/MiniMaxH3/$SLUG
WORK=/workspace/films/$SLUG
LOG=$WORK/logs/_draft_preview.log
mkdir -p "$WORK/logs"

case "$FILM" in
  film1) STEM=良心面试食堂红烧 ;;
  film2) STEM=相亲这场一包搞定 ;;
  *)     STEM=$FILM ;;
esac
OUT=$WORK/${STEM}_草稿版.mp4
LST=/tmp/_draft_${FILM}.txt

{
  echo "=== [$(date '+%F %T')] 等 20 镜草稿就绪 ==="
  for i in $(seq 1 240); do
    n=$(ls "$DRAFT"/voice_shot*_*.mp4 2>/dev/null | wc -l)
    [ "$n" -ge 20 ] && break
    sleep 30
  done
  n=$(ls "$DRAFT"/voice_shot*_*.mp4 2>/dev/null | wc -l)
  echo "  草稿数 = $n"
  [ "$n" -lt 20 ] && { echo "  ✘ 草稿不足 20，放弃"; exit 1; }

  : > "$LST"
  for i in $(seq -w 1 20); do
    f=$(ls -t "$DRAFT"/voice_shot${i}_*.mp4 2>/dev/null | head -1)
    [ -n "$f" ] && echo "file '$f'" >> "$LST"
  done
  echo "  清单 $(wc -l < "$LST") 条"

  # 各镜编码参数一致，优先 -c copy（零转码、几乎不占 CPU，不干扰正在跑的 GPU 渲染）
  ffmpeg -y -f concat -safe 0 -i "$LST" -c copy "$OUT" >/dev/null 2>&1
  if [ -s "$OUT" ]; then
    echo "  ✔ 草稿版（-c copy）$(du -h "$OUT" | cut -f1)"
  else
    echo "  -c copy 失败，改转码"
    ffmpeg -y -f concat -safe 0 -i "$LST" -c:v libx264 -crf 18 -preset veryfast \
           -pix_fmt yuv420p -c:a aac -b:a 160k "$OUT" >/dev/null 2>&1
    [ -s "$OUT" ] && echo "  ✔ 草稿版（转码）$(du -h "$OUT" | cut -f1)" || echo "  ✘ 合成失败"
  fi
  ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT" 2>/dev/null
} >> "$LOG" 2>&1
