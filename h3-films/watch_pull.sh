#!/usr/bin/env bash
# 本地看护：等远端产物出现 → 自动拉回本地。
#   bash watch_pull.sh draft            # 等两片「草稿版」低清预览（384x672）
#   bash watch_pull.sh final film1      # 只等片1 的「精修全片」（768x1344）
#   bash watch_pull.sh final            # 两片都等
#
# 为什么要单独挂后台：远端单镜精修约 2.5 分钟 × 20 镜，本地不干等，
# 到货即拉，用户随时能拿到最新一版。
#
# 注意：macOS 自带 /bin/bash 是 3.2，**不支持 `declare -A` 关联数组**，
# 所以这里只用字符串记录已完成片，别再引回关联数组写法。
set -uo pipefail
cd "$(dirname "$0")"

WHAT="${1:-final}"
WANT="${2:-all}"
HOST="${3:-root@117.50.188.156}"; PORT="${4:-23}"
: "${SSHPASS:?请先 export SSHPASS=远端密码}"

SSH="sshpass -e ssh -p $PORT -o StrictHostKeyChecking=no -o ConnectTimeout=15"
SCP="sshpass -e scp -P $PORT -o StrictHostKeyChecking=no"

case "$WHAT" in
  draft) PAT='*_草稿版.mp4' ;;
  final) PAT='*_全片.mp4' ;;
  *) echo "用法: watch_pull.sh draft|final [all|film1|film2] [host] [port]"; exit 2 ;;
esac

DIRS=""
if [ "$WANT" = "all" ] || [ "$WANT" = "film1" ]; then DIRS="$DIRS /workspace/films/douyin-office"; fi
if [ "$WANT" = "all" ] || [ "$WANT" = "film2" ]; then DIRS="$DIRS /workspace/films/douyin-blinddate"; fi
NEED=0; for _d in $DIRS; do NEED=$((NEED + 1)); done

mkdir -p _deliver
echo "[watch:$WHAT/$WANT] 开始看护（每 30s 探一次，最长 3 小时，目标 $NEED 片）"

DONE=""
for i in $(seq 1 360); do
  for d in $DIRS; do
    case " $DONE " in *" $d "*) continue ;; esac
    f=$( $SSH "ls $d/$PAT 2>/dev/null | head -1" 2>/dev/null | tr -d '\r' )
    [ -z "$f" ] && continue
    base=$(basename "$f")
    if [ -s "_deliver/$base" ]; then DONE="$DONE $d"; continue; fi
    echo "[watch:$WHAT/$WANT] 第 $((i * 30 / 60)) 分钟发现 $base，拉回本地"
    if $SCP "$HOST:$f" "_deliver/$base" >/dev/null 2>&1; then
      echo "[watch:$WHAT/$WANT] ✔ 已拉回 _deliver/$base"
      DONE="$DONE $d"
    else
      echo "[watch:$WHAT/$WANT] ✘ 拉取失败，下轮重试"
    fi
  done
  n=0; for x in $DONE; do n=$((n + 1)); done
  if [ "$n" -ge "$NEED" ]; then
    echo "[watch:$WHAT/$WANT] 到齐（$n/$NEED），结束看护"
    exit 0
  fi
  sleep 30
done
echo "[watch:$WHAT/$WANT] 超时退出"
