#!/bin/bash
# ==============================================================================
# remote_rebuild.sh —— 三部曲全量重跑（新剧本 + A1 完整 VAE 解码）
#
# 注意：**不加 --force**。
#   脚本里 stage1_draft 的 dest 常量写死 _00001_ 后缀，一旦 --force 重跑，
#   ComfyUI 会把新文件存成 _00002_，而精修仍去读 _00001_ 的旧草稿 —— 会拿错素材。
#   所以靠「已存在则跳过」的默认行为，只补跑缺失的镜头，最安全。
#
# 当前状态（预期）：
#   thirty_eight_eight : shot01 草稿+A1精修已就绪 → 只跑 02~08
#   laozi_buqule       : 未跑 → 全量 01~08
#   jiaming_zhiye      : 未跑 → 全量 01~08
# ==============================================================================
set -uo pipefail

PY=/workspace/venv/bin/python
LOG=/workspace/logs/rebuild_all.log
: > "$LOG"

for F in thirty_eight_eight laozi_buqule jiaming_zhiye; do
  {
    echo "############################## $F  START $(date +%H:%M:%S)"
  } >> "$LOG"
  cd "/workspace/films/$F" || { echo "!! 找不到 /workspace/films/$F" >> "$LOG"; continue; }
  "$PY" 10_run_film.py --shots 1-8 >> "$LOG" 2>&1
  {
    echo "############################## $F  DONE  $(date +%H:%M:%S)"
    ls final/ 2>/dev/null | wc -l | xargs echo "  成片数:"
    echo
  } >> "$LOG"
done

echo "ALL DONE $(date +%H:%M:%S)" >> "$LOG"
