#!/bin/bash
P=/workspace/venv/bin/python
S=/root/s2/submit_api.py
for k in dy1_s001 dy1_s002 dy1_s070; do
  echo "[$(date +%H:%M:%S)] -> $k"
  $P $S /workspace/dy_key/wf_full/wf_$k.json --host http://127.0.0.1:8188 --timeout 900 2>&1 | tail -4
  echo "[$(date +%H:%M:%S)] done $k"
done
