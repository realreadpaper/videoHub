#!/usr/bin/env bash
# ============================================================
# 01c_gpu_driver.sh — 安装 NVIDIA 驱动（≥580，torch cu130 的前提）
#
# 背景：01_provision_os.sh 只**核对**驱动，不装。裸机/新租实例上来时
#  nvidia-smi 往往不存在，而后面每一步（torch.cuda、ComfyUI 启动）都依赖它。
#  本脚本把「装驱动」这一步补齐，幂等可重复跑。
#
# 实测目标机（2026-09-19 gpu1）：Ubuntu 24.04.3 / 内核 6.14.0-35-generic /
#  KVM 直通 A100-PCIE-40GB（PCI 10de:20f1）/ apt 源内有 nvidia-driver-580-server
#
# 用法： bash 01c_gpu_driver.sh          # 装完自动判断是否需要重启
#        DRV=590 bash 01c_gpu_driver.sh  # 换版本
#        REBOOT=1 bash 01c_gpu_driver.sh # 装完自动重启
# ============================================================
set -eu

DRV=${DRV:-580}
REBOOT=${REBOOT:-0}
TARGET="nvidia-driver-${DRV}-server"

say() { printf '\n########## %s ##########\n' "$*"; }

# ---------------------------------------------------------------
say "0/5 现状核对"
echo "  内核        : $(uname -r)"
echo "  发行版      : $(. /etc/os-release && echo "$PRETTY_NAME")"
echo "  GPU(PCI)    : $(lspci -nn 2>/dev/null | grep -i 'nvidia' | head -1)"
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1; then
  echo "  ✓ 驱动已在位，无需安装："
  nvidia-smi --query-gpu=index,name,driver_version,memory.total --format=csv,noheader | sed 's/^/      /'
  exit 0
fi
if ! lspci -nn 2>/dev/null | grep -qi nvidia; then
  echo "  ✗ PCI 上看不到 NVIDIA 设备 —— 宿主机没做直通，装驱动也没用，先找云厂商。"
  exit 1
fi
CAND=$(apt-cache policy "$TARGET" 2>/dev/null | awk '/Candidate/{print $2}')
[ -n "$CAND" ] && echo "  待装        : $TARGET = $CAND" || {
  echo "  ✗ apt 源里没有 $TARGET。先确认 apt 源（01b_net_tune.sh），或改用官方 runfile。"; exit 1; }

# ---------------------------------------------------------------
say "1/5 构建依赖（DKMS 需要内核头）"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq dkms pkg-config "linux-headers-$(uname -r)" 2>&1 | tail -3
echo "  dkms $(dkms --version 2>/dev/null | head -1) · headers $(test -d /usr/src/linux-headers-$(uname -r) && echo OK || echo MISSING)"

# ---------------------------------------------------------------
say "2/5 屏蔽 nouveau（它现在很可能已占用 GPU，必须重启才能让位）"
if lsmod | grep -q '^nouveau'; then
  echo "  ⚠ nouveau 正在加载 —— 装完必须重启，否则 nvidia 模块加载不上"
  NEED_REBOOT=1
else
  NEED_REBOOT=0
fi
cat > /etc/modprobe.d/blacklist-nouveau.conf <<'EOF'
# 装 NVIDIA 专有驱动后 nouveau 必须让位
blacklist nouveau
options nouveau modeset=0
EOF
update-initramfs -u 2>&1 | tail -2 || true

# ---------------------------------------------------------------
say "3/5 安装 $TARGET"
# -server 变体不带 X11/桌面组件，服务器上更干净
apt-get install -y "$TARGET" 2>&1 | tail -12

say "4/5 校验安装产物"
dkms status 2>/dev/null | sed 's/^/      /' || true
echo "  内核模块包   : $(dpkg -l | awk '/nvidia.*kernel|linux-modules-nvidia/{print $2" "$3}' | tr '\n' ' ')"
echo "  nvidia-smi   : $(command -v nvidia-smi || echo '(装上了但 PATH 里没有)')"
echo "  内核模块 .ko : $(find /lib/modules/$(uname -r) -name 'nvidia.ko*' 2>/dev/null | head -3 | tr '\n' ' ')"

say "5/5 尝试加载模块"
if modprobe nvidia 2>/dev/null; then
  echo "  ✓ modprobe nvidia 成功"
  nvidia-smi --query-gpu=index,name,driver_version,memory.total --format=csv,noheader | sed 's/^/      /'
  NEED_REBOOT=0
else
  echo "  ✗ modprobe 失败（nouveau 仍占用或模块未装）→ 需要重启"
  NEED_REBOOT=1
fi

echo
if [ "$NEED_REBOOT" = "1" ]; then
  echo "=========== 需要重启 ==========="
  echo "  reboot 后执行： nvidia-smi && bash $(basename "$0")   # 复跑应打印『驱动已在位』"
  [ "$REBOOT" = "1" ] && { echo "  REBOOT=1 → 3 秒后重启"; sleep 3; reboot; }
else
  echo "=========== 驱动就绪 ==========="
  echo "  下一步： bash 02_build_stack.sh"
fi
