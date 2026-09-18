#!/bin/bash
# v3 全量生产跑链：Mode B 按镜帧数 · 原声锁 · 直出 768×1344
# 顺序（模型只装两次，绝不交替）：T2V(f1 16) → T2V(f2 18) → I2V(f1 7) → I2V(f2 7)
# f2s01 已由 Mode B 验证跑完成，跳过。
set -u
cd /root/v3run
OUT=/workspace/ComfyUI/output/MiniMaxH3/v3run
S="python3 /root/s2/submit_api.py"
: > run_v3.log
i=0
for k in $(cat /root/v3run/keys.txt); do
  i=$((i+1))
  echo "== [$i/47] $k start $(date +%H:%M:%S) ==" >> run_v3.log
  $S /root/v3run/wf_$k.json >> run_v3.log 2>&1
  rc=$?
  echo "== [$i/47] $k rc=$rc end $(date +%H:%M:%S) ==" >> run_v3.log
done
echo "ALL_DONE $(date +%H:%M:%S)" >> run_v3.log
ls -la $OUT/ >> run_v3.log
touch /root/v3run/DONE
