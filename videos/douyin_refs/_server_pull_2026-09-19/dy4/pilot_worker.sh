#!/bin/bash
# 试拍 4 镜 worker：按顺序提交给定 key，串行队列式。
# 用法: bash pilot_worker.sh <TAG> <PORT> <key...>
TAG=$1; PORT=$2; shift 2
cd /workspace/dy4 || { echo "cd /workspace/dy4 失败"; exit 1; }
for k in "$@"; do
  T0=$(date +%s)
  echo "[$(date +%H:%M:%S)][$TAG] -> $k"
  /workspace/venv/bin/python /root/s2/submit_api.py "wf/wf_${k}.json" \
    --host "http://127.0.0.1:${PORT}" --timeout 1800 2>&1 | tail -3
  echo "[$(date +%H:%M:%S)][$TAG] DONE $k  $(( $(date +%s) - T0 ))s"
done
echo "[$(date +%H:%M:%S)][$TAG] === ALL DONE ==="
