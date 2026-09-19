#!/usr/bin/env bash
# ============================================================
# 01_provision_os.sh — 系统层准备（apt 工具 / swap / 内核调优 / 驱动核对）
# 在目标机 root 下执行。幂等，可重复跑。
#
# 目标机参考：Ubuntu 22.04.2 LTS / 内核 5.15 / 16 核 / 125 GB RAM / 148 GB 盘
#             2 × A100-PCIE-40GB / 驱动 580.95.05
# ============================================================
set -eu

WORKSPACE=${WORKSPACE:-/workspace}
SWAP_MB=${SWAP_MB:-8192}

say() { printf '\n########## %s ##########\n' "$*"; }

say "1/5 apt 基础工具"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
  ffmpeg aria2 git curl wget rsync vim htop tmux \
  python3 python3-venv python3-dev build-essential pkg-config \
  sqlite3 unzip jq
echo "  ffmpeg : $(ffmpeg -version 2>/dev/null | head -1)"
echo "  aria2c : $(command -v aria2c)"

say "2/5 目录规范（与旧机保持一致，脚本里写死了这些路径）"
mkdir -p "$WORKSPACE"/{ComfyUI,venv,trilogy,dy_key,dl,logs,opt}
mkdir -p /root/s2
echo "  已建立： $WORKSPACE/{ComfyUI,venv,trilogy,dy_key,dl,logs,opt}  /root/s2"

say "3/5 swap 兜底（防 OOM kill，不是扩内存）"
if swapon --show | grep -q .; then
  echo "  已有 swap： $(swapon --show=NAME,SIZE --noheadings | tr '\n' ' ')"
else
  if [ ! -f /swapfile ]; then
    fallocate -l "${SWAP_MB}M" /swapfile || dd if=/dev/zero of=/swapfile bs=1M count="$SWAP_MB"
    chmod 600 /swapfile
    mkswap /swapfile
  fi
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  cat > /etc/sysctl.d/99-swap.conf <<'EOF'
vm.swappiness=10
EOF
  echo "  ✓ swap ${SWAP_MB} MB 已启用并写入 /etc/fstab + /etc/sysctl.d/99-swap.conf"
  echo "  ★ 注意：swap 只是兜底。真开始用 swap 会慢到像卡死，不要当容量用。"
fi

say "4/5 内核网络调优（BBR）—— 跨机房回传的关键，实测 0.11 → 6 MB/s"
cat > /etc/sysctl.d/99-net-speed.conf <<'EOF'
net.ipv4.tcp_congestion_control=bbr
net.core.wmem_max=16777216
net.core.rmem_max=16777216
net.ipv4.tcp_wmem=4096 65536 16777216
net.ipv4.tcp_rmem=4096 65536 16777216
EOF
sysctl --system >/dev/null 2>&1 || true
echo "  congestion_control = $(sysctl -n net.ipv4.tcp_congestion_control)"
echo "  default_qdisc      = $(sysctl -n net.core.default_qdisc)"
echo "  ★ 若无 bbr，先确认内核模块： modprobe tcp_bbr && lsmod | grep bbr"

say "5/5 NVIDIA 驱动核对"
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=index,name,driver_version,memory.total --format=csv,noheader | sed 's/^/  /'
  echo "  驱动满足（>=580 即可，torch cu130 自带 CUDA 13 运行时）"
else
  cat <<'EOM'
  ✗ 没有 nvidia-smi。驱动安装方式按云厂商给：华为云/阿里云通常用厂商镜像自带的
    GRID/vGPU 或标准驱动；裸装可用：
      wget https://us.download.nvidia.com/tesla/580.95.05/NVIDIA-Linux-x86_64-580.95.05.run
      sh NVIDIA-Linux-x86_64-580.95.05.run --silent --dkms
    旧机上留着安装包： /root/nvidia-580.95.05.run （396 MB）
    装完重跑本脚本确认。
EOM
fi

cat <<'EOM'

============================================================
系统层完成。下一步：
  1) 把仓库里的 deploy/ 目录拷到目标机（或直接在目标机 clone 仓库）
  2) bash 02_build_stack.sh        # venv + torch + ComfyUI + 自定义节点
  3) bash 03_dl_weights.sh         # 下载 6 个权重（约 71 GB）
  4) bash 04_launch_comfy.sh both  # 起双实例
EOM
