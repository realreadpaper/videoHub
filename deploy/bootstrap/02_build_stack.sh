#!/usr/bin/env bash
# ============================================================
# 02_build_stack.sh — 重建 Python 栈：venv + torch cu130 + ComfyUI + 3 个自定义节点
# 在目标机 root 下执行。
#
# ★★ 本脚本是旧机 /workspace/dl/build_env.sh 的**修正版**，三处差异务必保留：
#    1) COMFY_COMMIT 用 v0.36.0 (ee71d5c4)，旧脚本写的是 f42b24e(0.35) 已过时
#    2) comfy-kitchen 必须 ==0.2.34（0.2.33 没有 H3 需要的融合算子）
#    3) 补上 ComfyUI-KJNodes（旧脚本漏了，它提供 --use-ck-attention 相关的
#       PathchSageAttentionKJ 等节点与 color-matcher 依赖）
# ============================================================
set -eu

W=${W:-/workspace}
V=$W/venv
C=$W/ComfyUI
D=$W/dl
mkdir -p "$D"

COMFY_COMMIT=ee71d5c4993f29086b27fde1629a945ae48425bf   # ComfyUI v0.36.0 (2026-09-15)
NODE_COMMIT=e12d8af8ac85540da9895cb629836a4947e221ca    # comfyui-minimax-h3-audio-T8 v1.79.6
KJ_COMMIT=b3ec064dde7d122b333660918e1200e928e67ff1      # ComfyUI-KJNodes
TEA_COMMIT=4cbb50d69c73a19a5d6ec42c5aec1989d5a04b6f     # ComfyUI-MiniMaxH3-TeaCache（装了但不用）

PY=${PY:-python3}
say() { printf '\n########## %s ##########\n' "$*"; }

# ---------------------------------------------------------------
say "1/7 建 venv（目标 Python 3.10.12，与旧机一致）"
rm -rf "$V"
"$PY" -m venv "$V"
"$V/bin/pip" install -q --upgrade pip wheel setuptools
"$V/bin/python" -V

# ---------------------------------------------------------------
say "2/7 装 torch cu130"
echo "  ★ 必须走 pytorch 官方 cu130 索引。PyPI 默认源给的是普通构建，装了 driver 也是 cu130 但 torch 不带 CUDA 13 内核。"
"$V/bin/pip" install torch==2.14.0+cu130 torchvision==0.29.0+cu130 torchaudio==2.11.0+cu130 \
    --index-url https://download.pytorch.org/whl/cu130
"$V/bin/python" -c "import torch;print('  torch',torch.__version__,'| cuda',torch.version.cuda,'| gpus',torch.cuda.device_count(),'|',torch.cuda.get_device_name(0))"

# ---------------------------------------------------------------
say "3/7 clone ComfyUI 并锁定 commit $COMFY_COMMIT"
if [ ! -d "$C/.git" ]; then
  mkdir -p "$C"
  git -C "$C" init -q
  git -C "$C" remote add origin https://github.com/comfyanonymous/ComfyUI.git 2>/dev/null || \
    git -C "$C" remote set-url origin https://github.com/comfyanonymous/ComfyUI.git
  git -C "$C" fetch --depth 1 origin "$COMFY_COMMIT"
  git -C "$C" checkout -q FETCH_HEAD
fi
git -C "$C" log -1 --format='  %H %ci %s'
echo "  comfyui_version.py: $(grep __version__ "$C/comfyui_version.py" 2>/dev/null)"

# ---------------------------------------------------------------
say "4/7 装 ComfyUI 依赖（headless 清单）"
cat > "$D/requirements_headless.txt" <<'EOF'
comfyui-frontend-package==1.52.7
comfyui-embedded-docs==0.5.11
torch
torchsde
torchvision
torchaudio
numpy>=1.25.0
einops
transformers>=4.50.3
tokenizers>=0.13.3
sentencepiece
safetensors>=0.4.2
aiohttp>=3.11.8
yarl>=1.18.0
pyyaml
Pillow
scipy
tqdm
psutil
alembic
SQLAlchemy>=2.0.0
filelock
av>=17.0.0
comfy-kitchen==0.2.34
comfy-aimdo==0.5.3
requests
simpleeval>=1.0.0
blake3

# non essential dependencies:
kornia>=0.7.1
spandrel
pydantic~=2.0
pydantic-settings~=2.0
PyOpenGL>=3.1.8
comfy-angle
EOF
"$V/bin/pip" install -q -r "$D/requirements_headless.txt"
echo "  ✓ comfy-kitchen: $("$V/bin/pip" show comfy-kitchen | awk '/^Version/{print $2}')（必须 0.2.34）"

# ---------------------------------------------------------------
say "5/7 clone 三个自定义节点并锁 commit"
clone_pin () { # $1=repo_url $2=dir_name $3=commit
  local url=$1 name=$2 sha=$3 dir="$C/custom_nodes/$name"
  if [ -d "$dir/.git" ]; then echo "  [skip] $name 已存在"; return 0; fi
  GIT_CONFIG_GLOBAL=/dev/null git clone -q "$url" "$dir"   # ★ 本机有 insteadOf 改写，目标机若也有需这一行
  git -C "$dir" fetch -q --depth 1 origin "$sha" 2>/dev/null || true
  if git -C "$dir" cat-file -e "$sha^{commit}" 2>/dev/null; then
    git -C "$dir" checkout -q "$sha"
  else
    echo "  [warn] $name 取不到 $sha，留在默认分支（会与旧机不一致，务必人工核对）"
  fi
  printf '  %s → %s\n' "$name" "$(git -C "$dir" log -1 --format='%h %ci %s')"
}
clone_pin https://github.com/T8mars/comfyui-minimax-h3-audio-T8.git comfyui-minimax-h3-audio-T8 "$NODE_COMMIT"
clone_pin https://github.com/kijai/ComfyUI-KJNodes.git             ComfyUI-KJNodes               "$KJ_COMMIT"
clone_pin https://github.com/Icyoung/ComfyUI-MiniMaxH3-TeaCache.git ComfyUI-MiniMaxH3-TeaCache   "$TEA_COMMIT"

# ---------------------------------------------------------------
say "6/7 装节点依赖（必须排除 torch/numpy，否则会覆盖 cu130）"
"$V/bin/pip" install -q pillow color-matcher matplotlib mss opencv-python-headless
: > "$D/node_req.txt"
for r in "$C/custom_nodes/"*/requirements.txt; do
  [ -f "$r" ] || continue
  grep -viE '^(torch|torchvision|torchaudio|numpy|#|$)' "$r" >> "$D/node_req.txt" || true
done
sort -u "$D/node_req.txt" -o "$D/node_req.txt"
[ -s "$D/node_req.txt" ] && "$V/bin/pip" install -q -r "$D/node_req.txt" || true
echo "  内容： $(tr '\n' ' ' < "$D/node_req.txt")"
echo "  注：T8 节点自带 requirements.txt 是空说明（它的 torch/numpy 由 ComfyUI 供给），这是刻意的。"

# ---------------------------------------------------------------
say "7/7 验收"
"$V/bin/python" - <<'PYEOF'
import torch, sys
print("  python    :", sys.version.split()[0])
print("  torch     :", torch.__version__, "| cuda", torch.version.cuda, "| gpus", torch.cuda.device_count())
import comfy_kitchen
print("  kitchen   : import OK")
PYEOF
"$V/bin/pip" freeze > "$W/pip-freeze-lock.txt"
echo "  依赖锁文件已写： $W/pip-freeze-lock.txt （$(wc -l < "$W/pip-freeze-lock.txt") 个包）"
echo
echo "下一步： bash 03_dl_weights.sh"
