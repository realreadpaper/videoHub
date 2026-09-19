#!/bin/bash
PIP=/workspace/venv/bin/pip
PY=/workspace/venv/bin/python

export CUDA_HOME=$($PY -c "import nvidia.cuda_nvcc as m,os;print(os.path.dirname(m.__file__))" 2>/dev/null)
if [ -z "$CUDA_HOME" ] || [ ! -x "$CUDA_HOME/bin/nvcc" ]; then
  echo "nvcc 未就绪，先装"; $PIP install -q nvidia-cuda-nvcc-cu12 2>&1 | tail -2
  export CUDA_HOME=$($PY -c "import nvidia.cuda_nvcc as m,os;print(os.path.dirname(m.__file__))")
fi
echo "CUDA_HOME=$CUDA_HOME"
"$CUDA_HOME/bin/nvcc" --version 2>/dev/null | tail -1
export PATH="$CUDA_HOME/bin:$PATH"
export TORCH_CUDA_ARCH_LIST="8.0"
export MAX_JOBS=8

echo "=== 从 GitHub 取 SageAttention ==="
cd /workspace
rm -rf SageAttention
GIT_CONFIG_GLOBAL=/dev/null git clone --quiet https://github.com/thu-ml/SageAttention.git 2>&1 | tail -3
cd /workspace/SageAttention
echo "  可用 tag:"; git tag | tail -5 | sed 's/^/    /'
GIT_CONFIG_GLOBAL=/dev/null git checkout --quiet v2.2.0 2>/dev/null && echo "  已切到 v2.2.0" || echo "  无 v2.2.0 tag，用 main ($(git rev-parse --short HEAD))"

echo "=== 编译安装（SM80 only）==="
$PIP install . --no-build-isolation 2>&1 | tail -30

echo "=== 验证 ==="
$PY - <<'PYEOF'
import sageattention
print("version:", getattr(sageattention, "__version__", "?"))
from sageattention.core import per_thread_int8_triton, per_warp_int8_cuda, per_block_int8_triton, get_cuda_arch_versions
print("SAGE_IMPORT_OK  所需符号齐全")
print("arch:", get_cuda_arch_versions())
PYEOF
