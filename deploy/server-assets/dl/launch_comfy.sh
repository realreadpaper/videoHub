#!/bin/bash
# 泰国机房 · A100 ComfyUI 启动脚本 (支持 INT8 Attention 与双卡流水线/双实例)
set -u
C=/workspace/ComfyUI
LOG=/workspace/logs
mkdir -p $LOG

# 单卡实例启动函数
start_one () {  # $1=GPU序号 $2=端口 $3=日志标识
  local gpu=$1 port=$2 tag=$3
  CUDA_VISIBLE_DEVICES=$gpu nohup setsid $C/../venv/bin/python $C/main.py       --listen 127.0.0.1 --port $port --vram-headroom 1 --use-ck-attention       > $LOG/comfy_$tag.log 2>&1 < /dev/null &
  echo "[start] gpu=$gpu port=$port log=$LOG/comfy_$tag.log (CK-INT8-Attention)"
}

# 双卡流水线单实例启动函数 (GPU 0: Text Encoder + VAE, GPU 1: DiT)
start_pipeline () { # $1=端口 (默认 8188)
  local port=${1:-8188}
  CUDA_VISIBLE_DEVICES=0,1 nohup setsid $C/../venv/bin/python $C/main.py       --listen 127.0.0.1 --port $port --vram-headroom 1 --use-ck-attention       > $LOG/comfy_pipeline.log 2>&1 < /dev/null &
  echo "[start] Dual-GPU Pipeline (GPU 0,1) port=$port log=$LOG/comfy_pipeline.log (CK-INT8-Attention)"
}

case "${1:-}" in
  a)        start_one 0 8188 a ;;
  b)        start_one 1 8189 b ;;
  both)     start_one 0 8188 a; sleep 3; start_one 1 8189 b ;;
  pipeline) start_pipeline 8188 ;;
  stop)     pkill -f "ComfyUI/main.py" ; echo "ComfyUI instances stopped." ;;
  *) echo "用法: $0 {pipeline|both|a|b|stop}" ;;
esac
