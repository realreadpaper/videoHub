#!/bin/bash
# ============================================================
# run_dy_single.sh — 抖音复刻 · 单卡跑批（两条产线通用）
# 放到目标机 /workspace/dy_key/ 下执行
#
# 单卡形态下的推荐跑法：**只起一个 worker**，靠 pipeline_worker.sh 的
# 目录扫描 + 原子锁 + gates 断点续跑。不要按 keys 手工分片（那是双卡才需要的）。
#
# 用法（服务器）：
#   cd /workspace/dy_key
#   setsid nohup bash run_dy_single.sh full > run_full.log 2>&1 < /dev/null &   # 373 镜全量
#   setsid nohup bash run_dy_single.sh key  > run_key.log  2>&1 < /dev/null &   # 39 镜关键镜
#   tail -f run_full.log
#
# 可选第 2 参数：空闲退出秒数（默认 3600，即待办空了 1 小时后退出）
#
# ⚠ 本脚本以 set -u 运行，而文案里混有中文标点。**新加行时变量一律写成 ${VAR} 形式**：
#   形如 `$PORT）`（变量后紧跟中文全角括号/冒号）在非 UTF-8 locale 下，
#   bash 会把多字节字符的字节当作变量名的一部分 → 报 `PORT\xef\xbc\x89: unbound variable`。
#   若没开 set -u 则更糟：静默展开成空串，日志里少个字，看半天看不出来。
# ============================================================
set -u

# ★ 防 http_proxy 劫持 localhost 检查：curl 访问 127.0.0.1 若走代理会拿到 502，
#   于是误报「8188 没响应」而 ComfyUI 其实跑得好好的，排查方向被彻底带偏。
export no_proxy="127.0.0.1,localhost,::1"
export NO_PROXY="127.0.0.1,localhost,::1"

BASE=/workspace/dy_key
PY=/workspace/venv/bin/python
PORT=8188
API=http://127.0.0.1:$PORT
LINE=${1:-}
IDLE=${2:-3600}
TAG=S                                   # 单 worker，tag 固定 S，失败清单写 failed_S.txt

case "$LINE" in
  full) WF_DIR=$BASE/wf_full ; GATE_DIR=$BASE/gates_full
        DESC="抖音全量复刻 373 镜"; EST="单卡挂钟约 6h40m（实测 GPU 总机时 6.57 h）" ;;
  key)  WF_DIR=$BASE/wf      ; GATE_DIR=$BASE/gates
        DESC="抖音关键镜/骨架 39 镜"; EST="单卡挂钟约 5h15m（33 镜实测总机时 18908 s）" ;;
  *)    echo "用法: bash run_dy_single.sh {full|key} [空闲退出秒数]"
        echo "  full = wf_full/ 373 镜全量复刻"
        echo "  key  = wf/      39 镜关键镜"
        exit 1 ;;
esac

mkdir -p "$GATE_DIR"
echo "[$(date +%H:%M:%S)] === $DESC · 单卡（端口 ${PORT}）==="
echo "[$(date +%H:%M:%S)] WF_DIR=$WF_DIR"
echo "[$(date +%H:%M:%S)] GATE_DIR=$GATE_DIR   （★ 两条线 gates 必须独立，混用会互相跳过）"
echo "[$(date +%H:%M:%S)] $EST"

# ---------- 0) 端口必须在跑 ----------
if [ "$(curl -s -m 5 -o /dev/null -w '%{http_code}' "$API/system_stats")" != "200" ]; then
  echo "[abort] $API 没响应。先跑：bash deploy/bootstrap/04_launch_comfy.sh single"
  exit 2
fi

# ---------- 1) 不能有另一个 worker 在跑（否则清 lock 会破坏互斥） ----------
#    ★ ps 加 2>/dev/null：某些受限环境（容器 / 沙箱）里 ps 会因权限失败。
#      失败时计数得 0 = 放行，是安全的失败方向 —— 宁可放行也别误拦。
RUNNING=$(ps -eo pid,args 2>/dev/null | grep -c "[p]ipeline_worker.sh")
if [ "$RUNNING" -gt 0 ]; then
  echo "[abort] 已有 $RUNNING 个 pipeline_worker.sh 在跑。单卡只允许一个 worker。"
  ps -eo pid,args 2>/dev/null | grep "[p]ipeline_worker.sh"
  exit 2
fi

# ---------- 2) 清残留 lock（★ 单卡接手旧机时的必做项） ----------
# 双卡时代 worker 被 kill（或机器关机）会留下空的 .lock 目录，
# 它会让该镜被**永久跳过**——既不报错也不重跑，最阴的一类故障。
LOCKS=$(find "$GATE_DIR" -maxdepth 1 -type d -name '*.lock' 2>/dev/null | wc -l | tr -d ' ')
if [ "$LOCKS" -gt 0 ]; then
  echo "[$(date +%H:%M:%S)] 发现 $LOCKS 个残留 lock，清理中..."
  find "$GATE_DIR" -maxdepth 1 -type d -name '*.lock' -exec rmdir {} \; 2>/dev/null
  echo "           剩余 $(find "$GATE_DIR" -maxdepth 1 -type d -name '*.lock' | wc -l | tr -d ' ') 个（rmdir 失败说明里面真有东西，需人工看）"
fi

# ---------- 3) 队列必须为空 ----------
BUSY=$(curl -s -m 8 "$API/queue" | $PY -c 'import json,sys;d=json.load(sys.stdin);print(len(d["queue_running"])+len(d["queue_pending"]))' 2>/dev/null || echo 99)
if [ "${BUSY:-99}" != "0" ]; then
  echo "[abort] 队列非空（$BUSY 个任务）。清队列： curl -X POST $API/queue -H 'Content-Type: application/json' -d '{\"clear\":true}'"
  exit 2
fi

# ---------- 4) 清残留权重 ----------
echo "[$(date +%H:%M:%S)] 清残留权重（/free）..."
curl -s -m 60 -X POST "$API/free" -H 'Content-Type: application/json' \
     -d '{"unload_models":true,"free_memory":true}' >/dev/null 2>&1
sleep 15

# ---------- 5) 单 worker 开跑 ----------
TODO=$(ls "$WF_DIR"/wf_*.json 2>/dev/null | wc -l | tr -d ' ')
DONE=$(ls "$GATE_DIR"/*.done 2>/dev/null | grep -v bak | wc -l | tr -d ' ')
FAILED=$(ls "$GATE_DIR"/*.fail 2>/dev/null | wc -l | tr -d ' ')
echo "[$(date +%H:%M:%S)] 工作流 $TODO 个 / 已完成 $DONE / 曾失败 $FAILED"
echo "[$(date +%H:%M:%S)] 本次预计新跑 $((TODO-DONE-FAILED)) 个"
if [ "$FAILED" -gt 0 ]; then
  echo "           ★ 有 $FAILED 个镜带 .fail 标记，会被跳过。要重跑："
  echo "             rm $GATE_DIR/*.fail    （建议先看失败原因，通常是资源引用或权重问题）"
fi
echo "[$(date +%H:%M:%S)] 启动单 worker（空闲 ${IDLE}s 后自动退出）"
echo "---------------------------------------------------------------"

WF_DIR="$WF_DIR" GATE_DIR="$GATE_DIR" exec bash "$BASE/pipeline_worker.sh" "$TAG" "$PORT" "$IDLE"
