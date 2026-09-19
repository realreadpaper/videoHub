#!/bin/bash
# 双实例并行批量出片
#  用法: run_dual.sh a|b
#  实例 A → GPU0 / 8188 ，实例 B → GPU1 / 8189
set -u

# ★ 防 http_proxy 劫持 localhost（curl 走代理会拿到 502，误报「端口没响应」）
export no_proxy="127.0.0.1,localhost,::1"
export NO_PROXY="127.0.0.1,localhost,::1"

BASE=/workspace/trilogy
PY=/workspace/venv/bin/python
SUB=/root/s2/submit_api.py
TAG=$1
case "$TAG" in
  a) PORT=8188; KEYS=$BASE/keys_a.txt ;;
  b) PORT=8189; KEYS=$BASE/keys_b.txt ;;
  *) echo "用法: $0 a|b"; exit 1 ;;
esac
API=http://127.0.0.1:$PORT
mkdir -p $BASE/gates_one

for k in $(cat $KEYS); do
  if [ -f $BASE/gates_one/$k.done ]; then echo "[$(date +%H:%M:%S)][$TAG] skip $k"; continue; fi
  # 每镜前释放显存，避免上一镜权重压在卡里（历史踩坑：ComfyUI 跑完不自动释放）
  curl -s -X POST $API/free -H 'Content-Type: application/json' \
       -d '{"unload_models":false,"free_memory":true}' > /dev/null
  echo "[$(date +%H:%M:%S)][$TAG] → $k"
  T0=$(date +%s)
  if $PY $SUB $BASE/wf_one/wf_$k.json --host $API --timeout 3600; then
    touch $BASE/gates_one/$k.done
    echo "[$(date +%H:%M:%S)][$TAG] ✓ $k 用时 $(( $(date +%s) - T0 )) s"
  else
    echo "[$(date +%H:%M:%S)][$TAG] ✗ $k FAILED"
    echo "$k" >> $BASE/failed_$TAG.txt
  fi
done
echo "[$(date +%H:%M:%S)][$TAG] ===== 本实例跑完 ====="
