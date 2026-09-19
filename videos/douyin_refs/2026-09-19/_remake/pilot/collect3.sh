#!/bin/bash
# 边出边拉 v3 —— 不依赖 worker 日志，纯按「远端字节数 == 本地字节数」判定完整性。
#
# v1 教训：用「目标文件是否存在」判幂等 → 一次跨境丢包留下的 0 字节空文件把它永久卡住。
# v2 教训：以 worker 日志的 DONE 行触发 → 有一路 worker 的日志因故没生成，
#          该路的两条就永远收不到。
# v3 只认事实：轮询远端文件 → 拉成 .part → 比对大小 → 一致且够大才改名，否则重试。
#         写了一半的文件大小必然对不上，所以不需要额外的「稳定性」判断。
set -u

REMOTE_DIR=/workspace/ComfyUI/output/dy4_pilot
OUT=out/full2
KEYS=(dy4_u007_stomp dy4_u060_tearopen dy5_u055_expose dy5_u042_tender)
MIN_BYTES=1000000
ROUNDS=90
GAP=10

mkdir -p "$OUT"
rssh() { ssh -o ConnectTimeout=10 -o BatchMode=yes kehu "$@" 2>/dev/null; }

pull_one() {
  local k="$1" src rsz lsz
  src=$(rssh "ls -t $REMOTE_DIR/${k}_*.mp4 2>/dev/null | head -1")
  [ -z "$src" ] && return 1
  rsz=$(rssh "stat -c%s '$src'")
  [ -z "$rsz" ] && return 1
  [ "$rsz" -lt "$MIN_BYTES" ] && return 1        # 太小，多半还在写
  rm -f "$OUT/$k.part"
  scp -q -o ConnectTimeout=20 "kehu:$src" "$OUT/$k.part" >/dev/null 2>&1 || true
  lsz=$(stat -f%z "$OUT/$k.part" 2>/dev/null || echo 0)
  if [ "$lsz" = "$rsz" ]; then
    mv "$OUT/$k.part" "$OUT/$k.mp4"
    echo "  [$(date +%H:%M:%S)] OK $k  $lsz 字节"
    return 0
  fi
  rm -f "$OUT/$k.part"
  return 1
}

cnt() { ls "$OUT"/*.mp4 2>/dev/null | wc -l | tr -d ' '; }

for r in $(seq 1 $ROUNDS); do
  n=$(cnt)
  [ "$n" -ge 4 ] && break
  for k in "${KEYS[@]}"; do
    [ -s "$OUT/$k.mp4" ] && continue
    pull_one "$k" && :
  done
  sleep $GAP
done

# 收尾：剩下的再各试两轮，避免刚好卡在最后一轮
if [ "$(cnt)" -lt 4 ]; then
  for _ in 1 2; do
    for k in "${KEYS[@]}"; do [ -s "$OUT/$k.mp4" ] || pull_one "$k"; done
    [ "$(cnt)" -ge 4 ] && break
    sleep 6
  done
fi

echo "=== 最终（$(cnt)/4）==="
ls -la "$OUT"
for k in "${KEYS[@]}"; do
  [ -s "$OUT/$k.mp4" ] || echo "  !! 缺 $k"
done
