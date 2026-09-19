#!/bin/bash
TAG=$1; PORT=$2
WFD=/workspace/dy_key/wf_v3full
GD=/workspace/dy_key/gates_v3
P=/workspace/venv/bin/python
S=/root/s2/submit_api.py
IDLE=0
while :; do
  TODO=""
  for f in $WFD/wf_*.json; do
    k=$(basename "$f" .json); k=${k#wf_}
    [ -f "$GD/$k.done" ] && continue
    mkdir "$GD/$k.lock" 2>/dev/null || continue
    [ -f "$GD/$k.done" ] && { rmdir "$GD/$k.lock" 2>/dev/null; continue; }
    TODO=$k; break
  done
  if [ -z "$TODO" ]; then
    IDLE=$((IDLE+1)); echo "[$(date +%H:%M:%S)][$TAG] 待办空 空闲${IDLE}"
    [ $IDLE -gt 60 ] && { echo "[$(date +%H:%M:%S)][$TAG] === 退出 ==="; break; }
    sleep 30; continue
  fi
  IDLE=0
  T0=$(date +%s)
  echo "[$(date +%H:%M:%S)][$TAG] -> $TODO"
  $P $S "$WFD/wf_$TODO.json" --host http://127.0.0.1:$PORT --timeout 1800 2>&1 | tail -2
  touch "$GD/$TODO.done"; rmdir "$GD/$TODO.lock" 2>/dev/null
  echo "[$(date +%H:%M:%S)][$TAG] OK $TODO  $(( $(date +%s) - T0 ))s"
done
