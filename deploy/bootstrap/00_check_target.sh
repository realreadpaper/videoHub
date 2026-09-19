#!/usr/bin/env bash
# ============================================================
# 00_check_target.sh — 目标机体检（只读，不改任何东西）
# 在新服务器上新开一台机器后**第一件事**跑这个。
# 用法： ssh <新机别名> 'bash -s' < 00_check_target.sh
#        或在目标机上： bash 00_check_target.sh
# ============================================================
set -u

ok()   { printf '  [ OK ] %s\n' "$*"; }
warn() { printf '  [WARN] %s\n' "$*"; }
bad()  { printf '  [FAIL] %s\n' "$*"; }

echo "=========== 0. 基本信息 ==========="
echo "hostname : $(hostname)"
echo "os       : $(. /etc/os-release 2>/dev/null && echo "$PRETTY_NAME")"
echo "kernel   : $(uname -r)"
echo "cpu      : $(nproc) 核"
echo "mem      : $(free -g | awk '/^Mem:/{print $2" GB (available "$7" GB)"}')"
echo "swap     : $(free -g | awk '/^Swap:/{print $2" GB"}')"
echo "disk     :"
df -h / /workspace 2>/dev/null | sed 's/^/           /'

echo
echo "=========== 1. GPU ==========="
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=index,name,memory.total,driver_version,compute_cap \
             --format=csv,noheader | sed 's/^/  /'
  GPU_N=$(nvidia-smi --query-gpu=name --format=csv,noheader | wc -l)
  [ "$GPU_N" -ge 1 ] && ok "检测到 $GPU_N 张卡" || bad "没检测到 GPU"
  if [ "$GPU_N" -eq 1 ]; then
    echo "           → 形态判定：【单卡模式】。启动用 04_launch_comfy.sh single；"
    echo "             跑批用 deploy/single-gpu/ 下的脚本。单卡不需要 instance_b.db。"
  else
    echo "           → 形态判定：【多卡模式】。启动用 04_launch_comfy.sh both。"
    echo "             ★ 单卡脚本别在双卡机器上照抄：只在 GPU0 上跑，另一张卡全程闲置。"
  fi
  CAP=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader | head -1 | tr -d ' ')
  case "$CAP" in
    7.5|8.0|8.6|8.9|9.0|10.*|12.*) ok "compute capability $CAP 满足（需 >= 7.5）" ;;
    *) bad "compute capability $CAP 不满足（需 >= 7.5；bf16 需 >= 8.0）" ;;
  esac
  VRAM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1)
  [ "${VRAM:-0}" -ge 21504 ] && ok "单卡显存 ${VRAM} MiB 满足（需 >= 21 GB）" \
                             || bad "单卡显存 ${VRAM} MiB 不足（需 >= 21 GB）"
  DRV=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1)
  echo "           参考机型驱动： 580.95.05（CUDA 13.0）。torch 自带 CUDA 13 运行时，"
  echo "           系统无需安装 CUDA Toolkit；但驱动版本必须 >= 580。"
else
  bad "nvidia-smi 不存在：先装 NVIDIA 驱动（见 01_provision_os.sh）"
fi

echo
echo "=========== 2. 必备工具 ==========="
for t in python3 pip3 ffmpeg git rsync curl wget aria2c; do
  if command -v "$t" >/dev/null 2>&1; then
    ok "$t  → $(command -v $t)"
  else
    warn "$t 缺失（01_provision_os.sh 会补）"
  fi
done
echo "           python3 版本需 >= 3.10： $(python3 -V 2>&1)"
echo "           ffmpeg 必须存在 —— T8 的 MiniMaxH3SafeAVSaveT8Advanced 存 H.264 长视频依赖它"

echo
echo "=========== 3. 网络（决定权重下载与成片回传速度）==========="
if [ -f /etc/sysctl.d/99-net-speed.conf ]; then
  ok "已装 BBR 调优 (/etc/sysctl.d/99-net-speed.conf)"
else
  warn "未装 BBR 调优 —— 跨境回传会慢 10~50 倍，见 01_provision_os.sh"
fi
echo "           当前拥塞控制： $(sysctl -n net.ipv4.tcp_congestion_control 2>/dev/null)"
echo "           default_qdisc ： $(sysctl -n net.core.default_qdisc 2>/dev/null)"

echo
echo "=========== 4. 已有资产是否到位 ==========="
for p in /workspace/ComfyUI /workspace/venv /root/s2/submit_api.py /workspace/trilogy /workspace/dy_key; do
  [ -e "$p" ] && ok "$p 已存在" || warn "$p 不存在（新建机器属正常）"
done

echo
echo "=========== 5. 内存门槛（按卡数分档，别选错机型）==========="
MEM_GB=$(free -g | awk '/^Mem:/{print $2}')
echo "           本机内存：${MEM_GB:-0} GB"
if [ "${MEM_GB:-0}" -ge 100 ]; then
  ok "满足【双卡】门槛（>= 100 GB）—— 也必然满足单卡"
elif [ "${MEM_GB:-0}" -ge 96 ]; then
  ok "满足【单卡】门槛（>= 96 GB），但不够双卡（需 >= 100 GB）"
elif [ "${MEM_GB:-0}" -ge 64 ]; then
  bad "内存 ${MEM_GB} GB 低于单卡门槛 96 GB —— 有 OOM 风险，不建议用"
else
  bad "内存 ${MEM_GB} GB 明显不足（单卡也需 >= 96 GB）"
fi
echo "           机理：单张 A100-40G 装不下 50.2 GB 权重，必然 offload 到内存。"
echo "           旧机实测：**单个空闲 ComfyUI 进程常驻 ~57 GB**（双卡就是 2×57 GB）。"
echo "           ★ 所以单卡机器也请给到 96 GB 以上 —— 租卡时顺手选小内存机是常见事故。"
echo "           低于门槛时可加 swap 兜底（01_provision_os.sh 会建 8 GB），"
echo "           但 swap 只是安全气囊，真开始用会慢到像卡死，不能当容量用。"
echo
echo "体检结束。下一步： bash 01_provision_os.sh"
