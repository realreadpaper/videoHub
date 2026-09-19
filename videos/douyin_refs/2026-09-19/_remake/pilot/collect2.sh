#!/bin/bash
# 边出边拉（校验版）—— 2026-09-19
#
# 为什么要有校验：v1（collect_bg.sh）用「目标文件是否存在」判断，结果一次跨境丢包中断
# 留下的 **0 字节空文件** 就把该条永久卡住了（scp 中途断了但目标文件已创建）。
# 本版：
#   ① 以 worker 日志的 DONE 行触发，避免拉到写了一半的 mp4；
#   ② 先拉成 .part，比对**远端字节数 == 本地字节数**且 > 1 MB 才改名为 .mp4；
#   ③ 失败自动重试，最后再补扫两轮，只认「大小对得上」的文件。
set -u

REMOTE_DIR=/workspace/ComfyUI/output/dy4_pilot
OUT=out/full2
KEYS=(dy4_u007_stomp dy4_u060_tearopen dy5_u055_expose dy5_u042_tender)
MIN_BYTES=1000000

mkdir -p "$OUT"

rssh() { ssh -o ConnectTimeout=10 -o BatchMode=yes kehu "$@" 2>/dev/null; }

pull_one() {
  local k="$1" src rsz lsz
  src=$(rssh "ls -t $REMOTE_DIR/${k}_*.mp4 2>/dev/null | head -1")
  [ -z "$src" ] && { echo "  [$k] 远端还没有文件"; return 1; }
  rsz=$(rssh "stat -c%s '$src'")
  [ -z "$rsz" ] && { echo "  [$k] 取不到远端大小"; return 1; }
  rm -f "$OUT/$k.part"
  scp -q -o ConnectTimeout=15 "kehu:$src" "$OUT/$k.part" || true
  lsz=$(stat -f%z "$OUT/$k.part" 2>/dev/null || echo 0)
  if [ "$lsz" = "$rsz" ] && [ "$lsz" -gt "$MIN_BYTES" ]; then
    mv "$OUT/$k.part" "$OUT/$k.mp4"
    echo "  [$(date +%H:%M:%S)] OK $k  $lsz 字节"
    return 0
  fi
  echo "  [$k] 大小不符（远端 $rsz / 本地 $lsz），重试"
  rm -f "$OUT/$k.part"
  return 1
}

done_count() { ls "$OUT"/*.mp4 2>/dev/null | wc -l | tr -d ' '; }

for round in $(seq 1 60); do
  for k in "${KEYS[@]}"; do
    [ -s "$OUT/$k.mp4" ] && continue
    rssh "grep -q 'DONE $k' /workspace/dy4/A.log /workspace/dy4/B.log" || continue
    pull_one "$k"
  done
  n=$(done_count)
  echo "[$(date +%H:%M:%S)] 已收 $n/4"
  [ "$n" -ge 4 ] && break
  sleep 10
done

for _ in 1 2; do
  for k in "${KEYS[@]}"; do [ -s "$OUT/$k.mp4" ] || pull_one "$k"; done
  [ "$(done_count)" -ge 4 ] && break
  sleep 5
done

echo "=== 最终 ==="
ls -la "$OUT"
