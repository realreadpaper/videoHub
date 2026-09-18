#!/usr/bin/env bash
# ============================================================================
# A100 落地 · 权重获取 —— 换新实例后把缺的权重补齐
#
#   export SSHPASS='远端密码'
#   bash a100_weights.sh root@<IP> [端口]              # 演练：只列清单，不下载
#   bash a100_weights.sh root@<IP> [端口] --go         # 实际下载
#   bash a100_weights.sh root@<IP> [端口] --go --mirror  # 走 hf-mirror.com 加速
#
# 逻辑（关键）：
#   1. 不硬编码清单 —— 先在远端**反查所有工作流实际引用的 .safetensors**，
#      再逐个 stat，得出「缺哪些」。工作流一改，清单自动跟着变。
#   2. 按内置的「文件名 → HuggingFace 仓库 / 子目录」映射表推导下载地址。
#   3. 认不出来的文件**不猜**，单独列出来人工确认。
#   4. hf download 自带断点续传；失败不中断其余下载，最后出一份成败表。
#
# 下载量提醒：一个全新的实例补齐大约需要 **60–90 GB**（UNET + CLIP + LTX 精修链）。
# 先确保 /workspace 剩余空间够，脚本会在下载前检查。
# ============================================================================
set -uo pipefail
cd "$(dirname "$0")"

HOST="${1:-}"; shift 2>/dev/null || true
PORT=22; GO=0; MIRROR=0
for a in "$@"; do
  case "$a" in
    --go)     GO=1 ;;
    --mirror) MIRROR=1 ;;
    --port=*) PORT="${a#*=}" ;;
    --*)      warnx="未知选项 $a（已忽略）" ;;
    *)        PORT="$a" ;;          # 第一个非选项参数当作端口
  esac
done
[ -z "$HOST" ] && { echo "用法: bash a100_weights.sh root@<IP> [端口] [--go] [--mirror]"; exit 2; }
: "${SSHPASS:?请先 export SSHPASS=远端密码}"

SSH="sshpass -e ssh -p $PORT -o StrictHostKeyChecking=no -o ConnectTimeout=12 -o ServerAliveInterval=15 $HOST"
say()  { printf '\n\033[1m══ %s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✔\033[0m %s\n' "$*"; }
bad()  { printf '  \033[31m✘\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
dim()  { printf '    \033[2m%s\033[0m\n' "$*"; }

[ "$GO" = 0 ] && warn "演练模式（未加 --go），下面只列清单与命令，不实际下载"

# ── 1. 远端反查缺失清单 ─────────────────────────────────────────────────────
say "1/4 · 远端反查：工作流引用了哪些权重、缺哪些"
MISSING=$($SSH '/workspace/venv/bin/python - <<PYEOF
import json, os, glob, collections
C="/workspace/ComfyUI"; M=os.path.join(C,"models")
wfs=(glob.glob("/workspace/films/*/workflows/*.json")
     + glob.glob(C+"/custom_nodes/comfyui-minimax-h3-audio-T8/examples/**/*.json", recursive=True))
wanted=set()
for f in wfs:
    try: d=json.load(open(f,encoding="utf-8"))
    except Exception: continue
    def walk(o):
        if isinstance(o,str):
            if o.endswith(".safetensors"): wanted.add(os.path.basename(o))
        elif isinstance(o,dict):
            for v in o.values(): walk(v)
        elif isinstance(o,list):
            for v in o: walk(v)
    walk(d)
have=set()
for root,_,fs in os.walk(M):
    for f in fs:
        if f.endswith(".safetensors"): have.add(f)
miss=sorted(wanted-have)
print("\n".join(miss) if miss else "__NONE__")
PYEOF' 2>/dev/null | tr -d '\r')

if [ -z "$MISSING" ] || [ "$MISSING" = "__NONE__" ]; then
  ok "远端权重已齐，无需下载"
  exit 0
fi
echo "$MISSING" | sed 's/^/    ✘ /'

# ── 2. 盘查磁盘空间 ─────────────────────────────────────────────────────────
say "2/4 · 磁盘空间检查"
$SSH 'df -h /workspace 2>/dev/null | awk "NR==2{print \"  /workspace: \"\$2\" 总 / \"\$4\" 可用 / \"\$5\" 已用\"}"' 2>&1

# ── 3. 映射到 HuggingFace 下载地址 ──────────────────────────────────────────
say "3/4 · 映射到 HuggingFace 来源"
# 文件名前缀 → "仓库|models 下的子目录"。顺序敏感：越具体的规则放前面。
map_src() {
  local fn="$1"
  case "$fn" in
    minimax_h3_video_vae_fp16*|minimax_h3_audio_vae_fp32*)
        echo "Comfy-Org/MiniMax-H3|vae" ;;
    qwen3vl_32b_*)
        echo "Comfy-Org/MiniMax-H3|text_encoders" ;;
    minimax_h3_ref2va_*|minimax_h3_fl2va_*)
        echo "Comfy-Org/MiniMax-H3|diffusion_models" ;;
    minimax_h3_*turbo*|minimax_h3_*8step*|minimax_h3_*lora*)
        echo "lightx2v/Minimax-h3-Turbo|loras" ;;
    minimaxh3_art_is_explosion*)
        echo "Comfy-Org/MiniMax-H3|embeddings" ;;
    ltx-2.5-*|ltx25-*|ltxv*)
        echo "Lightricks/LTX-Video|vae" ;;
    *) echo "" ;;
  esac
}

CMDS=/tmp/_a100_dl_$$.sh
: > "$CMDS"
UNKNOWN=""
while IFS= read -r fn; do
  [ -z "$fn" ] && continue
  src=$(map_src "$fn")
  if [ -z "$src" ]; then
    UNKNOWN="$UNKNOWN$fn
"
    continue
  fi
  repo="${src%%|*}"; sub="${src##*|}"
  # $1 是远端仓库内路径，$2 是本地 models 下的目标目录
  case "$sub" in
    text_encoders) rpath="text_encoders/$fn"; tdir="text_encoders/minimax_h3" ;;
    *)             rpath="$sub/$fn";        tdir="$sub" ;;
  esac
  echo "# $fn"                                                                                  >> "$CMDS"
  echo "hfdl $repo $rpath /workspace/ComfyUI/models/$tdir/$fn"                                   >> "$CMDS"
  printf '    %-62s → %s/%s\n' "$fn" "$repo" "$rpath"
done <<< "$MISSING"

if [ -n "$UNKNOWN" ]; then
  warn "以下文件认不出来源（不猜，请人工确认后手工下载）："
  echo "$UNKNOWN" | sed 's/^/      /'
fi

# 下载前先确保 hf CLI 存在
if [ "$GO" = 1 ]; then
  say "4/4 · 执行下载"
  sshpass -e scp -P "$PORT" -o StrictHostKeyChecking=no "$CMDS" "$HOST:/tmp/_a100_dl.sh" >/dev/null

  # 远端执行器：准备下载器 → 逐条 eval 生成的 hfdl 命令 → 单条失败不中断
  RUNNER=/tmp/_a100_run_$$.sh
  cat > "$RUNNER" <<'RUNNEREOF'
set +e
V=/workspace/venv/bin
if ! "$V/python" -m pip show huggingface_hub >/dev/null 2>&1; then
  echo "安装 huggingface_hub ..."
  "$V/python" -m pip install -q huggingface_hub
fi
if "$V/python" -m pip show hf_transfer >/dev/null 2>&1; then
  export HF_HUB_ENABLE_HF_TRANSFER=1
fi
if [ -x "$V/hf" ]; then HFC="$V/hf"; else HFC="$V/huggingface-cli"; fi
echo "下载器: $HFC"
echo "镜像  : ${HF_ENDPOINT:-huggingface.co}"
echo

hfdl() {   # hfdl <repo> <repo内路径> <目标绝对路径>
  repo="$1"; rpath="$2"; dst="$3"
  if [ -s "$dst" ]; then echo "  跳过（已存在）$(basename "$dst")"; return 0; fi
  rm -rf /tmp/_a100_dl_stage
  if "$HFC" download "$repo" "$rpath" --local-dir /tmp/_a100_dl_stage >/dev/null 2>&1 \
     && [ -s "/tmp/_a100_dl_stage/$rpath" ]; then
    mkdir -p "$(dirname "$dst")"
    mv -f "/tmp/_a100_dl_stage/$rpath" "$dst"
    echo "  ✔ $(du -h "$dst" | cut -f1)  $(basename "$dst")"
    rm -rf /tmp/_a100_dl_stage
  else
    echo "  ✘ 失败: $repo/$rpath"
    return 1
  fi
}

FAILN=0; OKN=0
while IFS= read -r line; do
  case "$line" in
    "") continue ;;
    "#"*) echo "── ${line#\# }"; continue ;;
  esac
  if eval "$line"; then OKN=$((OKN+1)); else FAILN=$((FAILN+1)); fi
done < /tmp/_a100_dl.sh
echo
echo "下载结束：成功 $OKN 条，失败 $FAILN 条"
RUNNEREOF

  sshpass -e scp -P "$PORT" -o StrictHostKeyChecking=no "$RUNNER" "$HOST:/tmp/_a100_run.sh" >/dev/null
  if [ "$MIRROR" = 1 ]; then
    ok "启用 HF 镜像 hf-mirror.com"
    $SSH "export HF_ENDPOINT=https://hf-mirror.com; bash /tmp/_a100_run.sh" 2>&1 | tail -45
  else
    $SSH "bash /tmp/_a100_run.sh" 2>&1 | tail -45
  fi
  rm -f "$RUNNER" "$CMDS"

  say "回执"
  $SSH 'find /workspace/ComfyUI/models -name "*.safetensors" 2>/dev/null | wc -l | xargs -I{} echo "  {} 个 .safetensors 已就位"
        du -sh /workspace/ComfyUI/models 2>/dev/null | sed "s/^/  models 总占用 /"' 2>&1
  echo
  warn "务必复核：节点包 examples 里若有 Ref2VA 专用权重（minimax_h3_ref2va_*），
      它是**独立于 fl2va 的一份 UNET**（另带 ref2v turbo LoRA），不能用 fl2va 顶替。"
else
  say "4/4 · 演练结束"
  dim "实际执行："
  dim "  bash a100_weights.sh $HOST $PORT --go [--mirror]"
  [ -f "$CMDS" ] && { echo; dim "将执行以下命令（前 8 条）："; head -8 "$CMDS" | sed 's/^/      /'; rm -f "$CMDS"; }
fi
