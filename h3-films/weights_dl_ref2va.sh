#!/bin/bash
# weights_dl_ref2va.sh — 产品参考图（Ref2VA）权重下载 · 带 sha256 校验
#
#   用途：让「真实产品图」直接参与生成（Ref2VA 参考图路线），
#         取代早期「生成空白袋面 + 后处理贴图」的老方案。
#
#   两个文件（Comfy-Org/MiniMax-H3，公开未门控）：
#     diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors   19.53 GiB
#     loras/minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors      1.82 GiB
#
#   用法： bash weights_dl_ref2va.sh            # 下载
#         bash weights_dl_ref2va.sh --verify   # 只校验
#         本脚本与 FL2VA 的 int8_convrot 同一量化格式 → A100 后端已实证可用。
#
# 退出码: 0=齐备且校验通过  2=缺失或校验失败  3=磁盘不足
set -u

LOG=/root/weights_dl_ref2va.log
exec > >(tee "$LOG") 2>&1

M=/workspace/ComfyUI/models
HF=/workspace/venv/bin/hf
REPO=Comfy-Org/MiniMax-H3
MINFREE=${MINFREE:-7}
VERIFY_ONLY=0
[ "${1:-}" = "--verify" ] && VERIFY_ONLY=1

export HF_HUB_ENABLE_HF_TRANSFER=1
export PATH=/root/.local/bin:$PATH

# ---- 清单：仓库内路径 | 官方 sha256 | 官方字节数 ----
MANIFEST=(
"diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors|9255f52b6677845ad238f20dfaafa94727053694127ab7f255c048f0f9365779|20970379616"
"loras/minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors|5b9ab5ade15d0775676d01a907268a69a1468dc6033b3b0d3ded5502f3ebb84c|1956193000"
)

echo "=== Ref2VA 权重 $(date)  verify_only=$VERIFY_ONLY ==="
mkdir -p "$M"/{diffusion_models,loras}

FAIL=0; MISSING=0

for ROW in "${MANIFEST[@]}"; do
  IFS='|' read -r REL SHA SIZE <<<"$ROW"
  DST="$M/$REL"
  echo "-----------------------------------------------"
  echo "[$REL]"
  echo "  官方大小: $SIZE 字节 ($(awk "BEGIN{printf \"%.2f\", $SIZE/1073741824}") GiB)"

  if [ -f "$DST" ]; then
    CUR=$(stat -c %s "$DST")
    if [ "$CUR" = "$SIZE" ]; then
      echo "  已存在且大小一致，校验 sha256 ..."
      GOT=$(sha256sum "$DST" | awk '{print $1}')
      if [ "$GOT" = "$SHA" ]; then echo "  ✅ 校验通过"; else echo "  ❌ sha256 不符"; FAIL=$((FAIL+1)); fi
      continue
    else
      echo "  已存在但大小不符（$CUR），重下"
      rm -f "$DST"
    fi
  fi

  if [ "$VERIFY_ONLY" = "1" ]; then echo "  ⏳ 缺失（verify 模式不下载）"; MISSING=$((MISSING+1)); continue; fi

  AVAIL=$(df -BG --output=avail "$M" | tail -1 | tr -dc '0-9')
  NEED=$(awk "BEGIN{printf \"%d\", $SIZE/1073741824 + 1}")
  if [ "$AVAIL" -lt $((NEED+MINFREE)) ]; then
    echo "  ❌ 磁盘不足：可用 ${AVAIL}G，需 ${NEED}G + 余量 ${MINFREE}G"; FAIL=$((FAIL+1)); continue
  fi

  echo "  磁盘可用 ${AVAIL}G / 本次约需 ${NEED}G"
  echo "  下载中 $(date +%T) ..."
  if $HF download "$REPO" --include "$REL" --local-dir "$M" >/dev/null 2>&1; then
    if [ -f "$DST" ]; then
      GOT=$(sha256sum "$DST" | awk '{print $1}')
      if [ "$GOT" = "$SHA" ]; then echo "  ✅ 下载完成并校验通过"; else echo "  ❌ sha256 不符: $GOT"; FAIL=$((FAIL+1)); fi
    else
      echo "  ❌ 下载后文件未出现"; FAIL=$((FAIL+1))
    fi
  else
    echo "  ❌ 下载命令失败"; FAIL=$((FAIL+1))
  fi
done

echo "==============================================="
echo "=== 汇总 $(date) ==="
for ROW in "${MANIFEST[@]}"; do
  IFS='|' read -r REL SHA SIZE <<<"$ROW"
  DST="$M/$REL"
  if [ -f "$DST" ]; then
    GOT=$(sha256sum "$DST" | awk '{print $1}')
    MARK=$([ "$GOT" = "$SHA" ] && echo "✅" || echo "❌")
    awk "BEGIN{printf \"  %s  %8.2f GiB  %s\n\", \"$MARK\", $SIZE/1073741824, \"$REL\"}"
  else
    echo "  ⏳  缺失           $REL"
  fi
done
echo "失败项: $FAIL   缺失项: $MISSING"
df -h / | tail -1
if [ "$FAIL" = "0" ] && [ "$MISSING" = "0" ]; then echo "=== 全部就绪 ==="; exit 0; else exit 2; fi
