#!/bin/bash
# 目录扫描式流水线：双卡各起一个 worker，循环领取 wf/ 下未完成的工作流
# 用法: pipeline_worker.sh <TAG> <PORT> [空闲退出秒数]
# 特点：单权重连续跑，中途不 free / 不换参；原子锁防两卡抢同一镜；断点续跑
set -u
BASE=/workspace/dy_key
PY=/workspace/venv/bin/python
SUB=/root/s2/submit_api.py
TAG=$1; PORT=$2; IDLE_LIMIT=${3:-900}
API=http://127.0.0.1:$PORT
mkdir -p $BASE/gates
idle=0
while true; do
  nxt=""
  for f in $BASE/wf/wf_*.json; do
    [ -e "$f" ] || continue
    k=$(basename "$f" .json); k=${k#wf_}
    [ -f "$BASE/gates/$k.done" ] && continue
    [ -d "$BASE/gates/$k.lock" ] && continue
    if mkdir "$BASE/gates/$k.lock" 2>/dev/null; then nxt=$k; break; fi
  done
  if [ -z "$nxt" ]; then
    idle=$((idle+20))
    echo "[$(date +%H:%M:%S)][$TAG] 待办空 空闲${idle}s"
    if [ $idle -ge $IDLE_LIMIT ]; then echo "[$(date +%H:%M:%S)][$TAG] === 退出 ==="; break; fi
    sleep 20; continue
  fi
  idle=0
  echo "[$(date +%H:%M:%S)][$TAG] -> $nxt"
  T0=$(date +%s)
  if $PY $SUB $BASE/wf/wf_$nxt.json --host $API --timeout 3600; then
    touch $BASE/gates/$nxt.done
    echo "[$(date +%H:%M:%S)][$TAG] OK $nxt  $(( $(date +%s)-T0 ))s"
  else
    echo "[$(date +%H:%M:%S)][$TAG] FAIL $nxt"
    echo "$nxt" >> $BASE/failed_$TAG.txt
  fi
  rmdir "$BASE/gates/$nxt.lock" 2>/dev/null
done
