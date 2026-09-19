#!/bin/bash
# 双卡流水线并行批量出片 (Single-instance Dual-GPU Pipeline)
# GPU 0: Text Encoder (Qwen3-VL 26GB) + VAE (5GB)
# GPU 1: DiT (20GB) 全程无换出常驻
set -u
BASE=/workspace/trilogy
PY=/workspace/venv/bin/python
SUB=/root/s2/submit_api.py
PORT=8188
API=http://127.0.0.1:$PORT
mkdir -p $BASE/gates_one

KEYS="${1:-$BASE/keys.txt}"

if [ -f "$KEYS" ]; then
  TARGETS=$(cat "$KEYS")
else
  TARGETS="$KEYS"
fi

for k in $TARGETS; do
  if [ -f $BASE/gates_one/$k.done ]; then
    echo "[$(date +%H:%M:%S)][pipeline] skip $k (already done)"
    continue
  fi
  # 仅释放 PyTorch 显存碎片，不卸载常驻模型
  echo "[$(date +%H:%M:%S)][pipeline] → $k"
  T0=$(date +%s)
  if $PY $SUB $BASE/wf_pipeline/wf_$k.json --host $API --timeout 3600; then
    touch $BASE/gates_one/$k.done
    echo "[$(date +%H:%M:%S)][pipeline] ✓ $k 用时 $(( $(date +%s) - T0 )) s"
  else
    echo "[$(date +%H:%M:%S)][pipeline] ✗ $k FAILED"
    echo "$k" >> $BASE/failed_pipeline.txt
  fi
done
echo "[$(date +%H:%M:%S)][pipeline] ===== 流水线任务完成 ====="
