#!/usr/bin/env bash
# 把远端已合成的全片拉回本地，配好外挂字幕，落到 _deliver/ 交付目录。
#
#   export SSHPASS='远端密码'
#   bash pack_delivery.sh film1          # 只取片1
#   bash pack_delivery.sh                # 两片都取（默认 all）
#
# 交付口径（爸爸定下的硬规矩）：
#   · 成片**绝不烧字幕**，字幕以独立 .srt / .vtt 外挂，**与成片同名同目录**。
#   · 目录结构：_deliver/<片名>.mp4 + <片名>.srt + <片名>.vtt
set -uo pipefail
cd "$(dirname "$0")"

HOST="${1:-root@117.50.188.156}"; PORT="${2:-23}"
WANT="${3:-all}"
: "${SSHPASS:?请先 export SSHPASS=远端密码}"

SSH="sshpass -e ssh -p $PORT -o StrictHostKeyChecking=no -o ConnectTimeout=15"
SCP="sshpass -e scp -P $PORT -o StrictHostKeyChecking=no"

OUT=_deliver
mkdir -p "$OUT"

# film tag / 远端目录 / 片名（与 make_subs.py 的 safe_name 保持一致）
declare -a ROWS
ROWS[0]="film1|douyin-office|良心面试食堂红烧|p1_data"
ROWS[1]="film2|douyin-blinddate|相亲这场一包搞定|p2_data"

for row in "${ROWS[@]}"; do
  IFS='|' read -r tag slug stem mod <<< "$row"
  [ "$WANT" != "all" ] && [ "$WANT" != "$tag" ] && continue

  echo "== $tag （$stem）=="
  REMOTE_ALL=$( $SSH "ls /workspace/films/$slug/*_全片.mp4 2>/dev/null | head -1" | tr -d '\r' )
  if [ -z "$REMOTE_ALL" ]; then echo "   ✘ 远端还没有全片（渲染未完成），跳过"; continue; fi
  echo "   远端: $REMOTE_ALL"

  $SCP "$HOST:$REMOTE_ALL" "$OUT/$stem.mp4" >/dev/null 2>&1 || { echo "   ✘ 取片失败"; continue; }

  # ★ 禁字铁律门（爸爸定死）：画面不许出现任何成行文字 / 乱码字幕。
  #   权威判据 = 字幕带接触表（人眼逐格扫，30 秒看完）；
  #   OCR 只作预警与时间码定位 —— tesseract 对 H3 画的伪汉字识别弱、对纹理误报多。
  PY=/Users/hejianglong/.workbuddy/binaries/python/envs/default/bin/python
  echo "   禁字铁律：生成字幕带接触表…"
  mkdir -p _review
  if $PY scan_text_band.py --video "$OUT/$stem.mp4" --every 5 \
        --out "_review/${stem}_字幕带扫描.jpg" >/dev/null 2>&1; then
    echo "   → _review/${stem}_字幕带扫描.jpg　★ 逐格确认无「成行乱码汉字/数字」"
  else
    echo "   ⚠ 接触表生成失败，请手动检查画面下方 66%–90% 区域"
  fi
  echo "   OCR 预筛（仅预警，误报率高，勿据此判死刑）："
  $PY check_no_text.py --video "$OUT/$stem.mp4" --n 30 --quiet 2>&1 \
      | grep -E "预警器|❌|REVIEW" | head -6 | sed 's/^/     /'

  if [ ! -f "$stem.srt" ]; then
    echo "   本地缺字幕，先生成"
    /Users/hejianglong/.workbuddy/binaries/python/envs/default/bin/python make_subs.py --film "$tag" >/dev/null 2>&1
  fi
  cp -f "${stem}_字幕.srt" "$OUT/$stem.srt" 2>/dev/null
  cp -f "${stem}_字幕.vtt" "$OUT/$stem.vtt" 2>/dev/null

  echo "   ✔ 成片 $(du -h "$OUT/$stem.mp4" | cut -f1)  字幕 $(grep -c ' --> ' "$OUT/$stem.srt" 2>/dev/null || echo '?') 条"
  ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT/$stem.mp4" 2>/dev/null | awk '{printf "   时长 %.2fs（%.2f 分钟）\n", $1, $1/60}'
done

echo
echo "交付目录 $OUT/ ："
ls -lh "$OUT" 2>/dev/null | tail -n +2
