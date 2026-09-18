#!/bin/bash
# 等待前序 v3 任务彻底结束 → 强制清显存 → 启动三部曲两段流水线
# 判定"服务器空闲"只需两条，**显存不参与判定**：
#   1) v3 的 submit_api 进程已消失
#   2) ComfyUI 队列 running+pending 均为 0（连续两次，间隔 30s）
#
# ★★ 血泪（2026-09-18）：曾把"显存 < 8GB"也写进判定 → 死锁 30 分钟。
#    ComfyUI 跑完任务后**不会自动释放权重**，会常驻 20~29 GB（v3 后实测 28801 MB，
#    GPU 利用率 0%）。显存高 ≠ 在忙。正确做法是：判定空闲后**主动 POST /free**
#    （实测 28801 → 675 MiB，同时把内存可用从 6.9 GB 拉回 59.4 GB）。
set -u
BASE=/workspace/trilogy
API=http://127.0.0.1:8188
MAX_WAIT=10800          # 最多等 3 小时
T=0

q(){ curl -s -m 8 $API/queue 2>/dev/null \
     | /workspace/venv/bin/python -c 'import json,sys;d=json.load(sys.stdin);print(len(d["queue_running"])+len(d["queue_pending"]))' 2>/dev/null || echo 99; }
busy_proc(){ pgrep -f "submit_api.py /root/v3run" >/dev/null && echo 1 || echo 0; }
mem(){ nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | tr -d ' '; }

echo "[$(date +%H:%M:%S)] 等待服务器空闲（前序 v3 任务）..."
while [ $T -lt $MAX_WAIT ]; do
  P=$(busy_proc); Q=$(q)
  if [ "$P" = "0" ] && [ "$Q" = "0" ]; then
    echo "[$(date +%H:%M:%S)] 首次判定空闲 (proc=$P queue=$Q)，30s 后复核..."
    sleep 30
    P2=$(busy_proc); Q2=$(q)
    if [ "$P2" = "0" ] && [ "$Q2" = "0" ]; then
      echo "[$(date +%H:%M:%S)] 复核通过 → 空闲确认（显存不参与判定，稍后主动 free）"
      break
    fi
    echo "[$(date +%H:%M:%S)] 复核非空闲 (proc=$P2 queue=$Q2)，继续等"
  fi
  sleep 30; T=$((T+30))
  if [ $((T % 300)) = 0 ]; then echo "[$(date +%H:%M:%S)] 已等 ${T}s  proc=$P queue=$Q mem=$(mem)MB"; fi
done

if [ $T -ge $MAX_WAIT ]; then
  echo "[$(date +%H:%M:%S)] 超时未等到空闲，放弃启动"
  exit 1
fi

echo "[$(date +%H:%M:%S)] 强制清显存（前序残留权重）"
curl -s -m 60 -X POST $API/free -H "Content-Type: application/json" \
     -d '{"unload_models":true,"free_memory":true}' >/dev/null 2>&1
sleep 20
echo "[$(date +%H:%M:%S)] 清后显存: $(mem) MB"

echo "[$(date +%H:%M:%S)] ===== 启动 run_server.sh ====="
cd $BASE && bash run_server.sh
echo "[$(date +%H:%M:%S)] ===== run_server.sh 退出 ====="
