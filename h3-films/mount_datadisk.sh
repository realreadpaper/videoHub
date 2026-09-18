#!/bin/bash
# mount_datadisk.sh — 把新挂载的数据盘接入为 /workspace（彻底绕开系统盘扩容）
#
#   bash mount_datadisk.sh                      # 演练：只探测，绝对不动手
#   bash mount_datadisk.sh --go                 # 实际执行（默认 mode=workspace）
#   bash mount_datadisk.sh --go --device /dev/vdb --mode workspace
#   bash mount_datadisk.sh --go --mode models   # 只把 models 目录独立出去
#   bash mount_datadisk.sh --restore            # 回滚到用根盘上的旧目录
#
# mode=workspace : 整块盘挂到 /workspace（推荐，权重+输出都宽敞）
# mode=models    : 只挂到 /workspace/ComfyUI/models
#
# 退出码: 0=成功 2=找不到候选盘 3=设备不安全 4=执行失败
set -u

LOG=/root/mount_datadisk.log
exec > >(tee "$LOG") 2>&1

GO=0
MODE=workspace
DEV=""
RESTORE=0
FORCE_FMT=0

while [ $# -gt 0 ]; do
  case "$1" in
    --go) GO=1 ;;
    --mode) MODE="$2"; shift ;;
    --device) DEV="$2"; shift ;;
    --force-format) FORCE_FMT=1 ;;
    --restore) RESTORE=1 ;;
    *) echo "未知参数: $1"; exit 1 ;;
  esac
  shift
done

ROOT_SRC=$(findmnt -n -o SOURCE / )
echo "=== mount_datadisk $(date)  mode=$MODE  go=$GO ==="
echo "根分区设备: $ROOT_SRC"

# ---------------- 回滚 ----------------
if [ "$RESTORE" = "1" ]; then
  echo "--- 回滚：卸载新盘，恢复旧目录 ---"
  for M in /workspace /workspace/ComfyUI/models; do
    if findmnt -n -o SOURCE "$M" 2>/dev/null | grep -q "^/dev/v"; then
      U=$(findmnt -n -o UUID "$M")
      echo "卸载 $M (uuid=$U)"
      umount "$M" || { echo "!!! umount $M 失败"; exit 4; }
    fi
  done
  sed -i '/# h3-datadisk/d' /etc/fstab
  [ -d /workspace.old ] && { echo "恢复 /workspace.old -> /workspace"; rm -rf /workspace; mv /workspace.old /workspace; }
  [ -d /workspace/ComfyUI/models.old ] && { echo "恢复 models.old"; rm -rf /workspace/ComfyUI/models; mv /workspace/ComfyUI/models.old /workspace/ComfyUI/models; }
  echo "--- 回滚后 ---"; df -h / /workspace 2>/dev/null | tail -3
  exit 0
fi

# ---------------- 探测候选盘 ----------------
echo
echo "--- 全部块设备 ---"
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT,SERIAL

if [ -z "$DEV" ]; then
  # 排除：根盘所在设备、loop、以及已挂载者
  ROOTDISK=$(lsblk -no PKNAME "$ROOT_SRC" 2>/dev/null | head -1)
  for D in $(lsblk -nd -o NAME,TYPE | awk '$2=="disk"{print $1}'); do
    [ "$D" = "$ROOTDISK" ] && continue
    case "$D" in loop*) continue ;; esac
    DEV="/dev/$D"
    break
  done
fi

if [ -z "$DEV" ] || [ ! -b "$DEV" ]; then
  echo "!!! 找不到候选数据盘。请先在华为云控制台把数据盘【挂载】到本实例。"
  echo "!!! 挂载后无需重启，块设备会热插拔出现（/dev/vdb）。"
  exit 2
fi
echo "选中设备: $DEV"

# ---------------- 安全闸 ----------------
ROOTDISK=$(lsblk -no PKNAME "$ROOT_SRC" 2>/dev/null | head -1)
CAND=$(basename "$DEV")
if [ "$CAND" = "$ROOTDISK" ]; then
  echo "!!! 拒绝：$DEV 是承载根文件系统的设备（$ROOT_SRC）"
  exit 3
fi
if findmnt -n -o SOURCE -S "$DEV" >/dev/null 2>&1; then
  echo "!!! 拒绝：$DEV 正在挂载中"
  exit 3
fi

EXIST_FS=$(blkid -o value -s TYPE "$DEV" 2>/dev/null || true)
SIZE_B=$(blockdev --getsize64 "$DEV")
echo "容量: $((SIZE_B/1073741824)) GiB   现有文件系统: ${EXIST_FS:-<空>}"

if [ -n "$EXIST_FS" ] && [ "$FORCE_FMT" != "1" ]; then
  echo ">>> 该盘已有文件系统（$EXIST_FS），将【直接复用，不格式化】"
  FMT=0
elif [ -n "$EXIST_FS" ] && [ "$FORCE_FMT" = "1" ]; then
  echo ">>> --force-format：将【格式化】$DEV，其上数据全部丢失"
  FMT=1
else
  echo ">>> 空盘，将创建 ext4"
  FMT=1
fi

if [ "$GO" != "1" ]; then
  echo
  echo "=================== 演练结束（未做任何改动）==================="
  echo "确认无误后加 --go 实际执行。将执行的动作："
  echo "  1) ${FMT:+mkfs.ext4 -m 1 -L h3data $DEV  # 格式化}${FMT:-复用现有 $EXIST_FS}"
  echo "  2) 挂到 /mnt/h3new，用 cp -a 把数据搬过去并逐项校验"
  echo "  3) 原目录改名 .old，新盘按 UUID 挂到目标位置，写入 fstab(nofail)"
  echo "  4) 校验通过后提示你手动删除 .old 释放根盘空间"
  exit 0
fi

# ---------------- 执行 ----------------
set -e
STAGE=/mnt/h3new
mkdir -p "$STAGE"

if [ "$FMT" = "1" ]; then
  echo "--- mkfs.ext4 $DEV ---"
  mkfs.ext4 -F -m 1 -L h3data "$DEV"
fi

echo "--- 试挂 ---"
mount "$DEV" "$STAGE"
NEWUUID=$(blkid -o value -s UUID "$DEV")
echo "新盘 UUID=$NEWUUID"

if [ "$MODE" = "workspace" ]; then
  SRC=/workspace
  DST_MNT=/workspace
else
  SRC=/workspace/ComfyUI/models
  DST_MNT=/workspace/ComfyUI/models
fi
echo "迁移: $SRC  ->  $DEV"

echo "--- 拷贝中（大文件，耐心等）---"
SRC_BYTES=$(du -sb "$SRC" | cut -f1)
if command -v rsync >/dev/null 2>&1; then
  rsync -a --info=progress2 "$SRC"/ "$STAGE"/
else
  cp -a "$SRC"/. "$STAGE"/
fi
sync

echo "--- 校验 ---"
DST_BYTES=$(du -sb "$STAGE" | cut -f1)
SRC_N=$(find "$SRC" | wc -l)
DST_N=$(find "$STAGE" | wc -l)
echo "源: ${SRC_BYTES} 字节 / ${SRC_N} 个条目"
echo "新: ${DST_BYTES} 字节 / ${DST_N} 个条目"
if [ "$DST_BYTES" -lt "$SRC_BYTES" ] || [ "$DST_N" -lt "$SRC_N" ]; then
  echo "!!! 校验不通过（新盘内容少于源），中止，不做切换。"
  umount "$STAGE"
  exit 4
fi
echo "校验通过"

echo "--- 切换 ---"
umount "$STAGE"
mv "$SRC" "${SRC}.old"
mkdir -p "$DST_MNT"
mount "$DEV" "$DST_MNT"
echo "$NEWUUID $DST_MNT ext4 defaults,nofail 0 2 # h3-datadisk" >> /etc/fstab
systemctl daemon-reload 2>/dev/null || true
mount -a 2>/dev/null || true

echo "--- 结果 ---"
df -h / "$DST_MNT"
echo "fstab:"; grep "h3-datadisk" /etc/fstab
echo
echo "=== 完成 ==="
echo "旧目录仍在 ${SRC}.old（占根盘）。确认业务正常后手动删除："
echo "    rm -rf ${SRC}.old"
echo "如需回滚： bash $0 --restore"
