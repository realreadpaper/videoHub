#!/bin/bash
PIP=/workspace/venv/bin/pip
PY=/workspace/venv/bin/python

echo "=== 1. 装 nvcc (pip, 不动系统 CUDA) ==="
$PIP install -q nvidia-cuda-nvcc-cu12 2>&1 | tail -3
export CUDA_HOME=$($PY -c "import nvidia.cuda_nvcc as m,os;print(os.path.dirname(m.__file__))")
echo "CUDA_HOME=$CUDA_HOME"
ls -l "$CUDA_HOME/bin/nvcc" 2>/dev/null || echo "nvcc 缺失!"
"$CUDA_HOME/bin/nvcc" --version 2>/dev/null | tail -1
export PATH="$CUDA_HOME/bin:$PATH"
export TORCH_CUDA_ARCH_LIST="8.0"
export MAX_JOBS=8

echo "=== 2. 装 KJNodes 依赖 ==="
$PIP install -q pillow color-matcher matplotlib mss opencv-python-headless 2>&1 | tail -3

echo "=== 3. 编译安装 SageAttention 2.2 ==="
$PIP install sageattention==2.2.0 --no-build-isolation 2>&1 | tail -25

echo "=== 4. 验证符号 ==="
$PY - <<'PYEOF'
from sageattention.core import per_thread_int8_triton, per_warp_int8_cuda, per_block_int8_triton, get_cuda_arch_versions
import sageattention
print("SAGE_IMPORT_OK", getattr(sageattention, "__version__", "?"))
PYEOF
