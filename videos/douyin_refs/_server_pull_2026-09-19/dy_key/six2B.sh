#!/bin/bash
P=/workspace/venv/bin/python; S=/root/s2/submit_api.py
for k in dy2_s075 dy3_s145 dy3_s119; do
  echo "[$(date +%H:%M:%S)][B] -> $k"
  $P $S /workspace/dy_key/wf_six2/wf_$k.json --host http://127.0.0.1:8189 --timeout 1800 2>&1 | tail -2
  echo "[$(date +%H:%M:%S)][B] OK $k"
done
echo "[B] ALL DONE"
