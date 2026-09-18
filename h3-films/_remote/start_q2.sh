#!/usr/bin/env bash
# 幂等启动器：确保 queue_film2.sh 只有一个实例在跑。
# 之所以单独放一个文件：如果直接在命令行里写脚本名再 pgrep，会匹配到执行命令本身（自匹配假阳性）。
# 本文件自身命令行只含 "start_q2.sh"，所以 pgrep "queue_film2.sh" 是干净的。
set -u
TARGET=/workspace/films/douyin-blinddate/queue_film2.sh

n=$(pgrep -fc "queue_film2\.sh" 2>/dev/null || echo 0)
if [ "${n:-0}" -gt 0 ]; then
  echo "已在运行（$n 个进程），不重复启动"
  exit 0
fi

setsid nohup bash "$TARGET" >/dev/null 2>&1 < /dev/null &
sleep 2
if pgrep -f "queue_film2\.sh" >/dev/null; then
  echo "启动成功"
  tail -2 /workspace/films/douyin-blinddate/logs/_pipeline_film2.log 2>/dev/null
else
  echo "启动失败"
  exit 1
fi
