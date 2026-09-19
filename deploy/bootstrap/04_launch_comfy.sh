#!/usr/bin/env bash
# ============================================================
# 04_launch_comfy.sh — 启动 ComfyUI（单实例 / 双实例）
# 在目标机执行。这是旧机 /workspace/dl/launch_comfy.sh 的**修正版**：
#   ★ 旧脚本的 start_one() 漏了 --database-url，双实例同开会 Database is locked
#   ★ 旧脚本用 nohup setsid 顺序写反了，且没重定向 stdin，ssh 断开可能带走任务
#
# 用法：
#   bash 04_launch_comfy.sh single    # ★ 单卡机器用这个：只起 GPU0→8188
#   bash 04_launch_comfy.sh both      # 双卡（GPU0→8188, GPU1→8189）
#   bash 04_launch_comfy.sh a         # 只起 GPU0→8188（等价 single，日志名不同）
#   bash 04_launch_comfy.sh pipeline  # 单任务双卡（实测更慢，仅留作对照）
#   bash 04_launch_comfy.sh stop
#   bash 04_launch_comfy.sh status
#
# ★ 单卡注意：单实例**不需要** --database-url（只有一个进程写 comfyui.db，不会锁）。
#   这一条正是双卡最容易踩的坑，单卡反而天然免疫。
# ============================================================
set -u

# ★ 防 http_proxy 劫持 localhost 检查（2026-09-19 实测踩到）：
#   WorkBuddy / Clash 等会设 http_proxy=http://127.0.0.1:xxxxx，
#   curl 请求 127.0.0.1:8188 时会走代理 → 拿到 502 或 000，
#   于是脚本报「ComfyUI 没起来」而 ComfyUI 其实跑得好好的，排查方向被彻底带偏。
export no_proxy="127.0.0.1,localhost,::1"
export NO_PROXY="127.0.0.1,localhost,::1"

C=${C:-/workspace/ComfyUI}
V=${V:-/workspace/venv}
LOG=${LOG:-/workspace/logs}
BDB=/workspace/instance_b.db
EXTRA="--vram-headroom 1 --use-ck-attention"
mkdir -p "$LOG"

start_one () { # $1=GPU序号 $2=端口 $3=tag
  local gpu=$1 port=$2 tag=$3 dbarg=""
  # ★ 端口/DB 一一对应：8189 必须用独立 sqlite，否则两个进程抢 /workspace/ComfyUI/user/comfyui.db
  [ "$port" != "8188" ] && dbarg="--database-url sqlite:///$BDB"
  CUDA_VISIBLE_DEVICES=$gpu setsid nohup "$V/bin/python" "$C/main.py" \
      --listen 127.0.0.1 --port "$port" $EXTRA $dbarg \
      > "$LOG/comfy_$tag.log" 2>&1 < /dev/null &
  echo "  [start] GPU$gpu → 127.0.0.1:$port   log=$LOG/comfy_$tag.log   db=${dbarg:-默认}"
  echo "          ★ setsid + </dev/null 是必须的，否则 ssh 会话结束会把任务带走"
}

wait_ready () { # $1=端口 $2=超时秒
  local port=$1 t=${2:-180} i=0
  while [ $i -lt "$t" ]; do
    code=$(curl -s -m 5 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/system_stats" 2>/dev/null)
    if [ "$code" = "200" ]; then
      echo "  [ready] :$port 就绪（等待 ${i}s）"
      curl -s -m 8 "http://127.0.0.1:$port/system_stats" | head -c 300; echo
      return 0
    fi
    sleep 5; i=$((i+5))
  done
  echo "  [FAIL ] :$port 在 ${t}s 内未就绪，看 $LOG/comfy_$2.log"
  return 1
}

case "${1:-both}" in
  single) start_one 0 8188 single ; sleep 2; wait_ready 8188 300
          echo "  ★ 单卡形态：只跑 8188。不需要 instance_b.db，也不需要 --database-url。" ;;
  a)   start_one 0 8188 a ; sleep 2; wait_ready 8188 300 ;;
  b)   start_one 1 8189 b ; sleep 2; wait_ready 8189 300 ;;
  both) start_one 0 8188 a; sleep 5; start_one 1 8189 b
        wait_ready 8188 300; wait_ready 8189 300 ;;
  pipeline)
        CUDA_VISIBLE_DEVICES=0,1 setsid nohup "$V/bin/python" "$C/main.py" \
          --listen 127.0.0.1 --port 8188 $EXTRA \
          > "$LOG/comfy_pipeline.log" 2>&1 < /dev/null &
        echo "  [start] 单任务双卡 → 988"
        wait_ready 8188 300 ;;
  stop)
        # ★ 不要用 pkill -f "ComfyUI/main.py"：那条命令行本身会匹配到自己，导致 ssh 断连
        for p in $(ls /proc | grep -E '^[0-9]+$'); do
          cmd=$(tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null)
          case "$cmd" in
            *"main.py"*"--port 818"*) echo "  kill $p : $cmd"; kill "$p" ;;
          esac
        done
        echo "  已停止" ;;
  status)
        ALIVE=0
        for p in 8188 8189; do
          code=$(curl -s -m 5 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$p/system_stats" 2>/dev/null)
          q=$(curl -s -m 5 "http://127.0.0.1:$p/queue" 2>/dev/null)
          # ★ 单卡机器上 8189 不存在是正常的，不要当成故障
          [ "$code" = "200" ] && { echo "  :$p HTTP=$code  queue=$q"; ALIVE=$((ALIVE+1)); } \
                              || echo "  :$p 未启动"
        done
        echo "  存活实例：$ALIVE （单卡机器应为 1，双卡机器应为 2）"
        nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader | sed 's/^/  /'
        echo "  ★ 显存高 ≠ 在忙：必须看 /queue。空闲实例也会常驻 ~57 GB。" ;;
  *)   echo "用法: $0 {both|a|b|pipeline|stop|status}" ;;
esac
