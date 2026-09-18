#!/usr/bin/env bash
#
# Hypit 本地渲染验证脚本
# ---------------------------------------------------------------------------
# 用途：跑通「源码 → 渲染 → 成片」全链路，产出零模型费用的 8 秒示例视频。
#
# 重要：请在 macOS 自带的「终端」(Terminal.app) 或 iTerm 里运行本脚本。
#       不要在 AI 助手的沙箱环境里跑 —— 沙箱禁用了 `ps` 命令，而渲染引擎
#       在收尾阶段要用 `ps` 枚举进程树来清理 Chrome 子进程，会报
#       "Render cleanup failed; Error: spawn EPERM"。
#
# 用法：
#   bash ~/Desktop/videoHub/videos/demo/render-demo.sh
#
set -euo pipefail

HYPIT_ROOT="/Users/hejianglong/Desktop/videoHub/repos/hypit"
EXAMPLE_DIR="$HYPIT_ROOT/examples/semantic-composition"
OUT_DIR="$HOME/Desktop/videoHub/videos/demo/output"

export COREPACK_ENABLE_DOWNLOAD_PROMPT=0

cd "$HYPIT_ROOT"

echo "═══════════════════════════════════════════════"
echo " Step 1/4  校验 SVML 源码"
echo "═══════════════════════════════════════════════"
node bin/hypit.mjs check \
  examples/semantic-composition/chat.svml \
  --workspace "$EXAMPLE_DIR"

echo
echo "═══════════════════════════════════════════════"
echo " Step 2/4  提交渲染（纯本地，无模型费用）"
echo "═══════════════════════════════════════════════"
BUILD_LOG="$(mktemp)"
node bin/hypit.mjs build \
  examples/semantic-composition/chat.svrun \
  --workspace "$EXAMPLE_DIR" \
  --runtime "$EXAMPLE_DIR/hypit.runtime.json" \
  --follow | tee "$BUILD_LOG"

BUILD_ID="$(grep -oE 'bld_[0-9TZ]+_[A-Z0-9]+' "$BUILD_LOG" | head -1)"
if [ -z "$BUILD_ID" ]; then
  echo "✗ 未能解析 Build ID，请查看上面的输出。" >&2
  exit 1
fi
echo
echo "Build ID = $BUILD_ID"

echo
echo "═══════════════════════════════════════════════"
echo " Step 3/4  导出成片"
echo "═══════════════════════════════════════════════"
mkdir -p "$OUT_DIR"
node bin/hypit.mjs get "$BUILD_ID" \
  --output final.video \
  --to "$OUT_DIR/chat-demo.mp4" \
  --workspace "$EXAMPLE_DIR"

echo
echo "═══════════════════════════════════════════════"
echo " Step 4/4  完成"
echo "═══════════════════════════════════════════════"
ls -lh "$OUT_DIR/chat-demo.mp4"
echo
echo "成片路径：$OUT_DIR/chat-demo.mp4"
echo "打开看看：open \"$OUT_DIR\""
