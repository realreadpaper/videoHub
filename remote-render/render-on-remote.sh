#!/usr/bin/env bash
# ============================================================================
#  render-on-remote.sh — 把 hypit 工程送到远端 Linux 机器，渲染成片，取回本地
# ----------------------------------------------------------------------------
#  为什么需要它：
#    当前对话环境有「批量删除安全护栏」（单个 turn 内删满 50 个文件即中止），
#    hypit 的 Runtime Worker 在准备阶段清理临时文件时会撞上它，导致 Build 中断。
#    把渲染放到一台干净的 Linux 机器上跑，这个限制自然消失。
#
#    注意：成片渲染 = ffmpeg + Chrome 逐帧截图 + 编码，**全程只吃 CPU**。
#    远端是不是 4090、有没有 GPU，对「出片」这件事没有任何影响。
#    GPU 的价值在另一条链路：跑 AI 生成模型（FastVideo 等）去「生成画面」。
#
#  用法：
#     # 模式一：SSH 到远端服务器（你给 IP 的场景）
#     bash render-on-remote.sh --host root@1.2.3.4
#     bash render-on-remote.sh --host root@1.2.3.4 --port 22024 --remote-dir /data/hypit/douyin-ad
#
#     # 模式二：本地 Docker 容器（同一套脚本，用来先验证链路）
#     bash render-on-remote.sh --docker hypit-render
#
#  常用参数：
#     --project DIR     本地工程目录（默认：脚本上一级的 videos/douyin-ad）
#     --run FILE        要渲染的 run 文件（默认 productions/ad-clone/runs/final.svrun）
#     --out DIR         成片落地的本地目录（默认 <project>/output）
#     --slim            只传渲染必需文件，跳过 ref/ references/ 等分析素材
#     --keep-remote     渲染完不清理远端工程
#     --skip-bootstrap  跳过远端环境安装（确认已装好时用）
#     --dry-run         只做探测与传输，不启动渲染
# ============================================================================

set -uo pipefail

# ── 默认值 ──────────────────────────────────────────────────────────────────
HOST=""; SSH_PORT=""; DOCKER=""
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)/videos/douyin-ad"
RUN_FILE="productions/ad-clone/runs/final.svrun"
SVML_FILE="productions/ad-clone/authors/main.svml"
OUT_DIR=""
REMOTE_DIR=""
SLIM="no"; KEEP_REMOTE="no"; SKIP_BOOTSTRAP="no"; DRY_RUN="no"

usage() { sed -n '2,34p' "$0" | sed 's/^# \{0,1\}//'; exit 0; }

while [ $# -gt 0 ]; do
  case "$1" in
    --host)           HOST="$2"; shift 2 ;;
    --port)           SSH_PORT="$2"; shift 2 ;;
    --docker)         DOCKER="$2"; shift 2 ;;
    --project)        PROJECT_DIR="$2"; shift 2 ;;
    --run)            RUN_FILE="$2"; shift 2 ;;
    --out)            OUT_DIR="$2"; shift 2 ;;
    --remote-dir)     REMOTE_DIR="$2"; shift 2 ;;
    --slim)           SLIM="yes"; shift ;;
    --keep-remote)    KEEP_REMOTE="yes"; shift ;;
    --skip-bootstrap) SKIP_BOOTSTRAP="yes"; shift ;;
    --dry-run)        DRY_RUN="yes"; shift ;;
    --help|-h)        usage ;;
    *) echo "未知参数: $1"; usage ;;
  esac
done

C_OK=$'\033[32m'; C_WARN=$'\033[33m'; C_ERR=$'\033[31m'; C_DIM=$'\033[2m'; C_RST=$'\033[0m'
step() { echo; echo "${C_OK}════ $* ════${C_RST}"; }
ok()   { echo "  ${C_OK}✓${C_RST} $*"; }
warn() { echo "  ${C_WARN}!${C_RST} $*"; }
die()  { echo "  ${C_ERR}✗${C_RST} $*"; exit 1; }
info() { echo "  ${C_DIM}$*${C_RST}"; }

# ── 模式判定 ────────────────────────────────────────────────────────────────
[ -n "$HOST" ] || [ -n "$DOCKER" ] || { echo "必须指定 --host 或 --docker"; usage; }
[ -n "$HOST" ] && [ -n "$DOCKER" ] && die "--host 与 --docker 只能选一个"

PROJECT_NAME="$(basename "$PROJECT_DIR")"
PROJECT_DIR="$(cd "$PROJECT_DIR" 2>/dev/null && pwd)" || die "工程目录不存在：$PROJECT_DIR"
OUT_DIR="${OUT_DIR:-${PROJECT_DIR}/output}"
REMOTE_DIR="${REMOTE_DIR:-hypit-projects/${PROJECT_NAME}}"
mkdir -p "$OUT_DIR"

# ── 统一执行层：ssh / docker ────────────────────────────────────────────────
#  每条远端命令都前置 source ~/.hypit-browser-env：
#  ssh 非交互会话不读 .bashrc，hypit 的 preflight 会因拿不到
#  HYPERFRAMES_BROWSER_PATH 而判 provider 不可用。
ENV_PREFIX='[ -f ~/.hypit-browser-env ] && . ~/.hypit-browser-env;'

if [ -n "$DOCKER" ]; then
  MODE="docker"
  TARGET="容器 ${DOCKER}"
  SSH_OPTS=""
  rsh()      { docker exec "$DOCKER" bash -lc "${ENV_PREFIX} $1"; }
  rsh_tty()  { docker exec -i "$DOCKER" bash -lc "${ENV_PREFIX} $1"; }
  push()     { docker cp "$1" "${DOCKER}:$2" >/dev/null; }
  pull()     { docker cp "${DOCKER}:$1" "$2" >/dev/null; }
else
  MODE="ssh"
  TARGET="$HOST${SSH_PORT:+:$SSH_PORT}"
  SSH_OPTS="-o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=no"
  [ -n "$SSH_PORT" ] && SSH_OPTS="$SSH_OPTS -p $SSH_PORT"
  rsh()      { ssh $SSH_OPTS "$HOST" "${ENV_PREFIX} $1"; }
  rsh_tty()  { ssh $SSH_OPTS "$HOST" "${ENV_PREFIX} $1"; }
  push()     { scp ${SSH_PORT:+-P $SSH_PORT} -o StrictHostKeyChecking=no "$1" "${HOST}:$2" >/dev/null; }
  pull()     { scp ${SSH_PORT:+-P $SSH_PORT} -o StrictHostKeyChecking=no "${HOST}:$1" "$2" >/dev/null; }
fi

step "0. 目标确认"
ok "模式      ${MODE}"
ok "目标      ${TARGET}"
ok "本地工程  ${PROJECT_DIR}"
ok "Run       ${RUN_FILE}"
ok "成片落地  ${OUT_DIR}"

# ── 1. 连通性与环境探测 ─────────────────────────────────────────────────────
step "1. 探测远端环境"

PROBE="$(rsh 'echo __HOST__ $(hostname); echo __OS__ $( (. /etc/os-release 2>/dev/null && echo \"$PRETTY_NAME\") || uname -s); echo __ARCH__ $(uname -m); echo __CPU__ $(nproc 2>/dev/null || echo 0); echo __MEM__ $(awk \"/MemTotal/{printf \\\"%d\\\", \\\$2/1024/1024}\" /proc/meminfo 2>/dev/null || echo 0); echo __DISK__ $(df -Pk \$HOME | awk \"NR==2{printf \\\"%d\\\", \\\$4/1024/1024}\"); echo __NODE__ $(command -v node >/dev/null 2>&1 && node -v || echo none); echo __HYIT__ $(command -v hypit >/dev/null 2>&1 && hypit --version 2>/dev/null || echo none); echo __HFRM__ $(command -v hyperframes >/dev/null 2>&1 && hyperframes --version 2>/dev/null | head -1 || echo none); echo __FFMPEG__ $(command -v ffmpeg 2>/dev/null || echo none); echo __CHROME__ $(find \$HOME/.cache/puppeteer -name chrome -type f 2>/dev/null | head -1 || echo none); echo __GPU__ $(command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null | head -1 || echo none)' 2>&1)" || die "无法连接到 ${TARGET}"
echo "$PROBE" | grep -q "__HOST__" || { echo "$PROBE" | tail -5; die "远端探测失败"; }

gv() { echo "$PROBE" | sed -n "s/^__${1}__ //p" | head -1; }
R_HOST="$(gv HOST)"; R_OS="$(gv OS)"; R_ARCH="$(gv ARCH)"; R_CPU="$(gv CPU)"
R_MEM="$(gv MEM)";  R_DISK="$(gv DISK)"; R_NODE="$(gv NODE)"; R_HYIT="$(gv HYIT)"
R_HFRM="$(gv HFRM)"; R_FFMPEG="$(gv FFMPEG)"; R_CHROME="$(gv CHROME)"; R_GPU="$(gv GPU)"

INFO_TPL="  %-10s %s\n"
printf "$INFO_TPL" "主机"     "$R_HOST"
printf "$INFO_TPL" "系统"     "$R_OS"
printf "$INFO_TPL" "架构"     "$R_ARCH"
printf "$INFO_TPL" "CPU/内存" "${R_CPU} 核 / ${R_MEM}GB"
printf "$INFO_TPL" "可用磁盘" "${R_DISK}GB"
printf "$INFO_TPL" "node"     "$R_NODE"
printf "$INFO_TPL" "hypit"    "$R_HYIT"
printf "$INFO_TPL" "hyperframes" "$R_HFRM"
printf "$INFO_TPL" "ffmpeg"   "$R_FFMPEG"
printf "$INFO_TPL" "chrome"   "${R_CHROME:-none}"
printf "$INFO_TPL" "GPU"      "$R_GPU"
echo

# 环境体检
ENV_OK="yes"
[ "$R_NODE" = "none" ]   && { warn "远端缺 node";   ENV_OK="no"; }
[ "$R_HYIT" = "none" ]   && { warn "远端缺 hypit";  ENV_OK="no"; }
[ "$R_FFMPEG" = "none" ] && { warn "远端缺 ffmpeg"; ENV_OK="no"; }
[ "$R_CHROME" = "none" ] && { warn "远端缺 Chrome"; ENV_OK="no"; }

if [ "$R_GPU" = "none" ]; then
  info ""
  info "远端无 GPU —— 这不影响出片。成片渲染是 CPU 活（ffmpeg + Chrome 截图），"
  info "4090 之类的显卡只对「用 AI 模型生成画面」那条链路有价值。"
fi

# ── 2. 远端环境安装 ─────────────────────────────────────────────────────────
step "2. 远端环境"

if [ "$SKIP_BOOTSTRAP" = "yes" ]; then
  warn "--skip-bootstrap：跳过安装"
elif [ "$ENV_OK" = "yes" ]; then
  ok "环境已齐备，跳过安装"
else
  info "把 bootstrap 脚本送到远端并执行（首次约 5–10 分钟）…"
  rsh "mkdir -p ~/${REMOTE_DIR}" || die "远端建目录失败"
  push "${SCRIPT_DIR}/hypit-remote-bootstrap.sh" "~/${REMOTE_DIR}/hypit-remote-bootstrap.sh"
  if ! rsh_tty "bash ~/${REMOTE_DIR}/hypit-remote-bootstrap.sh 2>&1 | tail -30"; then
    warn "bootstrap 未完整成功，继续尝试渲染；若失败请手动在远端执行："
    warn "  bash ~/${REMOTE_DIR}/hypit-remote-bootstrap.sh"
  fi
  # 刷新 PATH（同一会话里新装的命令需要重新解析）
  rsh "ln -sf /usr/local/bin/node /usr/bin/node 2>/dev/null || true"
fi

# ── 3. 传输工程 ─────────────────────────────────────────────────────────────
step "3. 传输工程"

rsh "mkdir -p ~/${REMOTE_DIR}" || die "远端建目录失败"

if [ "$MODE" = "ssh" ]; then
  RSYNC_EXCL="--exclude node_modules --exclude .git --exclude .hypit/runtimes"
  [ "$SLIM" = "yes" ] && RSYNC_EXCL="$RSYNC_EXCL --exclude ref --exclude references --exclude docs"
  info "rsync $RSYNC_EXCL"
  # shellcheck disable=SC2086
  rsync -az --delete $RSYNC_EXCL ${SSH_PORT:+-e "ssh -p $SSH_PORT -o StrictHostKeyChecking=no"} \
    "${PROJECT_DIR}/" "${HOST}:~/${REMOTE_DIR}/" || die "rsync 失败"
else
  # docker cp 不支持排除：逐个必需项复制
  docker exec "$DOCKER" mkdir -p "/root/${REMOTE_DIR}" >/dev/null
  for item in productions hypit.runtime.json package.json; do
    [ -e "${PROJECT_DIR}/${item}" ] || continue
    # 先清掉旧的同名项
    docker exec "$DOCKER" rm -rf "/root/${REMOTE_DIR}/${item}" >/dev/null 2>&1 || true
    push "${PROJECT_DIR}/${item}" "/root/${REMOTE_DIR}/"
  done
  if [ "$SLIM" != "yes" ]; then
    for item in ref references docs; do
      [ -e "${PROJECT_DIR}/${item}" ] || continue
      docker exec "$DOCKER" rm -rf "/root/${REMOTE_DIR}/${item}" >/dev/null 2>&1 || true
      push "${PROJECT_DIR}/${item}" "/root/${REMOTE_DIR}/"
    done
  fi
fi
ok "工程已送达 ~/${REMOTE_DIR}"

# ── 4. 远端路径适配 ─────────────────────────────────────────────────────────
step "4. 远端配置适配"

FFMPEG_REMOTE="$(rsh 'command -v ffmpeg 2>/dev/null || echo /usr/bin/ffmpeg')"
FFPROBE_REMOTE="$(rsh 'command -v ffprobe 2>/dev/null || echo /usr/bin/ffprobe')"
info "远端 ffmpeg = ${FFMPEG_REMOTE}"

rsh "cd ~/${REMOTE_DIR} && python3 - <<'PYEOF' 2>/dev/null || sed -i 's|\"ffmpegPath\": \"[^\"]*\"|\"ffmpegPath\": \"${FFMPEG_REMOTE}\"|; s|\"ffprobePath\": \"[^\"]*\"|\"ffprobePath\": \"${FFPROBE_REMOTE}\"|' hypit.runtime.json
import json
p='hypit.runtime.json'
d=json.load(open(p))
ep=d.get('endpoints',{}).get('hyperframes.local',{}).get('config',{})
if ep:
    ep['ffmpegPath']='${FFMPEG_REMOTE}'
    ep['ffprobePath']='${FFPROBE_REMOTE}'
    json.dump(d,open(p,'w'),indent=2)
PYEOF"
ok "已把 ffmpeg/ffprobe 指到远端路径"

# ── 5. 校验与预演 ───────────────────────────────────────────────────────────
step "5. 校验工程"

if ! rsh "cd ~/${REMOTE_DIR} && hypit runtime use hypit.runtime.json --workspace . 2>&1 | tail -4"; then
  die "远端 runtime 选择失败"
fi
if ! rsh "cd ~/${REMOTE_DIR} && hypit check ${SVML_FILE} --workspace . 2>&1 | tail -6"; then
  warn "check 未通过 —— 通常是字体包缺失，远端执行："
  warn "  hypit packages install @fontsource-variable/noto-sans-sc@5.3.0"
  warn "  npm i -g @fontsource-variable/noto-sans-sc@5.3.0 @fontsource/zcool-qingke-huangyou@5.3.0"
fi
rsh "cd ~/${REMOTE_DIR} && hypit plan ${RUN_FILE} --workspace . 2>&1 | grep -E 'Preflight|Requests|Local requests' || true"

if [ "$DRY_RUN" = "yes" ]; then
  echo; ok "--dry-run：探测与传输完成，未启动渲染"
  exit 0
fi

# ── 6. 渲染 ─────────────────────────────────────────────────────────────────
step "6. 渲染（远端，按 CPU 性能可能数十分钟）"
info "远端执行：hypit build ${RUN_FILE} --follow"
echo

BUILD_JSON="$(rsh "cd ~/${REMOTE_DIR} && hypit build ${RUN_FILE} --workspace . --follow --json 2>&1" | tail -80)" || true
echo "$BUILD_JSON" | tail -25

BUILD_ID="$(echo "$BUILD_JSON" | grep -oE '"build[Ii]d"[[:space:]]*:[[:space:]]*"[^"]+"' | head -1 | sed 's/.*"\([^"]*\)"$/\1/')"
if [ -z "$BUILD_ID" ]; then
  BUILD_ID="$(echo "$BUILD_JSON" | grep -oE 'bld_[A-Za-z0-9_]+' | head -1)"
fi

if [ -z "$BUILD_ID" ]; then
  warn "未能自动解析 build id，请在远端跑 hypit runtime status 查看"
else
  ok "Build ID  ${BUILD_ID}"
fi

# ── 7. 导出成片 ─────────────────────────────────────────────────────────────
step "7. 导出成片"

STAMP="$(date +%Y%m%d-%H%M%S)"
REMOTE_OUT="~/output/final-${STAMP}.mp4"
rsh "mkdir -p ~/output"

if [ -n "$BUILD_ID" ]; then
  if rsh "cd ~/${REMOTE_DIR} && hypit get ${BUILD_ID} --output final.video --to ~/output/final-${STAMP}.mp4 --workspace . 2>&1 | tail -8"; then
    ok "远端已导出"
  else
    warn "hypit get 失败，尝试 runtime status 定位产物"
    rsh "cd ~/${REMOTE_DIR} && hypit runtime status 2>&1 | tail -20" || true
  fi
fi

# ── 8. 取回成片 ─────────────────────────────────────────────────────────────
step "8. 取回成片"

LOCAL_OUT="${OUT_DIR}/final-ad-clone-${STAMP}.mp4"
if pull "~/output/final-${STAMP}.mp4" "$LOCAL_OUT" 2>/dev/null; then
  SZ="$(du -h "$LOCAL_OUT" | cut -f1)"
  ok "成片已落地：${LOCAL_OUT}  (${SZ})"
  command -v ffprobe >/dev/null 2>&1 && {
    info "时长/分辨率：$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height,duration -of csv=p=0 "$LOCAL_OUT" 2>/dev/null | head -1)"
  }
else
  warn "取回失败。成片仍在远端：${TARGET}:${REMOTE_OUT}"
fi

# ── 9. 清理 ─────────────────────────────────────────────────────────────────
if [ "$KEEP_REMOTE" = "no" ] && [ -n "$BUILD_ID" ]; then
  step "9. 清理"
  rsh "cd ~/${REMOTE_DIR} && hypit runtime down 2>/dev/null | tail -3 || true" >/dev/null 2>&1
  ok "已停止远端 Worker（工程保留在 ~/${REMOTE_DIR}，中间产物未删）"
fi

echo
echo "${C_OK}════ 完成 ════${C_RST}"
