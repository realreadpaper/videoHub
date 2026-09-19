#!/bin/bash
set -u
W=/workspace; V=$W/venv; C=$W/ComfyUI
step() { echo; echo "########## $(date +%T) $* ##########"; }

step "1/4 重建 venv"
rm -rf $V
python3 -m venv $V
$V/bin/pip install -q --upgrade pip wheel setuptools
$V/bin/python -V; $V/bin/pip -V

step "2/4 torch cu130"
$V/bin/pip install torch==2.14.0+cu130 torchvision==0.29.0+cu130 torchaudio==2.11.0+cu130 \
    --index-url https://download.pytorch.org/whl/cu130 2>&1 | tail -3
$V/bin/python -c "import torch;print('torch',torch.__version__,'cuda',torch.version.cuda,'gpus',torch.cuda.device_count(),torch.cuda.get_device_name(0))"

step "3/4 ComfyUI 依赖"
$V/bin/pip install -r $W/dl/requirements_headless.txt 2>&1 | tail -3

step "4/4 节点依赖"
grep -viE "^(torch|torchvision|torchaudio|numpy|#)" $C/custom_nodes/comfyui-minimax-h3-audio-T8/requirements.txt > $W/dl/node_req.txt
$V/bin/pip install -r $W/dl/node_req.txt 2>&1 | tail -3

step "完成校验"
$V/bin/python -c "import torch,comfy;print('torch',torch.__version__,'cuda',torch.version.cuda)"
