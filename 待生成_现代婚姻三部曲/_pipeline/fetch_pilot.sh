#!/bin/bash
# 本地：轮询服务器 pilot 进度 → 完成后自动拉回成品与日志
set -u
SRV=kehu
RMT=/workspace/trilogy
CO=/workspace/ComfyUI
DEST=/Users/hejianglong/Desktop/story/待生成_现代婚姻三部曲/_deliver/pilot_20260918
KEYS="f1s02 f2s05 f3s06"
MAX=7200
T=0

mkdir -p "$DEST"/{refined,draft,logs}
cd "$(dirname "$0")/.." || exit 1

echo "[$(date +%H:%M:%S)] 开始轮询，最多 ${MAX}s"
while [ $T -lt $MAX ]; do
  # 判定：run.log 出现收尾行，或三镜 s2.done 齐全
  DONE=$(ssh -o ConnectTimeout=15 $SRV "ls $RMT/gates/*.s2.done 2>/dev/null | wc -l" 2>/dev/null | tr -d ' ')
  FIN=$(ssh -o ConnectTimeout=15 $SRV "grep -c '阶段 B 结束' $RMT/run.log 2>/dev/null" 2>/dev/null | tr -d ' ')
  if [ "${DONE:-0}" -ge 3 ] || [ "${FIN:-0}" -ge 1 ]; then
    echo "[$(date +%H:%M:%S)] 检测到完成 (s2.done=$DONE, fin=$FIN)"
    break
  fi
  sleep 120; T=$((T+120))
  if [ $((T % 600)) = 0 ]; then
    echo "[$(date +%H:%M:%S)] 已等 ${T}s | $(ssh -o ConnectTimeout=15 $SRV "tail -3 $RMT/run.log 2>/dev/null" 2>/dev/null | tr '\n' ' ')"
  fi
done

echo "[$(date +%H:%M:%S)] 拉取日志..."
scp -q -o ConnectTimeout=30 $SRV:$RMT/run.log "$DEST/logs/run.log" 2>/dev/null

echo "[$(date +%H:%M:%S)] 拉取成品..."
for k in $KEYS; do
  P="${k:0:2}_${k:2}"
  # 精修成品
  ssh -o ConnectTimeout=15 $SRV "ls -t $CO/output/MiniMaxH3/trilogy_refined/${k}_*.mp4 2>/dev/null | head -1" > /tmp/p_$k.txt 2>/dev/null
  F=$(cat /tmp/p_$k.txt | tr -d ' ')
  if [ -n "$F" ]; then
    scp -q -o ConnectTimeout=120 $SRV:"$F" "$DEST/refined/$k.mp4" && echo "  ✓ refined $k"
  else
    echo "  ✗ refined $k 未找到"
  fi
  # 草稿
  ssh -o ConnectTimeout=15 $SRV "ls -t $CO/output/MiniMaxH3/trilogy/${P}_*.mp4 2>/dev/null | head -1" > /tmp/d_$k.txt 2>/dev/null
  G=$(cat /tmp/d_$k.txt | tr -d ' ')
  if [ -n "$G" ]; then
    scp -q -o ConnectTimeout=120 $SRV:"$G" "$DEST/draft/$k.mp4" && echo "  ✓ draft   $k"
  fi
done

echo "[$(date +%H:%M:%S)] 完成。目录：$DEST"
ls -la "$DEST/refined" "$DEST/draft" 2>/dev/null
