#!/bin/bash
P=/workspace/venv/bin/python; S=/root/s2/submit_api.py
for k in dy1_s088 dy1_s093 dy2_s118; do
  echo "[$(date +%H:%M:%S)][A] -> $k"
  $P $S /workspace/dy_key/wf_six2/wf_$k.json --host http://127.0.0.1:8188 --timeout 1800 2>&1 | tail -2
  echo "[$(date +%H:%M:%S)][A] OK $k"
done
echo "[A] ALL DONE"
