#!/usr/bin/env bash
# 后处理流水线（零 GPU）—— 从「已生成的分镜」到「可交付成片」。
#
#   bash post_produce.sh film1                 # 跑全流程
#   bash post_produce.sh film1 --from 3        # 从第 3 阶段开始（断点续跑）
#   bash post_produce.sh film1 --only 2        # 只跑第 2 阶段
#
# 阶段
#   S1 产品贴图    overlay_product.py   真产品图逐帧贴到袋面（检测 + 光流追踪）
#   S2 节奏对齐    trim_shots.py        裁掉句末静音 + 等比提速，精确命中目标时长
#   S3 字幕带处理  mask_text_band.py    压掉 H3 照抄原片的乱码字幕（只处理确认有字的镜）
#   S4 拼接        ffmpeg concat        零转码拼接（参数一致时）
#   S5 字幕重算    make_subs_post.py    按实际成片时间轴生成外挂 .srt/.vtt
#   S6 校验        scan_text_band + ffprobe
#
# 产物：_post/<film>/  —— 成片.mp4 + 同名 .srt/.vtt + 校验接触表 + _post_report.txt
set -uo pipefail
cd "$(dirname "$0")"

PY=/Users/hejianglong/.workbuddy/binaries/python/envs/default/bin/python
FILM="${1:-film1}"; shift || true

FROM=1; ONLY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --from) FROM="$2"; shift 2;;
    --only) ONLY="$2"; shift 2;;
    *) echo "未知参数 $1"; exit 1;;
  esac
done
run_stage() { [ -n "$ONLY" ] && [ "$ONLY" != "$1" ] && return 1; [ "$1" -lt "$FROM" ] && return 1; return 0; }

# ── 每片配置 ────────────────────────────────────────────────────
if [ "$FILM" = "film1" ]; then
  STEM="良心面试_食堂红烧（原片复刻）_全片"
  TRACKS=tracks_film1.json
  TTS_DIR=_tts/film1
  TARGET=286.13
  MASKS="2,3,7,8,11,12"
else
  STEM="相亲这场一包搞定（原片复刻）_全片"
  TRACKS=tracks_film2.json
  TTS_DIR=_tts/film2
  TARGET=0
  MASKS=""
fi

W=_post/$FILM
mkdir -p "$W"
LOG=$W/_post_report.txt
: > "$LOG"
say() { echo "$@" | tee -a "$LOG"; }

say "════════ 后处理流水线 · $FILM ════════"
say "工作目录 $W"
say ""

# ── S1 产品贴图 ────────────────────────────────────────────────
if run_stage 1; then
  say "── S1 产品贴图（真产品图 → 袋面）──"
  if [ -f "$TRACKS" ]; then
    $PY overlay_product.py --tracks "$TRACKS" --out-dir "$W/s1_overlay" 2>&1 | tee -a "$LOG"
  else
    say "   跳：无 $TRACKS"
  fi
  say ""
fi
SRC_S1=$W/s1_overlay

# ── S2 节奏对齐 ────────────────────────────────────────────────
if run_stage 2; then
  say "── S2 节奏对齐（裁句末静音 + 等比提速）──"
  IN=$SRC_S1; [ -d "$IN" ] || IN=_deliver/shots_$FILM
  if [ "$TARGET" != "0" ]; then
    $PY trim_shots.py --shots "$IN" --lines "$TTS_DIR" \
        --out "$W/s2_aligned" --mode auto --target-total "$TARGET" \
        --json "$W/trim_report.json" 2>&1 | tee -a "$LOG"
  else
    $PY trim_shots.py --shots "$IN" --lines "$TTS_DIR" \
        --out "$W/s2_aligned" --mode voice-safe \
        --json "$W/trim_report.json" 2>&1 | tee -a "$LOG"
  fi
  say ""
fi
SRC_S2=$W/s2_aligned

# ── S3 字幕带处理 ──────────────────────────────────────────────
if run_stage 3; then
  say "── S3 字幕带局部处理（乱码字）──"
  IN=$SRC_S2; [ -d "$IN" ] || IN=_deliver/shots_$FILM
  if [ -n "$MASKS" ]; then
    $PY mask_text_band.py --shots "$IN" --shots-list "$MASKS" \
        --out "$W/s3_masked" --method clone --band 0.72,0.82 2>&1 | tee -a "$LOG"
  else
    say "   无待处理镜，直接复制"
    rm -rf "$W/s3_masked"; cp -R "$IN" "$W/s3_masked"
  fi
  say ""
fi
SRC_S3=$W/s3_masked
[ -d "$SRC_S3" ] || SRC_S3=$SRC_S2
[ -d "$SRC_S3" ] || SRC_S3=$SRC_S1
[ -d "$SRC_S3" ] || SRC_S3=_deliver/shots_$FILM

# ── S4 拼接 ────────────────────────────────────────────────────
if run_stage 4; then
  say "── S4 拼接成片 ──"
  FL=$W/_filelist.txt; : > "$FL"
  for f in $(ls "$SRC_S3"/shot*.mp4 | sort); do echo "file '$(cd "$(dirname "$f")" && pwd)/$(basename "$f")'" >> "$FL"; done
  say "   分镜 $(wc -l < "$FL" | tr -d ' ') 个"
  rm -f "$W/$STEM.mp4"
  ffmpeg -v error -f concat -safe 0 -i "$FL" -c copy "$W/$STEM.mp4" -y 2>>"$LOG" \
    || { say "   -c copy 失败，改重编码"; ffmpeg -v error -f concat -safe 0 -i "$FL" \
         -c:v libx264 -preset medium -crf 16 -pix_fmt yuv420p -c:a aac -b:a 192k \
         "$W/$STEM.mp4" -y 2>>"$LOG"; }
  ffprobe -v error -show_entries format=duration,size -show_entries stream=codec_type,width,height,r_frame_rate \
      -of default=noprint_wrappers=1 "$W/$STEM.mp4" 2>&1 | tee -a "$LOG"
  say ""
fi

# ── S5 字幕重算 ────────────────────────────────────────────────
if run_stage 5; then
  say "── S5 外挂字幕重算（按实际时间轴）──"
  $PY make_subs_post.py --film "$FILM" --trim "$W/trim_report.json" \
      --out-dir "$W" --stem "$STEM" 2>&1 | tee -a "$LOG"
  say "   ★ 字幕外挂、不烧画面（与成片同名同目录）"
  say ""
fi

# ── S6 校验 ────────────────────────────────────────────────────
if run_stage 6; then
  say "── S6 校验 ──"
  if [ -f "$W/$STEM.mp4" ]; then
    $PY scan_text_band.py --video "$W/$STEM.mp4" --every 6 \
        --out "$W/${STEM}_字幕带校验.jpg" 2>&1 | tail -3 | tee -a "$LOG"
    say "   → $W/${STEM}_字幕带校验.jpg  ★ 逐格目视确认"
    say "   时长 $(ffprobe -v error -show_entries format=duration -of csv=p=0 "$W/$STEM.mp4")s"
  fi
  say ""
fi

say "════════ 完成 ════════"
ls -lh "$W" | tail -n +2 | tee -a "$LOG"
