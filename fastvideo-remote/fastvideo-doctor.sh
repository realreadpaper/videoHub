#!/usr/bin/env bash
# ============================================================================
#  fastvideo-doctor.sh  —  FastVideo 远程服务器环境自检
# ----------------------------------------------------------------------------
#  在目标服务器上运行。只读检查，不安装、不修改、不下载任何东西。
#
#  用法:
#      bash fastvideo-doctor.sh              # 用当前目录所在的盘做空间检查
#      bash fastvideo-doctor.sh /data        # 指定权重要落地的目录
#
#  判断依据来自 hao-ai-lab/FastVideo 仓库内文档：
#      docs/getting_started/installation/gpu.md
#      docs/contributing/developer_env/runpod.md
#      docs/inference/support_matrix.md
#      docs/cookbook/openai-api.md
# ============================================================================

TARGET_DIR="${1:-$PWD}"

if [ -t 1 ]; then
  R=$'\033[31m'; G=$'\033[32m'; Y=$'\033[33m'; C=$'\033[36m'; D=$'\033[2m'
  N=$'\033[0m'; BOLD=$'\033[1m'
else
  R=''; G=''; Y=''; C=''; D=''; N=''; BOLD=''
fi

PASS=0; WARN=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf "  ${G}[通过]${N} %s\n" "$1"; }
wa()  { WARN=$((WARN+1)); printf "  ${Y}[注意]${N} %s\n" "$1"; }
no()  { FAIL=$((FAIL+1)); printf "  ${R}[失败]${N} %s\n" "$1"; }
inf() { printf "         ${D}%s${N}\n" "$1"; }
sec() { printf "\n${BOLD}${C}━━ %s${N}\n" "$1"; }

printf "\n${BOLD}FastVideo 远程部署环境自检${N}\n"
printf "${D}时间: %s | 主机: %s | 检查目录: %s${N}\n" \
  "$(date '+%Y-%m-%d %H:%M:%S')" "$(hostname 2>/dev/null || echo '?')" "$TARGET_DIR"

# ---------------------------------------------------------------- 系统
sec "1. 操作系统"
OS_TYPE="$(uname -s 2>/dev/null)"
inf "内核: $OS_TYPE $(uname -r 2>/dev/null)"

if [ "$OS_TYPE" = "Linux" ]; then
  ok "操作系统是 Linux —— 符合要求"
  if [ -f /etc/os-release ]; then
    # shellcheck disable=SC1091
    . /etc/os-release 2>/dev/null
    inf "发行版: ${PRETTY_NAME:-未知}"
  fi
else
  no "操作系统是 $OS_TYPE —— FastVideo 的 CUDA 路径要求 Linux 或 Windows WSL"
  inf "macOS 只能走另一条 MLX 分支，不能跑 CUDA 内核"
fi

# ---------------------------------------------------------------- GPU
sec "2. GPU 与驱动"

if ! command -v nvidia-smi >/dev/null 2>&1; then
  no "找不到 nvidia-smi —— 没有 NVIDIA 驱动，或没装驱动工具"
  inf "容器内运行的话，检查启动参数是否带了 --gpus all"
else
  GPU_CSV="$(nvidia-smi --query-gpu=name,memory.total,driver_version,compute_cap \
             --format=csv,noheader 2>/dev/null)"
  if [ -z "$GPU_CSV" ]; then
    wa "nvidia-smi 存在但查询无返回（驱动过旧，或 compute_cap 字段不被支持）"
    nvidia-smi 2>/dev/null | head -12 | sed 's/^/         /'
    GPU_NAME="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)"
    GPU_CC=""
  else
    GPU_NAME="$(echo "$GPU_CSV" | head -1 | cut -d',' -f1 | xargs)"
    GPU_MEM="$(echo "$GPU_CSV" | head -1 | cut -d',' -f2 | xargs)"
    GPU_DRV="$(echo "$GPU_CSV" | head -1 | cut -d',' -f3 | xargs)"
    GPU_CC="$(echo "$GPU_CSV"  | head -1 | cut -d',' -f4 | xargs)"
    GPU_COUNT="$(echo "$GPU_CSV" | grep -c . )"
    ok "检测到 $GPU_COUNT 张 GPU"
    inf "型号: $GPU_NAME | 显存: $GPU_MEM | 驱动: $GPU_DRV | 算力: ${GPU_CC:-未知}"
    if [ "$GPU_COUNT" -gt 1 ]; then
      inf "多卡明细:"
      echo "$GPU_CSV" | sed 's/^/         /'
    fi

    # 算力判定
    case "$GPU_CC" in
      8.9)
        ok "算力 8.9 (Ada) —— 与官方基准卡 L40S 同架构，FP8 原生支持"
        ;;
      9.0|10.0|12.0)
        ok "算力 $GPU_CC —— Hopper/Blackwell 级别，VSA/FA4 等高级内核可用"
        ;;
      8.6|8.0|7.5)
        wa "算力 $GPU_CC —— 能用，但 FP8 硬件加速不可用，性能会明显打折"
        ;;
      "")
        wa "没能读到算力值，稍后用 PyTorch 复核"
        ;;
      *)
        wa "算力 $GPU_CC —— 不在官方基准覆盖范围内，可能需要实测验证"
        ;;
    esac

    # 显存分档
    MEM_NUM="$(echo "$GPU_MEM" | tr -dc '0-9')"
    if [ -n "$MEM_NUM" ]; then
      if [ "$MEM_NUM" -ge 70000 ]; then
        ok "显存充足（${GPU_MEM}）—— 大模型单卡可行"
      elif [ "$MEM_NUM" -ge 40000 ]; then
        ok "显存 ${GPU_MEM} —— 中大型模型 480P 可行"
      elif [ "$MEM_NUM" -ge 20000 ]; then
        wa "显存 ${GPU_MEM} —— 需靠 FP8 + 稀疏注意力 + 逐层卸载撑，MiniMax-H3 单卡不可行"
      else
        no "显存 ${GPU_MEM} —— 低于 20 GB，视频生成基本跑不动"
      fi
    fi
  fi

  # CUDA 版本
  CUDA_VER="$(nvidia-smi 2>/dev/null | grep -o 'CUDA Version: *[0-9.]*' | head -1 | grep -o '[0-9][0-9.]*')"
  if [ -n "$CUDA_VER" ]; then
    case "$CUDA_VER" in
      12.6*|13.0*|12.8*|12.9*|13.*) ok "驱动支持的 CUDA 版本: $CUDA_VER" ;;
      12.*) wa "驱动支持 CUDA $CUDA_VER —— 官方主推 12.6 / 13.0，相邻版本一般兼容" ;;
      *) wa "驱动支持 CUDA $CUDA_VER —— 偏旧或偏新，注意选对 wheel 后端（cu126 / cu130）" ;;
    esac
  fi
fi

# ---------------------------------------------------------------- Python
sec "3. Python 环境"

PYBIN=""
for c in python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1; then PYBIN="$(command -v $c)"; break; fi
done

if [ -z "$PYBIN" ]; then
  no "没有找到 python3 —— 需要先装 Python 3.10–3.12"
else
  PYVER="$($PYBIN -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null)"
  inf "解释器: $PYBIN (Python $PYVER)"
  case "$PYVER" in
    3.10|3.11|3.12) ok "Python $PYVER —— 在支持范围内" ;;
    3.13|3.14) no "Python $PYVER —— 超出支持范围（3.10–3.12），安装会被拒" ;;
    *) wa "Python $PYVER —— 未在官方支持列表内" ;;
  esac
fi

if command -v uv >/dev/null 2>&1; then
  ok "uv 已安装: $(uv --version 2>/dev/null)"
else
  wa "没装 uv —— 官方推荐用它建环境，一条命令即可安装（见 setup 脚本）"
fi

if command -v conda >/dev/null 2>&1; then
  inf "检测到 conda，官方建议改用 uv（更快更稳）"
fi

# ---------------------------------------------------------------- 内存
sec "4. 内存与共享内存"

if [ -r /proc/meminfo ]; then
  MEM_TOTAL_KB="$(awk '/MemTotal/{print $2}' /proc/meminfo)"
  MEM_AVAIL_KB="$(awk '/MemAvailable/{print $2}' /proc/meminfo)"
  if [ -n "$MEM_TOTAL_KB" ]; then
    MEM_TOTAL_G=$(( MEM_TOTAL_KB / 1048576 ))
    MEM_AVAIL_G=$(( MEM_AVAIL_KB / 1048576 ))
    inf "物理内存: 共 ${MEM_TOTAL_G} GB / 可用 ${MEM_AVAIL_G} GB"
    if [ "$MEM_TOTAL_G" -ge 64 ]; then
      ok "内存充足 —— 支持逐层卸载与权重中转缓冲"
    elif [ "$MEM_TOTAL_G" -ge 32 ]; then
      wa "内存 ${MEM_TOTAL_G} GB —— 够用，但 14B 级模型的逐层卸载会吃紧"
    else
      no "内存仅 ${MEM_TOTAL_G} GB —— 卸载路径会频繁触发换页"
    fi
  fi
else
  wa "读不到 /proc/meminfo，跳过内存检查"
fi

SHM_TOTAL="$(df -h /dev/shm 2>/dev/null | awk 'NR==2{print $2}')"
if [ -n "$SHM_TOTAL" ]; then
  inf "/dev/shm 大小: $SHM_TOTAL"
  SHM_NUM="$(echo "$SHM_TOTAL" | tr -dc '0-9')"
  SHM_UNIT="$(echo "$SHM_TOTAL" | tr -dc 'GMT')"
  if [ "$SHM_UNIT" = "G" ] && [ -n "$SHM_NUM" ] && [ "$SHM_NUM" -lt 8 ]; then
    wa "/dev/shm 偏小（$SHM_TOTAL）—— 用 Docker 时必须加 --shm-size=16g，否则多进程加载模型会崩"
  else
    ok "/dev/shm 容量够用"
  fi
fi

# ---------------------------------------------------------------- 磁盘
sec "5. 磁盘空间"

if [ -d "$TARGET_DIR" ]; then
  df -h "$TARGET_DIR" 2>/dev/null | sed 's/^/         /'
  AVAIL_G="$(df -Pk "$TARGET_DIR" 2>/dev/null | awk 'NR==2{print int($4/1048576)}')"
  if [ -n "$AVAIL_G" ]; then
    inf "目标目录可用空间: ${AVAIL_G} GB"
    if [ "$AVAIL_G" -ge 200 ]; then
      ok "空间充裕 —— 可容纳镜像 + FastH3 全量权重（137 GB）"
    elif [ "$AVAIL_G" -ge 120 ]; then
      ok "空间够 FastWan / Wan2.2 系列（30–35 GB）；上 FastH3 需先清理"
    elif [ "$AVAIL_G" -ge 40 ]; then
      wa "空间 ${AVAIL_G} GB —— 只够单模型中量版本，跑完即删；FastH3 需要 137 GB"
    else
      no "空间仅 ${AVAIL_G} GB —— 装不下任何完整权重"
    fi
  fi
else
  wa "目录 $TARGET_DIR 不存在，改用当前目录检查"
  df -h . 2>/dev/null | sed 's/^/         /'
fi

# ---------------------------------------------------------------- Docker
sec "6. 容器能力"

if command -v docker >/dev/null 2>&1; then
  ok "docker 已安装: $(docker --version 2>/dev/null)"
  if docker info >/dev/null 2>&1; then
    ok "当前用户有权限直接调用 docker"
  else
    wa "docker 命令存在但无权限 —— 需要 sudo，或把用户加入 docker 组"
  fi
  if docker info 2>/dev/null | grep -qi nvidia; then
    ok "已配置 NVIDIA Container Toolkit（容器内可用 GPU）"
  else
    wa "未检测到 NVIDIA 容器运行时 —— 容器内可能看不到 GPU"
    inf "装法: nvidia-ctk runtime configure --runtime=docker && systemctl restart docker"
  fi
else
  wa "没装 docker —— 走 uv 直装路线即可，不是必须"
fi

if sudo -n true >/dev/null 2>&1; then
  ok "当前用户可免密 sudo —— 可安装系统依赖"
else
  wa "当前用户无免密 sudo —— 系统包安装会受限；容器路线不受影响"
fi

# ---------------------------------------------------------------- 网络
sec "7. 网络可达性"

check_url() {
  # $1=名称 $2=URL
  if command -v curl >/dev/null 2>&1; then
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 12 "$2" 2>/dev/null)"
    if [ "$code" = "200" ] || [ "$code" = "301" ] || [ "$code" = "302" ] || [ "$code" = "401" ]; then
      ok "$1 可达 (HTTP $code)"
      return 0
    fi
  fi
  no "$1 不可达"
  return 1
}

HF_OK=0
check_url "HuggingFace (huggingface.co)" "https://huggingface.co/api/models/FastVideo/FastWan2.1-T2V-1.3B-Diffusers" && HF_OK=1
MIRROR_OK=0
check_url "HF 国内镜像 (hf-mirror.com)" "https://hf-mirror.com" && MIRROR_OK=1
check_url "PyPI" "https://pypi.org/simple/" || true

if [ "$HF_OK" = "0" ] && [ "$MIRROR_OK" = "1" ]; then
  inf "结论: 直连 HF 不通但镜像通 —— 下载权重时务必设 HF_ENDPOINT=https://hf-mirror.com"
elif [ "$HF_OK" = "0" ] && [ "$MIRROR_OK" = "0" ]; then
  no "两条下载通道都不通 —— 需要在本地下好权重再上传，或用离线包"
fi

# ---------------------------------------------------------------- PyTorch 复核
sec "8. PyTorch 与 CUDA 复核"

if [ -n "$PYBIN" ] && "$PYBIN" -c "import torch" >/dev/null 2>&1; then
  "$PYBIN" - <<'PYEOF' 2>/dev/null | sed 's/^/         /'
import torch
print("torch 版本   :", torch.__version__)
print("CUDA 可用    :", torch.cuda.is_available())
print("编译 CUDA    :", torch.version.cuda)
if torch.cuda.is_available():
    n = torch.cuda.device_count()
    print("可见 GPU 数  :", n)
    for i in range(n):
        cap = torch.cuda.get_device_capability(i)
        print(f"  GPU{i} {torch.cuda.get_device_name(i)}  算力 {cap[0]}.{cap[1]}")
PYEOF
  TORCH_CC="$("$PYBIN" -c "import torch;print('ok') if torch.cuda.is_available() else print('no')" 2>/dev/null)"
  if [ "$TORCH_CC" = "ok" ]; then
    ok "PyTorch 能正常识别 CUDA 与 GPU"
  else
    wa "PyTorch 装了但用不了 CUDA —— wheel 后端选错了（需要 cu126 / cu130 版本）"
  fi
else
  inf "当前环境未安装 PyTorch（正常，尚未开始安装）"
fi

# ---------------------------------------------------------------- 结论
sec "自检结论"
TOTAL=$((PASS+WARN+FAIL))
printf "  通过 ${G}%s${N} 项 | 注意 ${Y}%s${N} 项 | 失败 ${R}%s${N} 项  （共 %s 项）\n" \
  "$PASS" "$WARN" "$FAIL" "$TOTAL"

if [ "$FAIL" -eq 0 ]; then
  printf "\n  ${G}${BOLD}结论：这台服务器具备运行条件${N}\n"
  if [ "$WARN" -gt 0 ]; then
    printf "  ${Y}但有 %s 项需要留意，看上面标 [注意] 的条目。${N}\n" "$WARN"
  fi
  printf "\n  ${BOLD}下一步：${N}跑 setup 脚本建环境\n"
  printf "      bash fastvideo-remote-setup.sh %s\n" "$TARGET_DIR"
else
  printf "\n  ${R}${BOLD}结论：存在 %s 项硬性阻塞，修完再继续${N}\n" "$FAIL"
  printf "  逐条看上面标 [失败] 的条目；多数是系统版本或驱动问题，不是项目本身的问题。\n"
fi
printf "\n"
