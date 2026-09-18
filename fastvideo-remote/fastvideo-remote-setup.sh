#!/usr/bin/env bash
# ============================================================================
#  fastvideo-remote-setup.sh  —  FastVideo 远程服务器一键建环境
# ----------------------------------------------------------------------------
#  做四件事：① 拿到仓库 ② 装 uv ③ 建 Python 3.12 虚拟环境 ④ 安装 fastvideo
#  幂等：重复运行不会出错，已完成的步骤会跳过。
#
#  用法:
#      bash fastvideo-remote-setup.sh                          # 默认 cu126 + 自动选镜像
#      bash fastvideo-remote-setup.sh --cuda 130               # CUDA 13 环境
#      bash fastvideo-remote-setup.sh --dir /data --no-mirror  # 指定目录 + 不用镜像
#      bash fastvideo-remote-setup.sh --help
#
#  重要: uv 会自己下载所需的 Python 3.12，所以即使系统装的是 3.13 也没问题。
# ============================================================================

set -uo pipefail

INSTALL_DIR="${HOME}/FastVideo"
CUDA_TAG="cu126"
HF_HOME_DIR=""
USE_MIRROR="auto"
DO_KERNEL="no"
REPO_URL="https://github.com/hao-ai-lab/FastVideo.git"

usage() {
  cat <<'EOF'

 用法:
     bash fastvideo-remote-setup.sh                          # 默认 cu126 + 自动选镜像
     bash fastvideo-remote-setup.sh --cuda 130               # CUDA 13 环境
     bash fastvideo-remote-setup.sh --dir /data --no-mirror  # 指定目录 + 不用镜像
     bash fastvideo-remote-setup.sh --help

 重要: uv 会自己下载所需的 Python 3.12，所以即使系统装的是 3.13 也没问题。

 可选参数:
    --dir PATH        安装目录（默认 ~/FastVideo）
    --cuda 126|130    CUDA 后端（默认 126）
    --hf-home PATH    权重缓存目录（默认与安装目录同级，便于挂持久盘）
    --mirror          强制使用 HF 国内镜像
    --no-mirror       强制不用镜像
    --with-kernel     顺便编译 VSA/STA 自定义内核（耗时 5–10 分钟）
    --help            显示本帮助
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --dir)        INSTALL_DIR="$2"; shift 2 ;;
    --cuda)       CUDA_TAG="cu$2"; shift 2 ;;
    --hf-home)    HF_HOME_DIR="$2"; shift 2 ;;
    --mirror)     USE_MIRROR="yes"; shift ;;
    --no-mirror)  USE_MIRROR="no"; shift ;;
    --with-kernel) DO_KERNEL="yes"; shift ;;
    --help|-h)    usage; exit 0 ;;
    *) echo "未知参数: $1"; usage; exit 1 ;;
  esac
done

if [ -t 1 ]; then
  R=$'\033[31m'; G=$'\033[32m'; Y=$'\033[33m'; C=$'\033[36m'; N=$'\033[0m'; B=$'\033[1m'
else
  R=''; G=''; Y=''; C=''; N=''; B=''
fi
step() { printf "\n${B}${C}▶ %s${N}\n" "$1"; }
ok()   { printf "  ${G}✔${N} %s\n" "$1"; }
wa()   { printf "  ${Y}▲${N} %s\n" "$1"; }
er()   { printf "  ${R}✘${N} %s\n" "$1"; }
die()  { er "$1"; exit 1; }

# ---------------------------------------------------------------- 0. 前置检查
step "0/5  前置检查"

[ "$(uname -s)" = "Linux" ] || die "操作系统不是 Linux（当前 $(uname -s)）。CUDA 路径只支持 Linux 或 WSL。"
ok "操作系统: Linux"

command -v nvidia-smi >/dev/null 2>&1 || die "找不到 nvidia-smi。先装 NVIDIA 驱动，容器内还需 --gpus all。"
GPU_NAME="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 | xargs)"
GPU_N="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | grep -c .)"
ok "GPU: ${GPU_N} × ${GPU_NAME:-未知}"

if [ -z "$HF_HOME_DIR" ]; then
  HF_HOME_DIR="$(dirname "$INSTALL_DIR")/hf_cache"
fi
ok "安装目录: $INSTALL_DIR"
ok "权重缓存: $HF_HOME_DIR"

# ---------------------------------------------------------------- 1. 仓库
step "1/5  获取代码"

if ! command -v git >/dev/null 2>&1; then
  wa "没装 git，尝试用包管理器安装"
  if command -v apt-get >/dev/null 2>&1; then
    (sudo apt-get update -qq && sudo apt-get install -y -qq git) || die "git 安装失败，请手动装"
  elif command -v yum >/dev/null 2>&1; then
    sudo yum install -y -q git || die "git 安装失败，请手动装"
  else
    die "无法自动安装 git，请手动安装后重试"
  fi
fi
ok "git: $(git --version)"

if [ -d "$INSTALL_DIR/.git" ]; then
  ok "仓库已存在，拉取最新代码"
  git -C "$INSTALL_DIR" pull --ff-only 2>&1 | sed 's/^/     /' || wa "拉取失败，继续用现有版本"
elif [ -d "$INSTALL_DIR" ] && [ -n "$(ls -A "$INSTALL_DIR" 2>/dev/null)" ]; then
  wa "$INSTALL_DIR 已存在且非空，但不是 git 仓库 —— 跳过克隆，直接在其中安装"
else
  ok "克隆仓库到 $INSTALL_DIR"
  mkdir -p "$(dirname "$INSTALL_DIR")"
  git clone --depth 1 "$REPO_URL" "$INSTALL_DIR" 2>&1 | tail -3 | sed 's/^/     /' \
    || die "克隆失败，检查网络或改用 --dir 指定已有仓库"
fi
cd "$INSTALL_DIR" || die "无法进入 $INSTALL_DIR"

# ---------------------------------------------------------------- 2. uv
step "2/5  准备 uv 与 Python 3.12"

export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
if command -v uv >/dev/null 2>&1; then
  ok "uv 已存在: $(uv --version)"
else
  ok "安装 uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh 2>&1 | tail -5 | sed 's/^/     /' \
    || die "uv 安装失败，可手动执行: pip install uv"
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
  command -v uv >/dev/null 2>&1 || die "uv 装好了但不在 PATH，请重开终端或手动 export PATH"
  ok "uv 安装完成: $(uv --version)"
fi

# uv 自带 Python 管理：3.13 的机器也能拉出 3.12
if [ -d ".venv" ] && [ -x ".venv/bin/python" ]; then
  VENV_PY="$(.venv/bin/python -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null)"
  if [ "$VENV_PY" = "3.12" ] || [ "$VENV_PY" = "3.11" ] || [ "$VENV_PY" = "3.10" ]; then
    ok "已有虚拟环境 Python $VENV_PY，复用"
  else
    wa "已有虚拟环境 Python $VENV_PY 不符合要求，重建"
    rm -rf .venv
  fi
fi

if [ ! -d ".venv" ]; then
  ok "创建 Python 3.12 虚拟环境（uv 会自动下载解释器，与系统 Python 版本无关）"
  uv venv --python 3.12 --seed 2>&1 | tail -5 | sed 's/^/     /' \
    || die "建虚拟环境失败"
fi

# shellcheck disable=SC1091
. .venv/bin/activate || die "激活虚拟环境失败"
ok "当前 Python: $(python -V 2>&1)"

# ---------------------------------------------------------------- 3. 镜像
step "3/5  配置权重下载通道"

ENDPOINT=""
if [ "$USE_MIRROR" = "auto" ]; then
  if curl -s -o /dev/null -m 10 "https://huggingface.co/api/models/FastVideo/FastWan2.1-T2V-1.3B-Diffusers" 2>/dev/null; then
    ok "HuggingFace 直连可用，不启用镜像"
  else
    wa "HuggingFace 直连不可达，自动切换国内镜像"
    ENDPOINT="https://hf-mirror.com"
  fi
elif [ "$USE_MIRROR" = "yes" ]; then
  ENDPOINT="https://hf-mirror.com"
  ok "按参数强制使用镜像: $ENDPOINT"
else
  ok "按参数不使用镜像"
fi

mkdir -p "$HF_HOME_DIR"
HF_PROFILE="${INSTALL_DIR}/.fastvideo-env.sh"
cat > "$HF_PROFILE" <<EOF
# FastVideo 环境变量 —— 由 fastvideo-remote-setup.sh 生成
# 用法: source $HF_PROFILE
export HF_HOME="$HF_HOME_DIR"
export HF_HUB_CACHE="$HF_HOME_DIR"
export TRANSFORMERS_CACHE="$HF_HOME_DIR"
export HF_HUB_ENABLE_HF_TRANSFER=1
export FASTVIDEO_MODEL_ROOT="$HF_HOME_DIR"
${ENDPOINT:+export HF_ENDPOINT="$ENDPOINT"}
EOF
ok "环境变量写入 $HF_PROFILE"
# shellcheck disable=SC1090
. "$HF_PROFILE"

if ! grep -q "fastvideo-env.sh" "$HOME/.bashrc" 2>/dev/null; then
  printf '\n# FastVideo\n[ -f "%s" ] && . "%s"\n' "$HF_PROFILE" "$HF_PROFILE" >> "$HOME/.bashrc"
  ok "已写入 ~/.bashrc，重开终端后永久生效"
fi

# ---------------------------------------------------------------- 4. 安装
step "4/5  安装 fastvideo"

export UV_TORCH_BACKEND="$CUDA_TAG"
ok "PyTorch 后端: $CUDA_TAG（对应 CUDA ${CUDA_TAG#cu} 的 wheel）"

uv pip install -e . 2>&1 | tail -12 | sed 's/^/     /' || die "安装失败，检查上方报错"
ok "fastvideo 安装完成"

if python -c "import fastvideo; print('OK')" >/dev/null 2>&1; then
  ok "import 验证通过"
else
  wa "import 失败 —— 可能是 PyTorch 后端与驱动不匹配，跑 doctor 脚本复核"
fi

if [ "$DO_KERNEL" = "yes" ]; then
  if [ -d "fastvideo-kernel" ] && [ -x "fastvideo-kernel/build.sh" ]; then
    ok "编译自定义内核（VSA / STA），预计 5–10 分钟"
    (cd fastvideo-kernel && ./build.sh) 2>&1 | tail -8 | sed 's/^/     /' \
      || wa "内核编译失败 —— 不影响基础推理，可先用 FLASH_ATTN 后端"
    ok "内核步骤结束"
  else
    wa "找不到 fastvideo-kernel/build.sh，跳过"
  fi
else
  wa "跳过自定义内核编译（要用 VSA 稀疏注意力再加 --with-kernel 重跑，或直接用 FLASH_ATTN）"
fi

# ---------------------------------------------------------------- 5. 完成
step "5/5  完成"

cat <<EOF

  ${B}环境已就绪。每次开新终端先执行：${N}
      cd $INSTALL_DIR && source .venv/bin/activate

  ${B}下载模型权重（示例：FastWan 2.1 T2V 1.3B，约 27 GB）：${N}
      hf download FastVideo/FastWan2.1-T2V-1.3B-Diffusers \\
        --local-dir $HF_HOME_DIR/FastWan2.1-T2V-1.3B-Diffusers

  ${B}跑第一支片：${N}
      fastvideo generate --config $INSTALL_DIR/examples/inference/basic/basic.py
      或直接用你配置好的 YAML（见 fastvideo-configs/ 目录）

  ${B}起服务：${N}
      fastvideo serve --config <你的 serve 配置>.yaml

  ${B}本地连接这个远程服务（在你自己电脑上执行）：${N}
      ssh -N -L 8000:127.0.0.1:8000 <用户名>@<服务器IP>

${B}提醒：${N}这套环境要长期用的话，建议用 tmux 保持会话，别直接挂在 SSH 上。

EOF
