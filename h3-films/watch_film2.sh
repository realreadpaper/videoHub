#!/usr/bin/env bash
# 本地看护：等片2（相亲这场一包搞定）产出 → 自动拉回 _deliver/
# 用途：片2 在远端 GPU 上串行渲染（draft ~25min + refine ~31min），
#      本地不干等，到货即拉。每 120s 探一次（间隔放长，避免 sshd 限流）。
# 用法: export SSHPASS=xxx; bash watch_film2.sh
set -uo pipefail
cd "$(dirname "$0")"

HOST="root@117.50.188.156"; PORT=23
RDIR=/workspace/films/douyin-blinddate
: "${SSHPASS:?请先 export SSHPASS=远端密码}"

SSH="sshpass -e ssh -p $PORT -o StrictHostKeyChecking=no -o ConnectTimeout=20"
SCP="sshpass -e scp -P $PORT -o StrictHostKeyChecking=no -o ConnectTimeout=25"
mkdir -p _deliver/shots_film2

rsh() { $SSH "$HOST" "$1" 2>/dev/null | tr -d '\r'; }

pull_if_new() {
  local rpath="$1" lpath="$2"
  [ -z "$rpath" ] && return 1
  local rsz; rsz=$(rsh "stat -c %s '$rpath'")
  [ -z "$rsz" ] && return 1
  if [ -s "$lpath" ]; then
    local lsz; lsz=$(stat -f %z "$lpath" 2>/dev/null || echo 0)
    [ "$lsz" = "$rsz" ] && { echo "[watch2] $lpath 已最新"; return 2; }
  fi
  echo "[watch2] 拉 $lpath ($((rsz / 1024 / 1024))MB)"
  $SCP "$HOST:$rpath" "$lpath" >/dev/null 2>&1 && { echo "[watch2] ✔ $lpath"; return 0; } || { echo "[watch2] ✘ 失败，下轮重试"; return 1; }
}

done_draft=0; done_final=0
for i in $(seq 1 60); do   # 60 × 120s = 2 小时
  if [ "$done_draft" = 0 ]; then
    f=$(rsh "ls $RDIR/*_草稿版.mp4 2>/dev/null | head -1")
    if [ -n "$f" ]; then
      pull_if_new "$f" "_deliver/$(basename "$f")" && done_draft=1
    fi
  fi
  if [ "$done_final" = 0 ]; then
    f=$(rsh "ls $RDIR/*_全片.mp4 2>/dev/null | head -1")
    if [ -n "$f" ]; then
      pull_if_new "$f" "_deliver/$(basename "$f")" && done_final=1
    fi
  fi
  # 分镜同步（只在草稿完成后做一次全量）
  if [ "$done_draft" = 1 ] && [ "$done_draft" != "synced" ]; then
    for f in $(rsh "ls $RDIR/final/shot*.mp4 2>/dev/null"); do
      pull_if_new "$f" "_deliver/shots_film2/$(basename "$f")" >/dev/null
    done
    echo "[watch2] 分镜已同步 $(ls _deliver/shots_film2/*.mp4 2>/dev/null | wc -l | tr -d ' ') 个"
    done_draft=synced
  fi
  [ "$done_draft" != 0 ] && [ "$done_final" = 1 ] && { echo "[watch2] 片2 全齐，结束"; exit 0; }
  sleep 120
done
echo "[watch2] 超时退出"
