#!/bin/bash
P=/workspace/venv/bin/python
S=/root/s2/submit_api.py
for k in dy2_s001 dy3_s001 dy3_s100; do
  echo "[$(date +%H:%M:%S)] -> $k"
  $P $S /workspace/dy_key/wf_full/wf_$k.json --host http://127.0.0.1:8189 --timeout 900 2>&1 | tail -4
  echo "[$(date +%H:%M:%S)] done $k"
done
