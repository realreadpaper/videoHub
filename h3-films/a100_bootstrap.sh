#!/usr/bin/env bash
# ============================================================================
# A100 落地引导 —— 拿到 SSH 配置后的**第一条命令**
#
#   export SSHPASS='远端密码'
#   bash a100_bootstrap.sh root@<IP> [端口]
#
# 它做五件事，全程只读、不改远端任何配置：
#   P0  连通性 + 主机基线（CPU / 内存 / 磁盘 / 内核 / 系统）
#   P1  GPU 与驱动（型号 / 显存 / compute_cap / 驱动版本 / NCCL 拓扑）
#   P2  硬件判决（自动调 check_gpu_compat.py，给出「能跑 / 需换权重 / 不可行」）
#   P3  环境基线（python / venv / torch / CUDA / ComfyUI / 节点包 / runner）
#   P4  权重盘点（**从远端实际工作流里反查**需要的权重，逐个 stat 报缺失）
#   P5  打印「下一步该敲什么」，并把完整报告落盘到本地 _a100/report.txt
#
# 注意：本脚本不下载权重、不改工作流、不启动 ComfyUI —— 那些在拿到这份报告后
# 按《A100 落地执行手册》逐条执行。
# ============================================================================
set -uo pipefail
cd "$(dirname "$0")"

HOST="${1:-}"
PORT="${2:-22}"
[ -z "$HOST" ] && { echo "用法: bash a100_bootstrap.sh root@<IP> [端口]"; exit 2; }
: "${SSHPASS:?请先 export SSHPASS=远端密码}"

PY=/Users/hejianglong/.workbuddy/binaries/python/envs/default/bin/python
[ -x "$PY" ] || PY=/usr/bin/python3

SSH="sshpass -e ssh -p $PORT -o StrictHostKeyChecking=no -o ConnectTimeout=12 -o ServerAliveInterval=15 $HOST"
SCP="sshpass -e scp -P $PORT -o StrictHostKeyChecking=no"
mkdir -p _a100
OUT="_a100/report_$(date +%Y%m%d_%H%M%S).txt"

say()  { printf '\n\033[1m══ %s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✔\033[0m %s\n' "$*"; }
bad()  { printf '  \033[31m✘\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
dim()  { printf '    \033[2m%s\033[0m\n' "$*"; }

# ── P0 连通性 ───────────────────────────────────────────────────────────────
say "P0 · 连通性"
if $SSH 'echo __OK__' 2>/dev/null | grep -q __OK__; then
  ok "SSH 可达 $HOST:$PORT"
else
  bad "SSH 不可达 —— 检查 IP / 端口 / 密码，或实例是否已开机"
  exit 3
fi

# ── P1 主机基线 ─────────────────────────────────────────────────────────────
say "P1 · 主机基线"
$SSH 'echo "  系统   : $( . /etc/os-release 2>/dev/null && echo "$PRETTY_NAME" || uname -a )"
      echo "  内核   : $(uname -r)"
      echo "  CPU    : $(nproc) 核  $(grep -m1 "model name" /proc/cpuinfo | cut -d: -f2 | xargs)"
      echo "  内存   : $(free -g | awk "/^Mem:/{print \$2\" GB 总 / \"\$7\" GB 可用\"}")"
      echo "  交换   : $(free -g | awk "/^Swap:/{print \$2\" GB\"}")"
      echo "  磁盘 / : $(df -h / | awk "NR==2{print \$2\" 总 / \"\$4\" 可用\"}")"
      echo "  /workspace : $(df -h /workspace 2>/dev/null | awk "NR==2{print \$2\" 总 / \"\$4\" 可用\"}" || echo "不存在")"
      echo "  时间   : $(date)"' 2>&1 | tee -a "$OUT"

# ── P2 GPU + 硬件判决 ───────────────────────────────────────────────────────
say "P2 · GPU 与硬件判决"
$SSH 'command -v nvidia-smi >/dev/null || { echo "  ✘ 无 nvidia-smi"; exit 0; }
      nvidia-smi --query-gpu=index,name,compute_cap,memory.total,memory.used,driver_version,utilization.gpu \
        --format=csv,noheader | sed "s/^/  GPU: /"' 2>&1 | tee -a "$OUT"

if [ -f check_gpu_compat.py ]; then
  $SCP check_gpu_compat.py "$HOST:/tmp/check_gpu_compat.py" >/dev/null 2>&1
  VERDICT=$($SSH 'command -v python3 >/dev/null && python3 /tmp/check_gpu_compat.py 2>&1' 2>&1)
  echo "$VERDICT" | tee -a "$OUT"
  RC=$($SSH 'python3 /tmp/check_gpu_compat.py --quiet >/dev/null 2>&1; echo $?' 2>/dev/null | tr -d '\r')
  case "${RC:-}" in
    0) ok "判决：可跑（原生）" ;;
    2) warn "判决：可跑，但需换权重（见上）" ;;
    3) bad "判决：不可行" ;;
    *) dim "（未能取到退出码）" ;;
  esac
else
  warn "本地缺 check_gpu_compat.py，跳过自动判决"
fi

# ── P3 环境基线 ─────────────────────────────────────────────────────────────
say "P3 · 环境基线"
$SSH 'C=/workspace/ComfyUI
  echo "  venv python : $(/workspace/venv/bin/python -V 2>&1 || echo 缺)"
  /workspace/venv/bin/python - <<PYEOF 2>&1 | sed "s/^/  /"
import importlib, sys
def v(m):
    try:
        mod=importlib.import_module(m)
        return getattr(mod,"__version__","?")
    except Exception as e:
        return "缺 (%s)"%type(e).__name__
print("torch       :", v("torch"))
try:
    import torch
    print("torch cuda  :", torch.version.cuda, "| 可用:", torch.cuda.is_available(),
          "| arch list:", torch.cuda.get_arch_list()[:14] if torch.cuda.is_available() else "-")
    if torch.cuda.is_available():
        p=torch.cuda.get_device_properties(0)
        print("device      :", p.name, "| SM %d.%d"%(p.major,p.minor), "| %.1f GB"%(p.total_memory/2**30))
except Exception as e:
    print("torch cuda  : 探测失败", e)
for m in ("comfy_kitchen","comfy_kitchen.cuda","sageattention","flash_attn","xformers","torchsde"):
    print("%-12s:"%m, v(m))
print("numpy       :", v("numpy"))
PYEOF
  echo "  nvcc        : $(nvcc --version 2>/dev/null | grep release || echo 缺)"
  echo "  CUDA runtime: $(ls -d /usr/local/cuda-* 2>/dev/null | tr "\n" " " || echo 缺)"
  echo "  ComfyUI     : $([ -d $C ] && echo 存在 || echo 缺)"
  echo "  ComfyUI 版本: $(cd $C 2>/dev/null && git log -1 --format="%h %ad %s" --date=short 2>/dev/null || echo ?)"
  echo "  节点包 T8   : $([ -d $C/custom_nodes/comfyui-minimax-h3-audio-T8 ] && echo 存在 || echo 缺)"
  echo "  runner      : $([ -f /workspace/h3scripts/80_run_workflow_remote.py ] && echo 存在 || echo 缺)"
  echo "  ComfyUI 进程: $(pgrep -af "main.py" | head -1 || echo 未运行)"
  echo "  端口 8188   : $( (curl -s -m 3 http://127.0.0.1:8188/system_stats >/dev/null && echo 通) || echo 不通)"
  echo "  工程目录:"
  for s in douyin-office douyin-blinddate; do
    n=$(ls /workspace/films/$s/workflows/*.json 2>/dev/null | wc -l)
    echo "     /workspace/films/$s  workflows=$n"
  done
  echo "  干声: $(ls $C/input/tts_dry/film1/*.wav 2>/dev/null | wc -l) + $(ls $C/input/tts_dry/film2/*.wav 2>/dev/null | wc -l)"
  echo "  首帧图: $(ls $C/input/frames/*.png 2>/dev/null | wc -l)   参考图: $(ls $C/input/refs/*.png 2>/dev/null | wc -l)"' 2>&1 | tee -a "$OUT"

# ── P4 权重盘点（从实际工作流反查，最可靠）──────────────────────────────────
say "P4 · 权重盘点（从远端实际工作流反查）"
$SSH 'C=/workspace/ComfyUI
  /workspace/venv/bin/python - <<PYEOF 2>&1
import json, os, glob, collections
C="/workspace/ComfyUI"
M=os.path.join(C,"models")
# 1) 收集所有工作流：工程目录 + 节点包 examples
wfs = (glob.glob("/workspace/films/*/workflows/*.json")
       + glob.glob(C+"/custom_nodes/comfyui-minimax-h3-audio-T8/examples/**/*.json", recursive=True))
wanted=collections.defaultdict(set)   # 文件名 -> 引用它的工作流数
nwf=0
for f in wfs:
    try: d=json.load(open(f,encoding="utf-8"))
    except Exception: continue
    nwf+=1
    def walk(o):
        if isinstance(o,str):
            if o.endswith(".safetensors"): wanted[o].add(os.path.basename(f))
        elif isinstance(o,dict):
            for v in o.values(): walk(v)
        elif isinstance(o,list):
            for v in o: walk(v)
    walk(d)
print("扫描 %d 份工作流，引用到 %d 个权重文件" % (nwf, len(wanted)))
print()
# 2) 候选目录（ComfyUI 会递归扫 models 下的子目录，所以按 basename 全盘找）
def find(fn):
    hit=[]
    for root,_,fs in os.walk(M):
        if os.path.basename(fn) in fs:
            p=os.path.join(root,os.path.basename(fn))
            hit.append((p, os.path.getsize(p)/2**30))
    return hit
tot_have=tot_miss=0.0
miss=[]
print("%-64s %-12s %s"%("权重文件","状态","大小"))
print("-"*92)
for fn in sorted(wanted):
    hit=find(fn)
    if hit:
        p,gb=hit[0]; tot_have+=gb
        print("%-64s %-12s %.2f GB"%(fn[:64], "✔ "+os.path.relpath(p,M)[:10], gb))
    else:
        miss.append(fn); print("%-64s %-12s %s"%(fn[:64], "✘ 缺失", "-"))
print("-"*92)
print("已就位合计 %.1f GB   |   缺失 %d 个" % (tot_have, len(miss)))
if miss:
    print()
    print("缺失清单（需要下载）：")
    for fn in miss: print("   -", fn)
print()
print("models/ 各子目录占用：")
for d in sorted(glob.glob(M+"/*")):
    if os.path.isdir(d):
        try:
            sz=sum(os.path.getsize(os.path.join(r,f)) for r,_,fs in os.walk(d) for f in fs)
            n=sum(len(fs) for _,_,fs in os.walk(d))
            print("   %-22s %6.1f GB  %d 文件"%(os.path.basename(d), sz/2**30, n))
        except Exception: pass
PYEOF' 2>&1 | tee -a "$OUT"

# ── P5 下一步 ───────────────────────────────────────────────────────────────
say "P5 · 下一步"
cat <<'NEXT' | tee -a "$OUT"
  按《A100 落地执行手册.html》的阶段顺序执行：

  [阶段 2] 若 P4 报缺失 → 补权重
       bash a100_weights.sh <host> <port>            # 先 --dry-run 看清单
       bash a100_weights.sh <host> <port> --go       # 实际下载（支持 HF 镜像）

  [阶段 3] 换 CLIP 权重（A100 唯一必改项，本地改完再投送）
       python3 a100_patch_clip.py --dir _remote --check    # 先看会改几处
       python3 a100_patch_clip.py --dir _remote            # 执行（自动备份）

  [阶段 4] 投送本地资产 + 工作流
       SSHPASS=... bash deploy_refs.sh <host> <port>       # 首帧图 / 参考图
       SSHPASS=... bash deploy_voice.sh <host> <port>      # 干声 / 工作流 / runner

  [阶段 5] 单镜验证（三条路线各一镜，别跳）
       ssh -p <port> <host>
       cd /workspace/films/douyin-office
       /workspace/venv/bin/python 11_run_voice_film.py --film film1 --shots 5
NEXT

echo
ok "完整报告已落盘：$OUT"
echo
