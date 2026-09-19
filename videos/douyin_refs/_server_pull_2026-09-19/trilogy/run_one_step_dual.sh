#!/bin/bash
# 双卡一步直出（2026-09-18 服务器升 2×A100-PCIE-40G 后启用）
#
# 前提（已核实）：
#   · 实例 8188：CUDA_VISIBLE_DEVICES=0；实例 8189：CUDA_VISIBLE_DEVICES=1
#   · ComfyUI 0.35.0，submit_api.py 支持 --host
# 用法（服务器）：cd /workspace/trilogy && nohup bash run_one_step_dual.sh > run_one_dual.log 2>&1 &
# 可选参数： bash run_one_step_dual.sh keys_full.txt
#
# 规矩（AGENTS.md）：
#   · 点火前两端口队列必须为空，否则拒跑（别叠别人的任务）
#   · 显存高 ≠ 在忙：启动时对自己的端口 POST /free
#   · gates_one 按 key 天然互斥，两 worker 取不相交 keys，无需加锁
set -u
BASE=/workspace/trilogy
CO=/workspace/ComfyUI
OUT=$CO/output/MiniMaxH3/trilogy_one
PY=/workspace/venv/bin/python
SUB=/root/s2/submit_api.py
KEYFILE=${1:-keys.txt}

mkdir -p $BASE/gates_one $OUT
cd $BASE

# 0) 两端口队列必须空闲
for PORT in 8188 8189; do
  BUSY=$(curl -s -m 8 http://127.0.0.1:$PORT/queue | $PY -c 'import json,sys;d=json.load(sys.stdin);print(len(d["queue_running"])+len(d["queue_pending"]))' 2>/dev/null || echo 99)
  if [ "${BUSY:-99}" != "0" ]; then echo "[abort] 端口 $PORT 队列非空($BUSY)，拒绝点火"; exit 2; fi
done

# 1) keys 轮流对半（逐镜时长相近，轮转分最均衡）
awk 'NR%2==1' $KEYFILE > keys_a.txt
awk 'NR%2==0' $KEYFILE > keys_b.txt
echo "[$(date +%H:%M:%S)] 双卡分发 A: $(tr '\n' ' ' < keys_a.txt)"
echo "[$(date +%H:%M:%S)] 双卡分发 B: $(tr '\n' ' ' < keys_b.txt)"

# 2) 清两卡残留权重（权重常驻 ≠ 在忙）
for PORT in 8188 8189; do
  curl -s -m 60 -X POST http://127.0.0.1:$PORT/free -H 'Content-Type: application/json' \
       -d '{"unload_models":true,"free_memory":true}' >/dev/null 2>&1
done
sleep 15

worker(){
  local TAG=$1 PORT=$2 KFILE=$3
  local API=http://127.0.0.1:$PORT
  while read -r k; do
    [ -z "$k" ] && continue
    if [ -f gates_one/$k.done ]; then echo "  [$TAG][skip] $k 已完成"; continue; fi
    local T0=$(date +%s)
    if $PY $SUB wf_one/wf_$k.json --host $API --timeout 2400; then
      touch gates_one/$k.done
      echo "  [$TAG][✓] $k  $(( $(date +%s)-T0 ))s"
    else
      echo "  [$TAG][✗] $k"
      echo "$k" >> failed_one_$TAG.txt
    fi
  done < $KFILE
}

worker A 8188 keys_a.txt &
PA=$!
worker B 8189 keys_b.txt &
PB=$!
wait $PA $PB

echo "=========== 双卡收尾 ==========="
echo "[$(date +%H:%M:%S)] gates 完成: $(ls gates_one/*.done 2>/dev/null | grep -v bak | wc -l)"
[ -f failed_one_A.txt ] && { echo "A 失败:"; cat failed_one_A.txt; }
[ -f failed_one_B.txt ] && { echo "B 失败:"; cat failed_one_B.txt; }
nvidia-smi --query-gpu=index,memory.used --format=csv,noheader
