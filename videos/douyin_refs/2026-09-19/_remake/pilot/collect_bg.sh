#!/bin/bash
# 边出边拉：以 worker 日志里的 DONE 行为触发（避免拉到写了一半的文件）
cd "$(dirname "$0")"
OUT=out/full2; mkdir -p $OUT
KEYS=(dy4_u007_stomp dy4_u060_tearopen dy5_u055_expose dy5_u042_tender)
for i in $(seq 1 80); do
  for k in "${KEYS[@]}"; do
    [ -f "$OUT/$k.mp4" ] && continue
    if ssh -o ConnectTimeout=8 kehu "grep -q 'DONE $k' /workspace/dy4/A.log /workspace/dy4/B.log" 2>/dev/null; then
      # 找实际文件名（可能是 _00001_ 或 _00002_）
      src=$(ssh -o ConnectTimeout=8 kehu "ls -t /workspace/ComfyUI/output/dy4_pilot/${k}_*.mp4 2>/dev/null | head -1")
      [ -n "$src" ] && scp -q -o ConnectTimeout=15 "kehu:$src" "$OUT/$k.mp4" && echo "[$(date +%H:%M:%S)] 拉到 $k"
    fi
  done
  [ "$(ls $OUT/*.mp4 2>/dev/null | wc -l)" -ge 4 ] && { echo "=== 4 条齐 ==="; break; }
  sleep 12
done
ls -la $OUT
