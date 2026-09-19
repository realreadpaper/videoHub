#!/bin/bash
# 泰国机房 · H3 一步直出权重下载（全部走 HuggingFace，实测 35MB/s；ModelScope 在此机房 9B/s 不可用）
set -u
M=/workspace/ComfyUI/models
mkdir -p $M/diffusion_models $M/text_encoders $M/vae $M/loras
cd $M

dl () {  # $1=url  $2=目标路径
  local url="$1" dst="$2"
  if [ -f "$dst" ]; then
    echo "[skip] $dst 已存在 ($(du -h "$dst" | cut -f1))"
    return 0
  fi
  echo "[start] $(date +%T) $dst"
  wget -q --show-progress --progress=dot:giga -c "$url" -O "$dst.part" 2>&1 | tail -2
  if [ $? -eq 0 ]; then
    mv "$dst.part" "$dst"
    echo "[done ] $(date +%T) $dst $(du -h "$dst" | cut -f1)"
  else
    echo "[FAIL ] $dst"
  fi
}

dl "https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors" \
   $M/diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors

dl "https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors" \
   $M/text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors

dl "https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/vae/minimax_h3_video_vae_fp16.safetensors" \
   $M/vae/minimax_h3_video_vae_fp16.safetensors

dl "https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/vae/minimax_h3_audio_vae_fp32.safetensors" \
   $M/vae/minimax_h3_audio_vae_fp32.safetensors

dl "https://huggingface.co/drbaph/MiniMax-H3-Turbo-Lora-ComfyUI/resolve/main/minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors" \
   $M/loras/minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors

echo "=== 全部完成 $(date +%T) ==="
ls -lh $M/*/*.safetensors
