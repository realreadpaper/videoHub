#!/usr/bin/env bash
# 本地：把已生成的产物分两批拉回 _deliver/
#   A) 片1 精修分镜 final/shotNN.mp4 —— 有多少拉多少（可反复跑，已存在且大小一致则跳过）
#   B) 片1 精修正片 <片名>_全片.mp4 —— 没出现就等，出现即拉
#
# 用法: export SSHPASS=xxx; bash pull_final.sh
#   MODE=shots  只拉分镜
#   MODE=final  只等正片
#   MODE=all    两者都做（默认）
set -uo pipefail
cd "$(dirname "$0")"

HOST="root@117.50.188.156"; PORT=23
REMOTE1=/workspace/films/douyin-office
REMOTE2=/workspace/films/douyin-blinddate
MODE="${MODE:-all}"
MAXROUND="${MAXROUND:-240}"     # 每轮 30s，默认最多等 2 小时
: "${SSHPASS:?请先 export SSHPASS=远端密码}"

SSH="sshpass -e ssh -p $PORT -o StrictHostKeyChecking=no -o ConnectTimeout=15"
SCP="sshpass -e scp -P $PORT -o StrictHostKeyChecking=no -o ConnectTimeout=20"
mkdir -p _deliver/shots_film1 _deliver/shots_film2

rsh() { $SSH "$HOST" "$1" 2>/dev/null | tr -d '\r'; }

# ---------- A) 拉分镜（可增量） ----------
pull_shots() {
  local rdir="$1" ldir="$2" label="$3"
  local names
  names=$(rsh "ls $rdir/final/shot*.mp4 2>/dev/null")
  [ -z "$names" ] && { echo "[$label] 暂无分镜"; return; }
  local n=0 ok=0
  for f in $names; do
    local b; b=$(basename "$f")
    local rsz; rsz=$(rsh "stat -c %s $f")
    n=$((n + 1))
    if [ -s "$ldir/$b" ]; then
      local lsz; lsz=$(stat -f %z "$ldir/$b" 2>/dev/null || echo 0)
      if [ "$lsz" = "$rsz" ]; then ok=$((ok + 1)); continue; fi
    fi
    echo "[$label] 拉 $b ($((rsz / 1024 / 1024))MB)"
    if $SCP "$HOST:$f" "$ldir/$b" >/dev/null 2>&1; then ok=$((ok + 1)); else echo "[$label] ✘ $b 失败"; fi
  done
  echo "[$label] 分镜 $ok/$n 已同步 -> $ldir"
}

# ---------- B) 等正片 ----------
pull_films() {
  local want
  for want in "$REMOTE1:良心面试食堂红烧" "$REMOTE2:相亲这场一包搞定"; do
    local rdir="${want%%:*}" slug="${want##*:}"
    local i; i=0
    while [ "$i" -lt "$MAXROUND" ]; do
      local f; f=$(rsh "ls $rdir/*_全片.mp4 2>/dev/null | head -1")
      if [ -n "$f" ]; then
        local base; base=$(basename "$f")
        local rsz; rsz=$(rsh "stat -c %s $f")
        if [ -s "_deliver/$base" ]; then
          local lsz; lsz=$(stat -f %z "_deliver/$base" 2>/dev/null || echo 0)
          [ "$lsz" = "$rsz" ] && { echo "[正片] $base 已在本地且完整"; break; }
        fi
        echo "[正片] 发现 $base ($((rsz / 1024 / 1024))MB)，拉回中…"
        if $SCP "$HOST:$f" "_deliver/$base" >/dev/null 2>&1; then
          echo "[正片] ✔ 已拉回 _deliver/$base"; break
        fi
        echo "[正片] ✘ 拉取失败，30s 后重试"
      fi
      sleep 30; i=$((i + 1))
    done
    [ "$i" -ge "$MAXROUND" ] && echo "[正片] $slug 等待超时（远端可能还在跑）"
  done
}

case "$MODE" in
  shots) pull_shots "$REMOTE1" _deliver/shots_film1 film1
         pull_shots "$REMOTE2" _deliver/shots_film2 film2 ;;
  final) pull_films ;;
  all)   pull_shots "$REMOTE1" _deliver/shots_film1 film1
         pull_shots "$REMOTE2" _deliver/shots_film2 film2
         pull_films ;;
  *) echo "MODE 只能是 shots|final|all"; exit 2 ;;
esac
echo "[pull] 完成"
