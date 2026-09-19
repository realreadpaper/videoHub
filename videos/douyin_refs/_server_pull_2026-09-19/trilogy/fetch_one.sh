#!/bin/bash
# 本地：轮询服务器「一步直出」进度 → 完成后自动拉回成品与日志
# 与 fetch_pilot.sh 的区别：
#   - 输出目录 MiniMaxH3/trilogy_one（非 trilogy_refined）
#   - gate 文件 gates_one/<k>.done（非 gates/*.s2.done）
#   - 无草稿，单阶段
set -u
SRV=kehu
RMT=/workspace/trilogy
CO=/workspace/ComfyUI
ROOT=/Users/hejianglong/Desktop/videoHub/待生成_现代婚姻三部曲
DEST=$ROOT/_deliver/onestep_20260918
KEYS=${KEYS:-"f1s02 f2s05 f3s06"}
NEED=$(echo $KEYS | wc -w)
MAX=9000
T=0

mkdir -p "$DEST"/{refined,logs,frames}

echo "[$(date +%H:%M:%S)] 开始轮询一步直出，期望 $NEED 镜，最多 ${MAX}s"
while [ $T -lt $MAX ]; do
  DONE=$(ssh -o ConnectTimeout=15 $SRV "ls $RMT/gates_one/*.done 2>/dev/null | wc -l" 2>/dev/null | tr -d ' ')
  DONE=${DONE:-0}
  FIN=$(ssh -o ConnectTimeout=15 $SRV "grep -c '收尾' $RMT/run_one.log 2>/dev/null" 2>/dev/null | tr -d ' ')
  FIN=${FIN:-0}
  if [ "$DONE" -ge "$NEED" ] || [ "$FIN" -ge 1 ]; then
    echo "[$(date +%H:%M:%S)] 检测到完成 (done=$DONE/$NEED, fin=$FIN)"
    break
  fi
  sleep 90; T=$((T+90))
  if [ $((T % 450)) = 0 ]; then
    echo "[$(date +%H:%M:%S)] 已等 ${T}s  done=$DONE/$NEED | $(ssh -o ConnectTimeout=15 $SRV "tail -2 $RMT/run_one.log 2>/dev/null" 2>/dev/null | tr '\n' ' ')"
  fi
done

echo "[$(date +%H:%M:%S)] 拉取日志..."
scp -q -o ConnectTimeout=30 $SRV:$RMT/run_one.log "$DEST/logs/run_one.log" 2>/dev/null

echo "[$(date +%H:%M:%S)] 拉取成品..."
for k in $KEYS; do
  P="${k:0:2}_${k:2}"     # f1s02 -> f1_s02（上传时 prefix 带下划线）
  F=$(ssh -o ConnectTimeout=15 $SRV "ls -t $CO/output/MiniMaxH3/trilogy_one/${P}_*.mp4 2>/dev/null | head -1" 2>/dev/null | tr -d ' ')
  if [ -z "$F" ]; then
    F=$(ssh -o ConnectTimeout=15 $SRV "ls -t $CO/output/MiniMaxH3/trilogy_one/${k}_*.mp4 2>/dev/null | head -1" 2>/dev/null | tr -d ' ')
  fi
  if [ -n "$F" ]; then
    scp -q -o ConnectTimeout=180 $SRV:"$F" "$DEST/refined/$k.mp4" && echo "  ✓ $k  ($(basename $F))"
  else
    echo "  ✗ $k 未找到"
  fi
done

echo "[$(date +%H:%M:%S)] 抽帧（每镜 4 帧）..."
for k in $KEYS; do
  [ -f "$DEST/refined/$k.mp4" ] || continue
  for i in 1 2 3 4; do
    /opt/homebrew/bin/ffmpeg -y -loglevel error -i "$DEST/refined/$k.mp4" \
      -vf "select='eq(n\,($i-1)*80)',scale=560:-1" -vframes 1 \
      "$DEST/frames/${k}_f$i.jpg" 2>/dev/null
  done
  echo "  ✓ $k 抽帧完成"
done

echo "[$(date +%H:%M:%S)] 完成。目录：$DEST"
ls -la "$DEST/refined" 2>/dev/null
