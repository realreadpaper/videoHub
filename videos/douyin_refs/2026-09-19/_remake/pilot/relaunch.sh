#!/bin/bash
# 清场 + 重启双卡跑批（在服务器上执行；命令行里不含 worker 名，避免自杀式断连）
export no_proxy="127.0.0.1,localhost,::1"

for p in 8188 8189; do
  curl -s -X POST "http://127.0.0.1:$p/interrupt" -o /dev/null
  curl -s -X POST -H "Content-Type: application/json" -d '{"clear":true}' \
       "http://127.0.0.1:$p/queue" -o /dev/null
done
sleep 5

# ★ 用 [p] 技巧避免匹配到 grep 自己；本脚本命令行里不含该模式，故不会自杀
ps -eo pid,args | grep '[p]ilot_worker\.sh [AB] ' | sed 's/^ *//' | cut -d' ' -f1 \
  | while read -r pid; do kill "$pid" 2>/dev/null; done
sleep 3

rm -f /workspace/ComfyUI/output/dy4_pilot/*.mp4
rm -f /workspace/dy4/A.log /workspace/dy4/B.log

cd /workspace/dy4 || exit 1
setsid nohup bash -c "cd /workspace/dy4 && exec bash pilot_worker.sh A 8188 dy4_u007_stomp dy4_u060_tearopen" \
  > /workspace/dy4/A.log 2>&1 < /dev/null &
setsid nohup bash -c "cd /workspace/dy4 && exec bash pilot_worker.sh B 8189 dy5_u055_expose dy5_u042_tender" \
  > /workspace/dy4/B.log 2>&1 < /dev/null &
sleep 12

date "+服务器 %H:%M:%S"
echo "=== 进程 ==="
ps -eo pid,args | grep '[p]ilot_worker\.sh [AB] '
echo "=== 队列 ==="
for p in 8188 8189; do
  echo -n "port $p: "
  curl -s "http://127.0.0.1:$p/queue" | python3 -c \
    "import sys,json;d=json.load(sys.stdin);print('running',len(d.get('queue_running',[])),'pending',len(d.get('queue_pending',[])))"
done
echo "=== 用的哪套图 ==="
curl -s http://127.0.0.1:8188/queue | python3 -c \
  "import sys,json,re;d=json.load(sys.stdin);[print('  8188',m) for q in d.get('queue_running',[]) for m in sorted(set(re.findall(r'dy4[a-z]?_[a-z]+/[a-z0-9_]+\.jpg', json.dumps(q[2]))))]"
curl -s http://127.0.0.1:8189/queue | python3 -c \
  "import sys,json,re;d=json.load(sys.stdin);[print('  8189',m) for q in d.get('queue_running',[]) for m in sorted(set(re.findall(r'dy4[a-z]?_[a-z]+/[a-z0-9_]+\.jpg', json.dumps(q[2]))))]"
