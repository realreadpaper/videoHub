#!/usr/bin/env bash
# ============================================================================
#  render-local.sh — 抖音带货复刻工程：一键渲染成片
# ----------------------------------------------------------------------------
#  ⚠️  请在**你自己的终端**里执行（Terminal.app / iTerm）。
#      不要在 AI 对话环境里跑：那边的沙箱会对文件删除做批量计数，
#      hypit 渲染收尾时清理自己的临时产物会被打断，导致 Build 中止在
#      「Saving Result」阶段（报 SAFE_DELETE_BULK_CONFIRM_REQUIRED）。
#      你自己的终端没有这层限制。
#
#  用法：
#     cd ~/Desktop/videoHub/videos/douyin-ad
#     bash render-local.sh              # 全流程：体检 → 校验 → 预演 → 渲染 → 导出
#     bash render-local.sh doctor       # 只做环境体检
#     bash render-local.sh check        # 只校验工程
#     bash render-local.sh plan         # 只看请求数与费用
#     bash render-local.sh build        # 只渲染
#     bash render-local.sh get          # 只导出最后一次的成片
#
#  产物：output/final-ad-clone-<时间戳>.mp4
#
#  说明：本工程全部走本地 Provider（ffmpeg + Chrome 逐帧渲染），
#        5 个请求 0 元 Provider 费用，不需要任何 API Key。
# ============================================================================

set -uo pipefail

PROJ_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJ_DIR"

RUN_FILE="productions/ad-clone/runs/final.svrun"
SVML_FILE="productions/ad-clone/authors/main.svml"
OUT_DIR="${OUT_DIR:-${PROJ_DIR}/output}"

C_OK=$'\033[32m'; C_WARN=$'\033[33m'; C_ERR=$'\033[31m'; C_DIM=$'\033[2m'; C_RST=$'\033[0m'
step() { echo; echo "${C_OK}════ $* ════${C_RST}"; }
ok()   { echo "  ${C_OK}✓${C_RST} $*"; }
warn() { echo "  ${C_WARN}!${C_RST} $*"; }
die()  { echo "  ${C_ERR}✗${C_RST} $*"; exit 1; }
info() { echo "  ${C_DIM}$*${C_RST}"; }

# ── 依赖自检 ────────────────────────────────────────────────────────────────
need() {
  command -v "$1" >/dev/null 2>&1 || die "找不到 $1 —— $2"
}

require_tools() {
  need hypit      "安装：npm i -g @hypit/hypit@0.1.10"
  need hyperframes "安装：npm i -g hyperframes"
  need ffmpeg     "安装：brew install ffmpeg"
  need ffprobe    "安装：brew install ffmpeg"
}

# ── doctor ──────────────────────────────────────────────────────────────────
do_doctor() {
  step "环境体检"
  info "node         $(command -v node)  $(node -v 2>/dev/null)"
  info "hypit        $(command -v hypit)  $(hypit --version 2>/dev/null)"
  info "hyperframes  $(command -v hyperframes)  $(hyperframes --version 2>/dev/null | head -1)"
  info "ffmpeg       $(command -v ffmpeg)  $(ffmpeg -version 2>/dev/null | head -1 | cut -d' ' -f1-3)"
  info "ffprobe      $(command -v ffprobe)"

  echo
  # ffmpeg 版本闸门：实测 <8 会出问题
  #   · 老版本（apt 4.4/5.1/6.1）直接拒绝 -autorotate 参数
  #   · 7.x 能跑但 fps filter 静默丢帧（2826 帧只出 2356）
  FF_MAJOR="$(ffmpeg -version 2>/dev/null | head -1 | sed -E 's/.*version ([0-9]+).*/\1/')"
  if [ "${FF_MAJOR:-0}" -ge 8 ]; then
    ok "ffmpeg 主版本 ${FF_MAJOR} ≥ 8，通过"
  else
    warn "ffmpeg 主版本 ${FF_MAJOR} < 8 —— 渲染会报帧数不符。修复：brew upgrade ffmpeg"
  fi

  # hyperframes 版本：provider 声明依赖 0.7.101
  HB_VER="$(hyperframes --version 2>/dev/null | head -1 | tr -d 'v' | tr -d ' ')"
  if [ "$HB_VER" = "0.7.101" ]; then
    ok "hyperframes ${HB_VER} 与 provider 声明一致"
  else
    warn "hyperframes 是 ${HB_VER}，provider 声明的是 0.7.101"
    info "若渲染报引擎相关错误，执行： npm i -g hyperframes@0.7.101"
  fi

  # 浏览器
  if clean_bp="$(hyperframes browser path 2>/dev/null | tail -1)" && [ -x "$clean_bp" ]; then
    ok "浏览器 ${clean_bp}"
  else
    warn "未找到无头浏览器 —— 执行： hyperframes browser ensure"
  fi
}

# ── check ───────────────────────────────────────────────────────────────────
do_check() {
  step "1. 校验工程"
  hypit runtime use hypit.runtime.json --workspace . 2>&1 | tail -3
  hypit check "$SVML_FILE" --workspace . 2>&1 | tail -6
}

# ── plan ────────────────────────────────────────────────────────────────────
do_plan() {
  step "2. 预演计划（确认请求数与费用）"
  hypit plan "$RUN_FILE" --workspace . 2>&1 | tail -20
}

# ── build ───────────────────────────────────────────────────────────────────
do_build() {
  step "3. 渲染（Chrome 逐帧截图 + ffmpeg 编码）"
  info "你的机器上预计几分钟到数十分钟；Ctrl-C 只停止观察，不中断渲染"
  echo
  BUILD_OUT="$(hypit build "$RUN_FILE" --workspace . --follow --color never 2>&1)"
  RC=$?
  echo "$BUILD_OUT" | tail -40

  BUILD_ID="$(echo "$BUILD_OUT" | grep -oE 'bld_[A-Za-z0-9_]+' | head -1)"
  if [ -n "$BUILD_ID" ]; then
    ok "Build ID  ${BUILD_ID}"
    printf '%s' "$BUILD_ID" > "${PROJ_DIR}/.last-build-id"
  else
    warn "未解析到 Build ID"
  fi
  [ "$RC" -eq 0 ] || warn "hypit build 退出码 ${RC}（看上面报错）"
}

# ── get ─────────────────────────────────────────────────────────────────────
do_get() {
  step "4. 导出成片"
  mkdir -p "$OUT_DIR"
  STAMP="$(date +%Y%m%d-%H%M%S)"
  TARGET="${OUT_DIR}/final-ad-clone-${STAMP}.mp4"

  BUILD_ID=""
  [ -f "${PROJ_DIR}/.last-build-id" ] && BUILD_ID="$(cat "${PROJ_DIR}/.last-build-id")"
  if [ -z "$BUILD_ID" ]; then
    BUILD_ID="$(hypit list --workspace . 2>/dev/null | grep -oE 'bld_[A-Za-z0-9_]+' | head -1)"
  fi
  [ -n "$BUILD_ID" ] || die "找不到 build 记录，请先执行 build"

  info "Build ID  ${BUILD_ID}"
  if ! hypit get "$BUILD_ID" --output final.video --to "$TARGET" --workspace . 2>&1 | tail -8; then
    warn "hypit get 失败，列出可用产物："
    hypit list --workspace . 2>&1 | tail -20
    return 1
  fi

  if [ -f "$TARGET" ]; then
    ok "成片落地：${TARGET}  ($(du -h "$TARGET" | cut -f1))"
    SPEC="$(ffprobe -v error -select_streams v:0 \
      -show_entries stream=width,height,r_frame_rate,duration -of csv=p=0 "$TARGET" 2>/dev/null | head -1)"
    [ -n "$SPEC" ] && info "规格（宽,高,帧率,时长）：${SPEC}"
    info "目录：$(dirname "$TARGET")"
  else
    warn "命令返回成功但找不到文件，检查 ${OUT_DIR}"
  fi
}

# ── 分发 ────────────────────────────────────────────────────────────────────
CMD="${1:-all}"
case "$CMD" in
  doctor) require_tools; do_doctor ;;
  check)  require_tools; do_doctor; do_check ;;
  plan)   require_tools; do_plan ;;
  build)  require_tools; do_build ;;
  get)    require_tools; do_get ;;
  all)    require_tools; do_doctor; do_check; do_plan; do_build && do_get ;;
  -h|--help|help) sed -n '2,26p' "$0" | sed 's/^# \{0,1\}//' ;;
  *) die "未知参数：$CMD（可用：doctor/check/plan/build/get/all）" ;;
esac

echo
echo "${C_OK}════ 完成 ════${C_RST}"
