#!/bin/bash
# 泰国机房(华为) · H3 一步直出运行时重建
# 源：本地快照 github/h3-remote-snapshot（ComfyUI f42b24ef / T8 节点 e12d8af / torch 2.14.0+cu130）
set -u
W=/workspace
V=$W/venv
C=$W/ComfyUI
COMFY_COMMIT=f42b24efbeee194513fff465d84ad6913a2698d5
NODE_COMMIT=e12d8af8ac85540da9895cb629836a4947e221ca

step() { echo; echo "########## $(date +%T) $* ##########"; }

step "1/6 建 venv"
python3 -m venv $V
$V/bin/pip install -q --upgrade pip wheel setuptools
$V/bin/python -V

step "2/6 装 torch cu130（走 pytorch 官方 cu130 索引，PyPI 默认源给的是非 cu130 构建）"
$V/bin/pip install torch==2.14.0+cu130 torchvision==0.29.0+cu130 torchaudio==2.11.0+cu130 \
    --index-url https://download.pytorch.org/whl/cu130
$V/bin/python -c "import torch;print('torch',torch.__version__,'cuda',torch.version.cuda,'gpu',torch.cuda.get_device_name(0),'x',torch.cuda.device_count())"

step "3/6 clone ComfyUI 并锁定 commit"
if [ ! -d $C/.git ]; then
  mkdir -p $C && cd $C && git init -q && git remote add origin https://github.com/comfyanonymous/ComfyUI.git
  git fetch --depth 1 origin $COMFY_COMMIT && git checkout -q FETCH_HEAD
fi
git -C $C log -1 --oneline

step "4/6 装 ComfyUI 依赖（headless 版，与源机器一致）"
$V/bin/pip install -q -r $W/dl/requirements_headless.txt

step "5/6 clone T8 自定义节点并锁定 commit"
cd $C/custom_nodes
git clone -q https://github.com/T8mars/comfyui-minimax-h3-audio-T8.git
cd comfyui-minimax-h3-audio-T8 && git checkout -q $NODE_COMMIT
git log -1 --oneline

step "6/6 装节点依赖（跳过自带 torch 相关，避免覆盖 cu130）"
grep -viE "^(torch|torchvision|torchaudio|numpy|#)" $C/custom_nodes/comfyui-minimax-h3-audio-T8/requirements.txt > $W/dl/node_req.txt
cat $W/dl/node_req.txt
$V/bin/pip install -q -r $W/dl/node_req.txt

step "完成"
$V/bin/python -c "import torch;print('FINAL torch',torch.__version__,torch.version.cuda, torch.cuda.device_count(),'GPU(s)')"
