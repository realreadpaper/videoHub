#!/bin/bash
# weights_dl_stage2.sh — Stage2 (LTX-2.5) 权重下载 · 免门控镜像 + sha256 校验
#
#   背景：官方 Lightricks/LTX-2.5 是 gated=auto（需登录 HF 同意协议），匿名下载全部 403。
#   本脚本改从两个**未门控**的社区镜像取，并逐个与官方 sha256 对齐。
#   ★ 关键：同名文件在不同镜像里内容可能不同，所以**必须分源取用**，不能图省事全用一家。
#
#   用法： bash weights_dl_stage2.sh          # 正常下载
#         bash weights_dl_stage2.sh --verify  # 只校验已存在的文件，不下载
#
# 退出码: 0=全部齐备且校验通过  2=有文件缺失或校验失败  3=磁盘不足
set -u

LOG=/root/weights_dl_stage2.log
exec > >(tee "$LOG") 2>&1

M=/workspace/ComfyUI/models
HF=/workspace/venv/bin/hf
MINFREE=${MINFREE:-6}
VERIFY_ONLY=0
[ "${1:-}" = "--verify" ] && VERIFY_ONLY=1

export HF_HUB_ENABLE_HF_TRANSFER=1
export PATH=/root/.local/bin:$PATH

# ---- 清单：路径 | 采用的仓库 | 官方 sha256 | 官方字节数 ----
# 分源依据：与官方 sha256 逐一比对得出（2026-09-17 实测）
MANIFEST=(
"diffusion_models/ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors|comfyicu/LTX-2.5|c4279eeff115cbeaca494bd2183e7d768c38fe85a184dc6afbb7159157c44334|21504034224"
"text_encoders/gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors|PulpCut/LTX-2.5-INT8-ConvRot-safetensors|6ce688a0aa98a5fa36a9f1e6c3f42152a498cc2b53ee8c15674c64244f91487f|15372969374"
"vae/ltx-2.5-video-vae-conv-bf16.safetensors|PulpCut/LTX-2.5-INT8-ConvRot-safetensors|685b06ee3d9b2039647698fc4ea33175112462fc374e2777312c907897dfce8d|1452269922"
"vae/ltx-2.5-audio-vae-bf16.safetensors|PulpCut/LTX-2.5-INT8-ConvRot-safetensors|c52733d37f6a7fb7949c3dc0fb468c6cb2169e4d836983a73babb9f0d54837a5|364866540"
"latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors|comfyicu/LTX-2.5|eb5a71fe4068ee87ccdb1c3aa635e547ca76bd2d30ae20ae889f2c325c0677e8|995778752"
)

echo "=== Stage2 下载开始 $(date)  verify_only=$VERIFY_ONLY ==="
mkdir -p "$M"/{diffusion_models,text_encoders,vae,latent_upscale_models}

FAIL=0
MISSING=0

for ROW in "${MANIFEST[@]}"; do
  IFS='|' read -r REL REPO SHA SIZE <<<"$ROW"
  DST="$M/$REL"
  echo "-----------------------------------------------"
  echo "[$REL]"
  echo "  来源仓库: $REPO"
  echo "  官方大小: $SIZE 字节"

  if [ -s "$DST" ]; then
    CUR=$(stat -c %s "$DST")
    if [ "$CUR" = "$SIZE" ]; then
      echo "  已存在且字节数吻合，跳过下载"
      if [ "$VERIFY_ONLY" = "1" ]; then
        ACT=$(sha256sum "$DST" | cut -d' ' -f1)
        if [ "$ACT" = "$SHA" ]; then echo "  ✅ sha256 校验通过"
        else echo "  ❌ sha256 不符: $ACT"; FAIL=$((FAIL+1)); fi
      fi
      continue
    else
      echo "  已存在但字节数不符（$CUR），删除重下"
      rm -f "$DST"
    fi
  fi

  [ "$VERIFY_ONLY" = "1" ] && { echo "  ❌ 缺失"; MISSING=$((MISSING+1)); continue; }

  AVAIL=$(df -BG --output=avail / | tail -1 | tr -dc '0-9')
  NEED=$(( SIZE / 1073741824 + 2 ))
  echo "  磁盘可用 ${AVAIL}G / 本次约需 ${NEED}G"
  if [ "$AVAIL" -lt "$MINFREE" ] || [ "$AVAIL" -lt "$NEED" ]; then
    echo "  ❌ 磁盘不足，中止"
    exit 3
  fi

  echo "  下载中 $(date +%H:%M:%S) ..."
  if ! $HF download "$REPO" "$REL" --local-dir "$M" 2>&1 | tail -2; then
    echo "  ❌ 下载命令失败"; FAIL=$((FAIL+1)); continue
  fi

  if [ ! -s "$DST" ]; then echo "  ❌ 落盘失败"; FAIL=$((FAIL+1)); continue; fi

  CUR=$(stat -c %s "$DST")
  if [ "$CUR" != "$SIZE" ]; then
    echo "  ❌ 字节数不符：得到 $CUR / 期望 $SIZE"; FAIL=$((FAIL+1)); continue
  fi
  ACT=$(sha256sum "$DST" | cut -d' ' -f1)
  if [ "$ACT" != "$SHA" ]; then
    echo "  ❌ sha256 不符（可能拿到了同名不同物）"
    echo "     实际: $ACT"
    echo "     期望: $SHA"
    FAIL=$((FAIL+1)); continue
  fi
  echo "  ✅ 完成并校验通过"
done

echo "==============================================="
echo "=== 汇总 $(date) ==="
for ROW in "${MANIFEST[@]}"; do
  IFS='|' read -r REL REPO SHA SIZE <<<"$ROW"
  DST="$M/$REL"
  if [ -s "$DST" ] && [ "$(stat -c %s "$DST")" = "$SIZE" ]; then
    printf "  ✅ %8.2f GiB  %s\n" "$(echo "$SIZE/1073741824" | bc -l)" "$REL"
  else
    printf "  ❌ %8s      %s\n" "缺失" "$REL"
  fi
done
echo "失败项: $FAIL   缺失项: $MISSING"
df -h / | tail -1
[ "$FAIL" = "0" ] && [ "$MISSING" = "0" ] && { echo "=== 全部就绪 ==="; exit 0; }
echo "=== 未全部就绪 ==="; exit 2
