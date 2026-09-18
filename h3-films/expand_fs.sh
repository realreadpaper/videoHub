#!/bin/bash
# expand_fs.sh — 识别宿主机扩容后的系统盘，扩展分区与文件系统
# 用法： bash /root/expand_fs.sh
# 退出码： 0=扩容成功  2=块设备未变大(宿主侧未生效/需重启)  3=growpart失败  4=resize2fs失败
set -u
LOG=/root/expand_fs.log
exec > >(tee "$LOG") 2>&1
echo "=== 扩容处理 $(date) ==="

DEV=/dev/vda
PART=${DEV}1

SECT=$(cat /sys/block/${DEV##*/}/size)
BYTES=$((SECT * 512))
GIB=$((BYTES / 1073741824))
echo "块设备 ${DEV} 当前容量: ${GIB} GiB (${BYTES} bytes)"

if [ "$BYTES" -le 107374182400 ]; then
  echo "!!! 宿主侧扩容尚未落到块设备：仍为 100GiB"
  echo "!!! 原因：virtio-blk 无在线 rescan，且 guest 内 reboot 不会重建 QEMU 进程"
  echo "!!! 处置：控制台【关机】-> 等状态变已关机 ->【开机】（stop/start，不是重启）"
  echo "!!!       开机后重跑本脚本；若控制台未显示 150G 则扩容单未落地，先找平台确认"
  exit 2
fi

echo "--- 扩容前 ---"
df -h / | tail -1
parted -s "$DEV" unit GiB print | tail -3

echo "--- growpart ${DEV} 1 ---"
if ! growpart "$DEV" 1; then
  echo "!!! growpart 失败，回退 parted resizepart（脚本模式自动应答）"
  parted -s "$DEV" resizepart 1 100% || { echo "!!! parted 回退也失败"; exit 3; }
fi
partprobe "$DEV" 2>/dev/null || true
sleep 1
lsblk "$DEV"

echo "--- resize2fs ${PART} ---"
resize2fs "$PART" || { echo "!!! resize2fs 失败"; exit 4; }

echo "--- 扩容后 ---"
df -h / | tail -1
df -BG --output=avail / | tail -1
echo "=== 完成 $(date) ==="
