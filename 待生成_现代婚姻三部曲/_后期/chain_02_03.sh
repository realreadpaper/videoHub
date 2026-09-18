#!/bin/bash
# ==============================================================================
# 串联流水线：等 02 精修 → 拉回 → 后期总装（无字幕+外挂）→ 自动接 03 草稿批
#
# 设计原则：机器不等人。前一阶段一落盘就自动进下一阶段，避免 GPU 空转。
# 字幕策略（2026-09-14 定稿）：成片不烧字幕，只出外挂 .srt/.vtt。
# ==============================================================================
PORT=23
R=root@117.50.188.156
SSH="ssh -p ${PORT} -o StrictHostKeyChecking=no -o ConnectTimeout=15"
SCP="scp -P ${PORT} -o StrictHostKeyChecking=no -q"
BASE="/Users/hejianglong/Desktop/story/待生成_现代婚姻三部曲"
PY=/usr/bin/python3                                            # 不烧字幕就不需要 PIL
PYPIL=/Users/hejianglong/.workbuddy/binaries/python/envs/default/bin/python   # 涉及 PIL 的脚本用它
F2="$BASE/02_姜文_老子不娶了"

log() { echo "[$(date +%H:%M:%S)] $*"; }

# ---------- 1. 等 02 精修批落盘 ----------
log "等待 02《老子不娶了》精修批..."
for i in $(seq 1 120); do
  sleep 30
  S=$($SSH $R 'pgrep -f "[1]0_run_film.py" >/dev/null && echo RUN || echo DONE; ls /workspace/films/laozi_buqule/final/ 2>/dev/null | wc -l' 2>/dev/null | tr '\n' ' ')
  log "  [$((i*30))s] $S"
  case "$S" in DONE*) break;; esac
done
log "02 精修批结束，开始拉回"

# ---------- 2. 拉回 8 镜 ----------
mkdir -p "$F2/shots"
for i in 01 02 03 04 05 06 07 08; do
  $SCP $R:/workspace/films/laozi_buqule/final/shot$i.mp4 "$F2/shots/" || log "  !! 拉回失败 shot$i"
done
log "拉回完成: $(ls "$F2/shots" | wc -l | tr -d ' ') 个文件"

# ---------- 3. 后期总装（无字幕成片 + 外挂字幕）----------
cd "$BASE" || exit 1
$PY _后期/finish_film.py --film "02_姜文_老子不娶了" 2>&1 | tail -20
$PY _后期/build_html.py --film "02_姜文_老子不娶了" 2>&1 | tail -3
$PYPIL _后期/contact_sheet.py "$F2/shots" -o "$F2/抽帧总览_八镜.jpg" --cols 4 --at 6 2>&1 | tail -2
log "02 后期总装完成"

# ---------- 4. 同步 03 工程并启动草稿批 ----------
$SSH $R "mkdir -p /workspace/films/jiaming_zhiye" 
$SCP -r "$BASE/03_奉俊昊_加名之夜/." $R:/workspace/films/jiaming_zhiye/ && log "03 工程已同步"

$SSH $R 'curl -s -X POST http://127.0.0.1:8188/free -H "Content-Type: application/json" \
  -d "{\"unload_models\":true,\"free_memory\":true}"; sleep 4; nvidia-smi --query-gpu=memory.used --format=csv,noheader'

log "提交 03《加名之夜》草稿批（8 镜 × 362 帧）"
$SSH $R 'cd /workspace/films/jiaming_zhiye && mkdir -p logs && setsid nohup /workspace/venv/bin/python 10_run_film.py --stage draft --shots 1-8 < /dev/null > logs/draft_all.log 2>&1 & sleep 10; pgrep -af "[1]0_run_film.py" | head -2; tail -3 logs/draft_all.log'

# ---------- 5. 轮询 03 草稿 ----------
log "轮询 03 草稿批..."
for i in $(seq 1 120); do
  sleep 30
  S=$($SSH $R 'pgrep -f "[1]0_run_film.py" >/dev/null && echo RUN || echo DONE; ls /workspace/ComfyUI/output/MiniMaxH3/jiaming_zhiye/ 2>/dev/null | grep -c "^draft_"' 2>/dev/null | tr '\n' ' ')
  log "  [$((i*30))s] $S"
  case "$S" in DONE*) break;; esac
done
log "03 草稿批结束"
$SSH $R 'tail -14 /workspace/films/jiaming_zhiye/logs/draft_all.log'

# ---------- 6. 自动接 03 精修批 ----------
$SSH $R 'curl -s -X POST http://127.0.0.1:8188/free -H "Content-Type: application/json" \
  -d "{\"unload_models\":true,\"free_memory\":true}"; sleep 4; nvidia-smi --query-gpu=memory.used --format=csv,noheader'
log "提交 03 精修批"
$SSH $R 'cd /workspace/films/jiaming_zhiye && setsid nohup /workspace/venv/bin/python 10_run_film.py --stage refine --shots 1-8 < /dev/null > logs/refine_all.log 2>&1 & sleep 10; tail -3 logs/refine_all.log'

log "轮询 03 精修批..."
for i in $(seq 1 120); do
  sleep 30
  S=$($SSH $R 'pgrep -f "[1]0_run_film.py" >/dev/null && echo RUN || echo DONE; ls /workspace/films/jiaming_zhiye/final/ 2>/dev/null | wc -l' 2>/dev/null | tr '\n' ' ')
  log "  [$((i*30))s] $S"
  case "$S" in DONE*) break;; esac
done
log "03 精修批结束 → 可拉回做后期"
$SSH $R 'tail -14 /workspace/films/jiaming_zhiye/logs/refine_all.log'
log "=== 全链完成 ==="
