#!/bin/bash
# 本地一键：上传全部资产 → 服务器 nohup 启动两段流水线（断网也不中断）
# 用法： bash _pipeline/go.sh pilot    # 试拍 3 镜（f1s02/f2s05/f3s06）
#        bash _pipeline/go.sh full     # 全量 24 镜
#        bash _pipeline/go.sh status   # 只看进度
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRV=kehu
RMT=/workspace/trilogy
CO=/workspace/ComfyUI
MODE=${1:-pilot}

say(){ echo "▶ $*"; }

if [ "$MODE" = "status" ]; then
  ssh -o ConnectTimeout=20 $SRV "cd $RMT && echo '--- 日志尾 ---' && tail -25 run.log 2>/dev/null; \
    echo '--- 阶段A完成 ---' && ls gates/*.s1.done 2>/dev/null | wc -l; \
    echo '--- 阶段B完成 ---' && ls gates/*.s2.done 2>/dev/null | wc -l; \
    echo '--- 草稿 ---' && ls -la $CO/output/MiniMaxH3/trilogy/ 2>/dev/null | tail -8; \
    echo '--- 精修 ---' && ls -la $CO/output/MiniMaxH3/trilogy_refined/ 2>/dev/null | tail -8; \
    echo '--- GPU ---' && nvidia-smi --query-gpu=memory.used --format=csv,noheader"
  exit 0
fi

# 选 keys
if [ "$MODE" = "pilot" ]; then KEYS="f1s02 f2s05 f3s06"; else KEYS=$(cat "$ROOT/_pipeline/wf/keys.txt" | tr '\n' ' '); fi
say "模式=$MODE  镜=$KEYS"

say "检查连通性..."
ssh -o ConnectTimeout=20 -o BatchMode=yes $SRV 'echo ok; nvidia-smi --query-gpu=memory.used --format=csv,noheader' || { echo "✗ 服务器不可达，稍后重试"; exit 1; }

say "建目录..."
ssh $SRV "mkdir -p $RMT/{wf,prompts,gates} $CO/input/tts_dry/trilogy $CO/input/trilogy_drafts $CO/output/MiniMaxH3/trilogy $CO/output/MiniMaxH3/trilogy_refined"

say "上传工作流 + prompt + 干声..."
scp -q -o ConnectTimeout=30 "$ROOT/_pipeline/wf/"*.json          $SRV:$RMT/wf/
scp -q -o ConnectTimeout=30 "$ROOT/_pipeline/prompts/"*.txt      $SRV:$RMT/prompts/
scp -q -o ConnectTimeout=60 "$ROOT/_pipeline/tts_dry/"*.wav      $SRV:$CO/input/tts_dry/trilogy/
scp -q -o ConnectTimeout=30 "$ROOT/_pipeline/run_server.sh"      $SRV:$RMT/
echo "$KEYS" | tr ' ' '\n' | grep -v '^$' > /tmp/trilogy_keys.txt
scp -q /tmp/trilogy_keys.txt $SRV:$RMT/keys.txt
say "上传完成：$(echo $KEYS | wc -w) 镜"

say "启动（nohup，断网不中断）..."
ssh $SRV "cd $RMT && rm -f failed_s1.txt failed_s2.txt && nohup bash run_server.sh > run.log 2>&1 & sleep 3; echo started; tail -5 run.log"
say "已启动。回来看进度： bash _pipeline/go.sh status"
