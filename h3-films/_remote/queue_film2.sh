#!/usr/bin/env bash
# 远端：等片1 全链路（draft→refine→concat）跑完后，自动接棒跑片2。
# 用法（远端）：nohup bash /workspace/films/douyin-blinddate/queue_film2.sh > /dev/null 2>&1 &
#
# 设计要点
#  - GPU 串行：片1 与片2 绝不并发（4090 单卡，22G 显存只能跑一路）。
#  - 轮询判活：只要还有 `11_run_voice_film.py --film film1` 进程存在就等着。
#  - 幂等：每步都带续跑（草稿/精修已存在则跳过），中断后重跑本脚本即可续。
set -u

DIR=/workspace/films/douyin-blinddate
LOG=$DIR/logs/_pipeline_film2.log
PY=/workspace/venv/bin/python

mkdir -p "$DIR/logs"

{
  echo "=== [$(date '+%F %T')] 片2 排队启动，等待片1 释放 GPU ==="
  waited=0
  while pgrep -f "11_run_voice_film.py --film film1" >/dev/null 2>&1; do
    sleep 20
    waited=$((waited + 20))
    if [ $((waited % 300)) -eq 0 ]; then
      echo "  [$(date '+%H:%M:%S')] 仍在等片1（已等 $((waited / 60)) 分钟）"
    fi
  done
  echo "=== [$(date '+%F %T')] 片1 已释放，片2 开跑 ==="

  cd "$DIR" || exit 1
  $PY 11_run_voice_film.py --film film2 --shots 1-20 --stage draft
  echo "=== [$(date '+%F %T')] 片2 草稿完成，转精修 ==="
  $PY 11_run_voice_film.py --film film2 --shots 1-20 --stage refine
  echo "=== [$(date '+%F %T')] 片2 精修完成，合成全片 ==="
  $PY 11_run_voice_film.py --film film2 --concat
  echo "=== [$(date '+%F %T')] 片2 全链路结束 ==="
} >> "$LOG" 2>&1
