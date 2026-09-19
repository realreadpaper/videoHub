#!/bin/bash
# 单卡 worker：按 key 列表顺序提交，gates 断点续跑
# 用法: run_worker.sh <TAG> <PORT> <key1> [key2 ...]
set -u
BASE=/workspace/dy_key
PY=/workspace/venv/bin/python
SUB=/root/s2/submit_api.py
TAG=$1; PORT=$2; shift 2
API=http://127.0.0.1:$PORT
mkdir -p $BASE/gates
for k in "$@"; do
  if [ -f $BASE/gates/$k.done ]; then echo "[$(date +%H:%M:%S)][$TAG] skip $k (done)"; continue; fi
  echo "[$(date +%H:%M:%S)][$TAG] -> $k"
  T0=$(date +%s)
  if $PY $SUB $BASE/wf/wf_$k.json --host $API --timeout 3600; then
    touch $BASE/gates/$k.done
    echo "[$(date +%H:%M:%S)][$TAG] OK $k  $(( $(date +%s)-T0 ))s"
  else
    echo "[$(date +%H:%M:%S)][$TAG] FAIL $k"
    echo "$k" >> $BASE/failed_$TAG.txt
  fi
done
echo "[$(date +%H:%M:%S)][$TAG] ==== worker done ===="
