#!/usr/bin/env bash
# ============================================================
# 03_dl_weights.sh — 下载 6 个模型权重（合计约 75 GB）
# ★ 全部走 HuggingFace。旧机在华为云泰国机房，ModelScope 实测 9 B/s（等于不通）。
#   若目标机在中国大陆，可把 base 换成 hf-mirror.com，但请先 curl -L 测速再决定。
# 幂等：已存在且大小正确的文件会跳过。
# ============================================================
set -u

M=${M:-/workspace/ComfyUI/models}
HF=${HF:-https://huggingface.co}
ARIA=${ARIA:-1}          # 1=用 aria2c 多线程（推荐），0=用 wget 断点续传

mkdir -p "$M"/diffusion_models "$M"/text_encoders/minimax_h3 "$M"/vae "$M"/loras

say() { printf '\n--- %s\n' "$*"; }

dl () { # $1=url  $2=目标绝对路径  $3=期望字节数（用于校验，可留空）
  local url="$1" dst="$2" want="${3:-}"
  local name; name=$(basename "$dst")
  if [ -f "$dst" ]; then
    local have; have=$(stat -c%s "$dst")
    if [ -z "$want" ] || [ "$have" = "$want" ]; then
      printf '  [skip] %-64s %s\n' "$name" "$(numfmt --to=iec "$have" 2>/dev/null || echo "$have")"
      return 0
    fi
    echo "  [redo] $name 大小不符（有 $have 期望 $want），重下"
    rm -f "$dst"
  fi
  echo "  [get ] $name  ← $url"
  local t0=$SECONDS
  if [ "$ARIA" = "1" ] && command -v aria2c >/dev/null 2>&1; then
    aria2c -c -x 8 -s 8 -k 1M --file-allocation=none --summary-interval=10 \
           -d "$(dirname "$dst")" -o "$name" "$url" || { echo "  [!] aria2c 退出码 $?"; }
  else
    wget -c --show-progress -q -O "$dst.part" "$url" && mv "$dst.part" "$dst"
  fi
  if [ -f "$dst" ]; then
    local got; got=$(stat -c%s "$dst")
    printf '  [done] %-64s %s  (%ss)\n' "$name" "$(numfmt --to=iec "$got" 2>/dev/null || echo "$got")" "$((SECONDS-t0))"
    [ -n "$want" ] && [ "$got" != "$want" ] && echo "         ⚠ 字节数与旧机不一致：期望 $want 实得 $got"
    # 只校验 safetensors 头，能读出来即文件完好
    /workspace/venv/bin/python - "$dst" <<'PY' 2>/dev/null || true
import struct,sys,json
p=sys.argv[1]
with open(p,'rb') as f:
    n=struct.unpack('<Q',f.read(8))[0]
    if n>200_000_000: raise SystemExit(0)
    json.loads(f.read(n).decode())
print("         ✓ safetensors 头可解析")
PY
  else
    echo "  [FAIL] $name 未落盘"
  fi
}

echo "=========== H3 权重下载（约 75 GB）==========="
echo "目标目录： $M"

say "1/6 DiT 主干 · fl2va（无参考音/静音轮用）  19.5 GiB"
dl "$HF/Comfy-Org/MiniMax-H3/resolve/main/diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors" \
   "$M/diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors" 20970379616

say "2/6 DiT 主干 · Singularity ref2va（原声锁/参考图轮用）  19.5 GiB"
dl "$HF/WarmBloodAban/Minimax-h3_Singularity/resolve/main/Minimax-h3_Singularity_ref2va_Pruned_v1.3_int8.safetensors" \
   "$M/diffusion_models/Minimax-h3_Singularity_ref2va_Pruned_v1.3_int8.safetensors" 20967647456

say "3/6 Text Encoder · Qwen3-VL 32B int8  25.3 GiB"
echo "  ★ 注意子目录：必须落在 text_encoders/minimax_h3/ 下，工作流里 clip_name 写的是"
echo "    'minimax_h3/qwen3vl_32b_...' 。放错根目录会 400 value_not_in_list。"
dl "$HF/Comfy-Org/MiniMax-H3/resolve/main/text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors" \
   "$M/text_encoders/minimax_h3/qwen3vl_32b_minimax_h3_int8_convrot.safetensors" 27141342152

say "4/6 Video VAE fp16  4.85 GiB"
dl "$HF/Comfy-Org/MiniMax-H3/resolve/main/vae/minimax_h3_video_vae_fp16.safetensors" \
   "$M/vae/minimax_h3_video_vae_fp16.safetensors" 5207808496

say "5/6 Audio VAE fp32  577 MiB"
dl "$HF/Comfy-Org/MiniMax-H3/resolve/main/vae/minimax_h3_audio_vae_fp32.safetensors" \
   "$M/vae/minimax_h3_audio_vae_fp32.safetensors" 605254808

say "6/6 Turbo LoRA v4 step600 EMA（4 步加速）  592 MiB"
dl "$HF/drbaph/MiniMax-H3-Turbo-Lora-ComfyUI/resolve/main/minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors" \
   "$M/loras/minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors" 620285592

echo
echo "=========== 汇总 ==========="
find "$M" -name '*.safetensors' -printf '%12s  %p\n' 2>/dev/null | sort -rn | \
  while read -r sz p; do printf '  %8s  %s\n' "$(numfmt --to=iec "$sz")" "$p"; done
echo "  合计 $(du -sh "$M" 2>/dev/null | cut -f1)"
echo
echo "★ 权重只与「路径 + 文件名」耦合，工作流 json 里写死了这 6 个名字。改名会 400。"
echo "下一步： bash 04_launch_comfy.sh both"
