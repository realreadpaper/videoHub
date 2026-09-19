#!/usr/bin/env bash
# 从 kehu 拉回产出资产：逐棵树独立传输 + 失败不中断 + 末尾校验
# 用法: bash pull_h3_assets.sh
set -uo pipefail

DEST="/Users/jianglong/Desktop/videoHub/videos/douyin_refs/_server_pull_2026-09-19"
HOST="kehu"
TREES=("ComfyUI/input" "ComfyUI/output")

mkdir -p "$DEST" || { echo "无法创建 $DEST"; exit 1; }
cd "$DEST" || exit 1

echo "===== 回传开始 $(date '+%Y-%m-%d %H:%M:%S') ====="
echo "目的地: $DEST"

for T in "${TREES[@]}"; do
  T0=$(date +%s)
  echo "--- [$(date '+%H:%M:%S')] 开始拉取 $T"
  if ssh -o ConnectTimeout=20 -o ServerAliveInterval=20 "$HOST" \
       "cd /workspace && tar -cf - --exclude='.DS_Store' --exclude='._*' '$T'" | tar -xf -; then
    T1=$(date +%s)
    echo "--- [$(date '+%H:%M:%S')] 完成 $T  耗时 $((T1 - T0))s  当前体积 $(du -sh "$DEST" | cut -f1)"
  else
    RC=$?
    echo "!!! [$(date '+%H:%M:%S')] 拉取失败 $T  (rc=$RC) —— 可重跑本脚本续传"
  fi
done

echo "===== 回传结束 $(date '+%Y-%m-%d %H:%M:%S') ====="
echo "本地文件数: $(find "$DEST" -type f | wc -l | tr -d ' ')"
echo "本地体积:   $(du -sh "$DEST" | cut -f1)"
