#!/bin/bash
# 目录扫描式流水线：每卡起一个 worker，循环领取工作流目录下未完成的镜
# 用法: pipeline_worker.sh <TAG> <PORT> [空闲退出秒数]
# 特点：单权重连续跑，中途不 free / 不换参；原子锁防抢同一镜；断点续跑
#
# 用环境变量切换产线（2026-09-19 加：此前 wf 目录是硬编码的，只能跑 wf/）：
#   WF_DIR  工作流目录，默认 $BASE/wf
#   GATE_DIR 门禁目录，默认 $BASE/gates
# 例：
#   关键镜/骨架  WF_DIR=/workspace/dy_key/wf        GATE_DIR=/workspace/dy_key/gates
#   全量 373 镜  WF_DIR=/workspace/dy_key/wf_full   GATE_DIR=/workspace/dy_key/gates_full
#
# 三种门禁标记（2026-09-19 加 .fail，修「失败镜无限重试」）：
#   <k>.lock  目录 = 正在跑（mkdir 原子性保证互斥）
#   <k>.done  文件 = 已完成，永久 skip
#   <k>.fail  文件 = 失败过，**不再自动重试**（旧版会反复重领同一失败镜，
#                   单卡长跑时表现为死循环烧机时）。要重跑就删掉这个文件。
set -u
BASE=/workspace/dy_key
PY=/workspace/venv/bin/python
SUB=/root/s2/submit_api.py
TAG=$1; PORT=$2; IDLE_LIMIT=${3:-900}
WF_DIR=${WF_DIR:-$BASE/wf}
GATE_DIR=${GATE_DIR:-$BASE/gates}
API=http://127.0.0.1:$PORT
mkdir -p "$GATE_DIR"
echo "[$(date +%H:%M:%S)][$TAG] WF_DIR=$WF_DIR  GATE_DIR=$GATE_DIR"
idle=0
while true; do
  nxt=""
  for f in $WF_DIR/wf_*.json; do
    [ -e "$f" ] || continue
    k=$(basename "$f" .json); k=${k#wf_}
    [ -f "$GATE_DIR/$k.done" ] && continue
    [ -f "$GATE_DIR/$k.fail" ] && continue
    [ -d "$GATE_DIR/$k.lock" ] && continue
    if mkdir "$GATE_DIR/$k.lock" 2>/dev/null; then nxt=$k; break; fi
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
  if $PY $SUB $WF_DIR/wf_$nxt.json --host $API --timeout 3600; then
    touch $GATE_DIR/$nxt.done
    echo "[$(date +%H:%M:%S)][$TAG] OK $nxt  $(( $(date +%s)-T0 ))s"
  else
    echo "[$(date +%H:%M:%S)][$TAG] FAIL $nxt  $(( $(date +%s)-T0 ))s —— 写 .fail，不再自动重试"
    echo "$nxt" >> $BASE/failed_$TAG.txt
    touch $GATE_DIR/$nxt.fail
  fi
  rmdir "$GATE_DIR/$nxt.lock" 2>/dev/null
done
