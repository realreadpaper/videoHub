#!/usr/bin/env bash
# ============================================================================
#  hypit-remote-bootstrap.sh — 在远端 Linux 服务器上一键装好 hypit 渲染环境
# ----------------------------------------------------------------------------
#  用途：
#    让一台 Linux 机器（纯 CPU 云主机 / 4090 GPU 机都行）具备「渲染 hypit 成片」
#    的能力。成片渲染 = ffmpeg + Chrome 逐帧截图 + 编码，全程吃 CPU，不吃 GPU。
#    GPU 只有在跑 AI 生成模型（FastVideo 等）时才有用，和出片本身无关。
#
#  装什么（全部幂等，已就绪自动跳过）：
#    ① 系统依赖：ffmpeg + Chrome 运行库 + 中文字体包
#    ② ffmpeg 版本闸门（apt 自带的不够，自动换静态构建 · 实测坑）
#    ③ Node 22 LTS（tarball 装法，不污染系统包管理）
#    ④ @hypit/hypit CLI + hyperframes CLI（版本与 provider 声明对齐）
#    ④b 修复 hypit 内部包软链（npm 发布版不带 workspace 包 · 实测坑）
#    ④c hyperframes 运行时包（@hyperframes/engine / producer）
#    ⑤ 作者字体包（必须 hypit 与 npm 双装 · 实测坑）
#    ⑥ chrome-headless-shell（只能走 hyperframes 官方入口 · 实测坑）
#    ⑦ 逐项体检，不通过就明确告诉你缺什么
#
#  用法：
#     bash hypit-remote-bootstrap.sh                    # 默认：国内镜像 + 自动架构
#     bash hypit-remote-bootstrap.sh --no-mirror        # 海外机器走官方源
#     bash hypit-remote-bootstrap.sh --skip-chrome      # 只装 CLI，不装浏览器
#     bash hypit-remote-bootstrap.sh --node 22.22.2     # 指定 Node 版本
#     bash hypit-remote-bootstrap.sh --help
#
#  说明：
#    · 需要 root 或 sudo。脚本会自己判断用不用 sudo。
#    · x86_64 / aarch64 自动识别，Node 与 Chrome 都会选对架构。
#    · 国内镜像指：清华 apt 源 + npmmirror 的 node/chrome/npm 三处镜像。
# ============================================================================

set -uo pipefail

NODE_VERSION="22.22.2"
HYIT_VERSION="0.1.10"
HYPERFRAMES_VERSION="0.7.101"
USE_MIRROR="auto"
SKIP_CHROME="no"
PUPPETEER_CACHE="${HOME}/.cache/puppeteer"

usage() {
  sed -n '2,32p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
}

while [ $# -gt 0 ]; do
  case "$1" in
    --node)          NODE_VERSION="$2"; shift 2 ;;
    --hypit)         HYIT_VERSION="$2"; shift 2 ;;
    --hyperframes)   HYPERFRAMES_VERSION="$2"; shift 2 ;;
    --mirror)        USE_MIRROR="yes"; shift ;;
    --no-mirror)     USE_MIRROR="no"; shift ;;
    --skip-chrome)   SKIP_CHROME="yes"; shift ;;
    --help|-h)       usage ;;
    *) echo "未知参数: $1"; usage ;;
  esac
done

# ── 输出小工具 ──────────────────────────────────────────────────────────────
C_OK=$'\033[32m'; C_WARN=$'\033[33m'; C_ERR=$'\033[31m'; C_DIM=$'\033[2m'; C_RST=$'\033[0m'
step() { echo; echo "${C_OK}════ $* ════${C_RST}"; }
ok()   { echo "  ${C_OK}✓${C_RST} $*"; }
warn() { echo "  ${C_WARN}!${C_RST} $*"; }
die()  { echo "  ${C_ERR}✗${C_RST} $*"; exit 1; }
info() { echo "  ${C_DIM}$*${C_RST}"; }

# ── 0. 环境侦察 ─────────────────────────────────────────────────────────────
step "0. 环境侦察"

[ "$(uname -s)" = "Linux" ] || die "本脚本只面向 Linux 远端服务器。当前系统：$(uname -s)"

ARCH_RAW="$(uname -m)"
case "$ARCH_RAW" in
  x86_64|amd64)  NODE_ARCH="x64";    CHROME_PLATFORM="linux64" ;;
  aarch64|arm64) NODE_ARCH="arm64";  CHROME_PLATFORM="linux-arm64" ;;
  *) die "不支持的架构：$ARCH_RAW" ;;
esac

if [ "$(id -u)" -eq 0 ]; then
  SUDO=""
elif command -v sudo >/dev/null 2>&1; then
  SUDO="sudo"
else
  die "需要 root 或 sudo 权限"
fi

if ! command -v apt-get >/dev/null 2>&1; then
  die "本脚本目前只支持 Debian/Ubuntu 系（找不到 apt-get）。请告知你的发行版，我再补一版。"
fi

DISTRO="$( (. /etc/os-release 2>/dev/null && echo "$PRETTY_NAME") || echo "unknown Linux" )"
ok "系统      $DISTRO"
ok "架构      $ARCH_RAW  (node=$NODE_ARCH, chrome=$CHROME_PLATFORM)"
ok "权限      ${SUDO:-root}"
ok "CPU 核心  $(nproc 2>/dev/null || echo '?')"
if command -v nvidia-smi >/dev/null 2>&1; then
  ok "GPU       $(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null | head -1)"
else
  info "未检测到 nvidia-smi —— 不影响出片（渲染走 CPU）"
fi
# 磁盘空间
AVAIL_KB="$(df -Pk "${HOME}" | awk 'NR==2{print $4}')"
AVAIL_GB=$(( AVAIL_KB / 1024 / 1024 ))
if [ "$AVAIL_GB" -lt 5 ]; then
  warn "可用空间仅 ${AVAIL_GB}GB，建议 ≥5GB（Chrome+Node+依赖约 1.5GB，渲染中间帧另算）"
else
  ok "可用空间  ${AVAIL_GB}GB"
fi

# ── 1. 镜像决策 ─────────────────────────────────────────────────────────────
step "1. 选择下载源"

if [ "$USE_MIRROR" = "auto" ]; then
  # 用 nodejs.org 探测，3 秒内不通就切国内镜像
  if curl -fsS --max-time 3 -o /dev/null https://nodejs.org/dist/index.json 2>/dev/null; then
    USE_MIRROR="no"; ok "官方源可达，使用官方源"
  else
    USE_MIRROR="yes"; warn "官方源不可达，自动切换国内镜像"
  fi
fi

if [ "$USE_MIRROR" = "yes" ]; then
  APT_MIRROR="mirrors.tuna.tsinghua.edu.cn"
  NODE_BASE="https://cdn.npmmirror.com/binaries/node"
  CHROME_BASE="https://cdn.npmmirror.com/binaries/chrome-for-testing"
  NPM_REGISTRY="https://registry.npmmirror.com"
  ok "清华 apt 源 / npmmirror 三类镜像"
else
  APT_MIRROR=""
  NODE_BASE="https://nodejs.org/dist"
  CHROME_BASE="https://storage.googleapis.com/chrome-for-testing-public"
  NPM_REGISTRY="https://registry.npmjs.org"
  ok "官方源"
fi

# ── 2. 系统依赖 ─────────────────────────────────────────────────────────────
step "2. 系统依赖（ffmpeg + Chrome 运行库 + 中文字体）"

if [ -n "$APT_MIRROR" ]; then
  if [ -f /etc/apt/sources.list.d/debian.sources ]; then
    $SUDO sed -i "s|deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources 2>/dev/null || true
    info "已切换 debian.sources → ${APT_MIRROR}"
  fi
  if [ -f /etc/apt/sources.list ]; then
    $SUDO sed -i -E "s|https?://(archive\|security)\.ubuntu\.com|https://${APT_MIRROR}|g" /etc/apt/sources.list 2>/dev/null || true
    $SUDO sed -i -E "s|https?://(archive\|security)\.ubuntu\.com|https://${APT_MIRROR}|g" /etc/apt/sources.list.d/*.sources 2>/dev/null || true
    info "已切换 ubuntu 源 → ${APT_MIRROR}"
  fi
fi

export DEBIAN_FRONTEND=noninteractive
$SUDO apt-get update -qq 2>&1 | tail -2

# ffmpeg 是媒体管线的硬依赖；其余是 Chrome headless 的运行库
APT_PKGS="ffmpeg unzip curl ca-certificates xz-utils fonts-liberation fonts-noto-cjk"
APT_PKGS="$APT_PKGS libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2"
APT_PKGS="$APT_PKGS libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2"
APT_PKGS="$APT_PKGS libgbm1 libpango-1.0-0 libcairo2 libasound2"

# libasound2 在较新发行版改名 libasound2t64，做一个兼容兜底
if ! $SUDO apt-get install -y -qq $APT_PKGS >/tmp/hypit-apt.log 2>&1; then
  info "依赖安装报错，尝试用 libasound2t64 兜底（Ubuntu 24.04+）"
  APT_PKGS="$(echo "$APT_PKGS" | sed 's/libasound2/libasound2t64/')"
  $SUDO apt-get install -y -qq $APT_PKGS >>/tmp/hypit-apt.log 2>&1 \
    || { tail -20 /tmp/hypit-apt.log; die "系统依赖安装失败，详见 /tmp/hypit-apt.log"; }
fi

command -v ffmpeg >/dev/null 2>&1 && ok "ffmpeg  $(ffmpeg -version 2>/dev/null | head -1 | cut -d' ' -f1-3)" || die "ffmpeg 安装失败"
command -v fc-list >/dev/null 2>&1 && {
  CJK="$(fc-list :lang=zh 2>/dev/null | wc -l)"
  [ "$CJK" -gt 0 ] && ok "中文字体  ${CJK} 个可用" || warn "未找到中文字体，字幕/文本层可能显示为方块"
}

# ── 2b. ffmpeg 版本闸门（实测两个坑，必踩） ─────────────────────────────────
#  坑一 · 老版本直接报参数错：
#    Ubuntu 22.04 → 4.4、Debian 12 → 5.1、Ubuntu 24.04 → 6.1，这些版本一律不行。
#    hypit 把 `-autorotate` 放在输出位置，老版本拒绝：
#      "Option autorotate ... cannot be applied to output url ... Invalid argument"
#
#  坑二 · 7.x 能过参数校验，但会静默丢帧（更隐蔽）：
#    同一素材、同一条 filter，计划输出 2826 帧，ffmpeg 7.0.2 只产出 2356 帧（少 16%）。
#    于是撞上 hypit 的帧数断言：
#      "Normalized visual frame shape differs from its plan"
#    对照实测：ffmpeg 9.0.1 输出 2826 帧（正确）。所以闸门必须卡在 ≥8。
#
#  结论：apt 装的版本不够，johnvansickle 的 7.0.2 静态构建也不够。
#        用 BtbN 的滚动构建（当前 9.x），实测可用。
FF_MAJOR="$(ffmpeg -version 2>/dev/null | head -1 | sed -E 's/.*version ([0-9]+).*/\1/')"
FF_MAJOR="${FF_MAJOR:-0}"

if [ "$FF_MAJOR" -ge 8 ]; then
  ok "ffmpeg 主版本 ${FF_MAJOR} ≥ 8，满足 hypit 要求"
else
  warn "系统 ffmpeg 是 ${FF_MAJOR}.x，低于 hypit 要求（≥8），换装静态构建"

  if [ "$USE_MIRROR" = "yes" ]; then
    GH="https://ghfast.top/https://github.com"
    warn "GitHub 直连可能很慢，走加速前缀"
  else
    GH="https://github.com"
  fi

  case "$NODE_ARCH" in
    arm64)
      FF_URLS="${GH}/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linuxarm64-gpl.tar.xz
https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz" ;;
    x64)
      FF_URLS="${GH}/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz
https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz" ;;
  esac

  FF_TMP=/tmp/ffmpeg-static.tar.xz
  FF_GOT="no"
  while IFS= read -r url; do
    [ -n "$url" ] || continue
    info "尝试 ${url%%/releases*}"
    if curl -fL --retry 1 --max-time 900 -o "$FF_TMP" "$url"; then FF_GOT="yes"; break; fi
    warn "该源不可用，换下一个"
  done <<EOF
$FF_URLS
EOF

  if [ "$FF_GOT" = "yes" ]; then
    FF_DIR=/tmp/ffmpeg-extract
    rm -rf "$FF_DIR"; mkdir -p "$FF_DIR"
    tar -xJf "$FF_TMP" -C "$FF_DIR" 2>/dev/null || tar -xf "$FF_TMP" -C "$FF_DIR"
    FF_BIN="$(find "$FF_DIR" -type f -name ffmpeg  -perm -u+x 2>/dev/null | head -1)"
    FP_BIN="$(find "$FF_DIR" -type f -name ffprobe -perm -u+x 2>/dev/null | head -1)"
    if [ -n "$FF_BIN" ] && [ -n "$FP_BIN" ]; then
      $SUDO mkdir -p /opt/ffmpeg-static
      $SUDO install -m 0755 "$FF_BIN" /opt/ffmpeg-static/ffmpeg
      $SUDO install -m 0755 "$FP_BIN" /opt/ffmpeg-static/ffprobe
      for b in ffmpeg ffprobe; do
        $SUDO ln -sf "/opt/ffmpeg-static/${b}" "/usr/local/bin/${b}"
      done
      hash -r 2>/dev/null || true
      NEW_MAJOR="$(/usr/local/bin/ffmpeg -version 2>/dev/null | head -1 | sed -E 's/.*version ([0-9]+).*/\1/')"
      if [ "${NEW_MAJOR:-0}" -ge 8 ]; then
        ok "已换用 ffmpeg ${NEW_MAJOR}.x · $(/usr/local/bin/ffmpeg -version 2>/dev/null | head -1 | cut -d' ' -f1-3)"
        info "路径 /usr/local/bin/ffmpeg（务必确认它在 PATH 里优先于 /usr/bin/ffmpeg）"
      else
        warn "装上了但版本仍是 ${NEW_MAJOR}.x，请手动确认"
      fi
    else
      warn "压缩包解不出 ffmpeg/ffprobe，请手动安装"
    fi
    rm -rf "$FF_DIR" "$FF_TMP"
  else
    warn "静态构建下载失败。备用方案（任选其一）："
    warn "  · conda： micromamba create -y -p /opt/ffmpeg -c https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge 'ffmpeg>=8'"
    warn "  · 手动： 从 https://github.com/BtbN/FFmpeg-Builds/releases 下 linux64 / linuxarm64 的 gpl 构建，"
    warn "          解压后把 bin/ffmpeg、bin/ffprobe 放到 /opt/ffmpeg-static 并软链进 /usr/local/bin"
    warn "  · 注意：不要用 johnvansickle 的 7.0.2（会丢帧），也不要依赖 apt 版本"
  fi
fi

# 记录最终生效的 ffmpeg，写进 runtime 配置时要用绝对路径
FFMPEG_FINAL="$(command -v ffmpeg)"
ok "最终 ffmpeg → ${FFMPEG_FINAL}"

# ── 3. Node 22 ──────────────────────────────────────────────────────────────
step "3. Node ${NODE_VERSION}"

NEED_NODE="yes"
if command -v node >/dev/null 2>&1; then
  CUR="$(node -v 2>/dev/null | sed 's/^v//')"
  if [ "$(printf '%s\n%s\n' "22.15.0" "$CUR" | sort -V | head -1)" = "22.15.0" ]; then
    ok "已有 node v${CUR}（≥22.15.0，满足 hypit 要求）"
    NEED_NODE="no"
  else
    warn "已有 node v${CUR} < 22.15.0，将并存安装新版本"
  fi
fi

if [ "$NEED_NODE" = "yes" ]; then
  TARBALL="node-v${NODE_VERSION}-linux-${NODE_ARCH}.tar.xz"
  URL="${NODE_BASE}/v${NODE_VERSION}/${TARBALL}"
  info "下载 ${URL}"
  curl -fL --retry 3 --max-time 600 -o "/tmp/${TARBALL}" "$URL" || die "Node 下载失败"
  NODE_PREFIX="/usr/local/lib/nodejs"
  $SUDO mkdir -p "$NODE_PREFIX"
  $SUDO tar -xJf "/tmp/${TARBALL}" -C "$NODE_PREFIX" || die "Node 解包失败"
  NODE_BIN_DIR="${NODE_PREFIX}/node-v${NODE_VERSION}-linux-${NODE_ARCH}/bin"
  for b in node npm npx corepack; do
    [ -e "${NODE_BIN_DIR}/${b}" ] && $SUDO ln -sf "${NODE_BIN_DIR}/${b}" "/usr/local/bin/${b}"
  done
  rm -f "/tmp/${TARBALL}"
  ok "node $(node -v)   npm $(npm -v)"
else
  NODE_BIN_DIR="$(dirname "$(command -v node)")"
fi

# ── 4. hypit + hyperframes ──────────────────────────────────────────────────
step "4. hypit CLI + hyperframes CLI"

npm config set registry "$NPM_REGISTRY" >/dev/null 2>&1 || true
info "npm registry = ${NPM_REGISTRY}"

if command -v hypit >/dev/null 2>&1 && [ "$(hypit --version 2>/dev/null)" = "$HYIT_VERSION" ]; then
  ok "hypit ${HYIT_VERSION} 已就绪"
else
  info "安装 @hypit/hypit@${HYIT_VERSION} …"
  npm i -g "@hypit/hypit@${HYIT_VERSION}" >/tmp/hypit-install.log 2>&1 \
    || { tail -20 /tmp/hypit-install.log; die "hypit 安装失败"; }
  ok "hypit 安装完成"
fi

if command -v hyperframes >/dev/null 2>&1 && [ "$(hyperframes --version 2>/dev/null | head -1 | tr -d 'v')" = "$HYPERFRAMES_VERSION" ]; then
  ok "hyperframes ${HYPERFRAMES_VERSION} 已就绪"
else
  info "安装 hyperframes@${HYPERFRAMES_VERSION}（必须与 provider 声明版本一致）…"
  npm i -g "hyperframes@${HYPERFRAMES_VERSION}" >/tmp/hyperframes-install.log 2>&1 \
    || { tail -20 /tmp/hyperframes-install.log; die "hyperframes 安装失败"; }
  ok "hyperframes 安装完成"
fi

# 修 PATH：npm 全局 bin 有时不在 /usr/local/bin，补软链
NPM_PREFIX="$(npm prefix -g 2>/dev/null)"
if [ -n "$NPM_PREFIX" ] && [ -d "${NPM_PREFIX}/bin" ]; then
  LINKED=0
  for f in "${NPM_PREFIX}/bin"/*; do
    [ -e "$f" ] || continue
    b="$(basename "$f")"
    [ -e "/usr/local/bin/${b}" ] && continue
    $SUDO ln -sf "$f" "/usr/local/bin/${b}" 2>/dev/null && LINKED=$((LINKED+1))
  done
  [ "$LINKED" -gt 0 ] && ok "补链 ${LINKED} 个命令到 /usr/local/bin"
fi

command -v hypit >/dev/null 2>&1 || die "hypit 不在 PATH，请检查 npm prefix（$(npm prefix -g 2>/dev/null)）"
ok "hypit $(hypit --version)   hyperframes $(hyperframes --version 2>/dev/null | head -1)"

# ── 4b. 修复 hypit 内部包链接（实测坑，必踩） ───────────────────────────────
#  背景：@hypit/hypit 的 packages/* 里大量内部包是 "private": true + workspace:* 协议。
#       monorepo 里由 pnpm 负责建立链接；npm 的**发布版不会建**。
#       于是 provider 里这行 import 直接崩：
#         import ... from "@hypit/hyperframes/project"
#       → ERR_MODULE_NOT_FOUND: Cannot find package '@hypit/hyperframes'
#       Build 表现为「跑过前两步后突然报缺包」，看起来像环境不全，其实是发布包的
#       链接缺失。本地容器实测：补完 112 个软链后这一步才过。
#  做法：把 $HB/packages/* 全部软链进 $HB/node_modules/@hypit/（幂等，可重复跑）。
step "4b. 修复 hypit 内部包链接"

HB="$(npm prefix -g 2>/dev/null)/lib/node_modules/@hypit/hypit"
if [ -d "${HB}/packages" ]; then
  $SUDO mkdir -p "${HB}/node_modules/@hypit"
  LINK_MADE=0
  for d in "${HB}"/packages/*/; do
    [ -d "$d" ] || continue
    n="$(basename "$d")"
    if [ ! -e "${HB}/node_modules/@hypit/${n}" ]; then
      if [ -w "${HB}/node_modules/@hypit" ]; then
        ln -s "$d" "${HB}/node_modules/@hypit/${n}" 2>/dev/null && LINK_MADE=$((LINK_MADE+1))
      else
        $SUDO ln -s "$d" "${HB}/node_modules/@hypit/${n}" 2>/dev/null && LINK_MADE=$((LINK_MADE+1))
      fi
    fi
  done
  LINK_TOTAL="$(ls -1 "${HB}/node_modules/@hypit" 2>/dev/null | wc -l | tr -d ' ')"
  ok "内部包链接 ${LINK_TOTAL} 个（本次新建 ${LINK_MADE}）"
  LINK_MISS=0
  for p in hyperframes media-track media-execution provider-hyperframes-local endpoint-kit; do
    [ -e "${HB}/node_modules/@hypit/${p}" ] || { warn "缺 @hypit/${p}"; LINK_MISS=$((LINK_MISS+1)); }
  done
  [ "$LINK_MISS" -eq 0 ] && ok "关键内部包全部可解析"
else
  warn "未找到 ${HB}/packages —— hypit 安装结构异常，请检查 npm prefix"
fi

# ── 4c. hyperframes 运行时包 ────────────────────────────────────────────────
#  与内部包同理：@hyperframes/engine 等也要「双处」可解析。
#  （本地容器里装到这一步就被打断，未跑完整轮验证；远端若报缺包，先看这里。）
step "4c. hyperframes 运行时包"
for p in "@hyperframes/engine" "@hyperframes/producer"; do
  npm i -g "${p}@${HYPERFRAMES_VERSION}" >/dev/null 2>&1 \
    && ok "npm 全局 ${p}@${HYPERFRAMES_VERSION}" || warn "npm 全局 ${p} 安装异常"
  hypit packages install "${p}@${HYPERFRAMES_VERSION}" >/dev/null 2>&1 \
    && ok "hypit 包  ${p}@${HYPERFRAMES_VERSION}" || warn "hypit 包 ${p} 安装异常"
done

# ── 5. 作者字体包 ───────────────────────────────────────────────────────────
#  实测坑：字体要「两处都装」才生效 ——
#    · `hypit packages install` 让它进 hypit 的 machine home（check 阶段查这个）
#    · `npm i -g`                让 Node 能全局解析到（渲染阶段查这个）
#  只装一处会出现「check 过了、渲染报缺字体」或反过来的错位。
step "5. 作者字体包"

install_font_pkg() {
  local pkg="$1" ver="$2"
  hypit packages install "${pkg}@${ver}" >/dev/null 2>&1 && ok "hypit 包  ${pkg}@${ver}" || warn "hypit 包 ${pkg} 安装异常"
  npm i -g "${pkg}@${ver}" >/dev/null 2>&1 && ok "npm 全局 ${pkg}@${ver}" || warn "npm 全局 ${pkg} 安装异常"
}

if [ -d "${HOME}/.local/state/hypit/packages/@fontsource-variable/noto-sans-sc/5.3.0" ] \
   || [ -d "${HOME}/Library/Application Support/hypit/packages/@fontsource-variable/noto-sans-sc/5.3.0" ]; then
  ok "字体包已就绪，跳过"
else
  info "安装中文字体（作品里用到的 noto-sans-sc / zcool-qingke-huangyou）…"
  install_font_pkg "@fontsource-variable/noto-sans-sc" "5.3.0"
  install_font_pkg "@fontsource/zcool-qingke-huangyou" "5.3.0"
  info "如果作品里还用到别的字体，hypit check 会直接报出「需要的包名@精确版本」，照着再装一次即可。"
fi

# ── 6. 无头浏览器 ───────────────────────────────────────────────────────────
#  实测坑：hyperframes 渲染要的是 **chrome-headless-shell**，不是完整版 Chrome。
#  官方入口是 `hyperframes browser ensure`，它会自己找到或下载正确的构建。
#  手动塞 puppeteer 的完整 Chrome 进去是没用的 —— preflight 会直接判 provider 不可用。
step "6. 无头浏览器（chrome-headless-shell）"

export PUPPETEER_DOWNLOAD_BASE_URL="$CHROME_BASE"

if [ "$SKIP_CHROME" = "yes" ]; then
  warn "--skip-chrome 已指定，跳过"
elif [ -n "$(hyperframes browser path 2>/dev/null | tail -1 | grep -E '^/')" ]; then
  ok "已就绪：$(hyperframes browser path 2>/dev/null | tail -1)"
else
  info "通过 hyperframes 官方入口获取（约 100MB）…"
  hyperframes browser ensure >/tmp/chrome-install.log 2>&1 \
    || warn "下载失败，可稍后手动执行：hyperframes browser ensure --force"
  BP="$(hyperframes browser path 2>/dev/null | tail -1)"
  if [ -n "$BP" ] && [ -x "$BP" ]; then
    ok "浏览器：${BP}"
    # hypit 的 preflight 会检查这个变量；ssh 非交互会话（bash -lc）拿不到交互式 PATH，
    # 所以同时写 ~/.bashrc（带 guard，幂等）和 ~/.hypit-browser-env。
    cat > "${HOME}/.hypit-browser-env" <<EOF
export HYPERFRAMES_BROWSER_PATH="${BP}"
EOF
    BRC="${HOME}/.bashrc"
    touch "$BRC"
    if ! grep -q "HYPERFRAMES_BROWSER_PATH" "$BRC" 2>/dev/null; then
      {
        echo ""
        echo "# hypit 渲染所需（由 hypit-remote-bootstrap.sh 写入）"
        echo "[ -f \"\${HOME}/.hypit-browser-env\" ] && . \"\${HOME}/.hypit-browser-env\""
      } >> "$BRC"
      ok "已写入 ~/.bashrc（新会话自动生效）"
    else
      info "~/.bashrc 已有该变量，跳过"
    fi
    info "当前会话生效： . ~/.hypit-browser-env"
  else
    warn "未拿到浏览器路径，后续渲染会报 MANAGED_PROGRAM_DOWN"
    warn "手动修复： hyperframes browser ensure --force  然后 hyperframes browser path"
  fi
fi

# ── 7. 验证 ─────────────────────────────────────────────────────────────────
step "7. 逐项体检"

FAIL=0
check() { if eval "$2" >/dev/null 2>&1; then ok "$1"; else warn "$1 未就绪"; FAIL=$((FAIL+1)); fi; }
check "node        $(node -v 2>/dev/null)"  "node -v"
check "hypit       $(hypit --version 2>/dev/null)" "hypit --version"
check "hyperframes $(hyperframes --version 2>/dev/null | head -1)" "hyperframes --version"
FFV="$(ffmpeg -version 2>/dev/null | head -1 | cut -d' ' -f1-3)"
FFMAJ="$(ffmpeg -version 2>/dev/null | head -1 | sed -E 's/.*version ([0-9]+).*/\1/')"
if [ "${FFMAJ:-0}" -ge 8 ]; then ok "ffmpeg      ${FFV}  (≥8 ✓)"; else warn "ffmpeg      ${FFV}  (需要 ≥8，会丢帧/报错)"; FAIL=$((FAIL+1)); fi
check "浏览器      $(hyperframes browser path 2>/dev/null | tail -1)" "hyperframes browser path 2>/dev/null | tail -1 | grep -qE '^/'"
HB2="$(npm prefix -g 2>/dev/null)/lib/node_modules/@hypit/hypit"
check "内部包链接  $(ls -1 "${HB2}/node_modules/@hypit" 2>/dev/null | wc -l | tr -d ' ') 个" "[ -e '${HB2}/node_modules/@hypit/hyperframes' ]"

echo
if [ "$FAIL" -eq 0 ]; then
  echo "${C_OK}════ 环境就绪 ════${C_RST}"
  echo
  echo "接下来（在工程目录里执行）："
  echo "  . ~/.hypit-browser-env                    # 当前会话导入浏览器路径"
  echo "  hypit runtime use hypit.runtime.json --workspace ."
  echo "  hypit check productions/ad-clone/authors/main.svml --workspace ."
  echo "  hypit plan  productions/ad-clone/runs/final.svrun --workspace ."
  echo "  hypit build productions/ad-clone/runs/final.svrun --workspace . --follow"
  echo
  echo "预期：check → Outputs 19；plan → Requests 5 / Local requests 5（零 Provider 费用）"
else
  echo "${C_WARN}════ 有 ${FAIL} 项未就绪，请按上面提示补装 ════${C_RST}"
  exit 1
fi
