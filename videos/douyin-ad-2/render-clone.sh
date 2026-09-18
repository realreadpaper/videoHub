#!/usr/bin/env bash
# 复刻工程一键渲染 —— 必须在 Terminal.app 里跑，不要在受限/沙箱环境里跑。
#
# 原因（实测，两条独立硬限制）：
#   1) hypit 的 Runtime Worker 在准备阶段批量清理临时文件，若环境带"删除数量护栏"
#      （如 SAFE_DELETE_BULK_CONFIRM_REQUIRED），累计到阈值即中止，Build 根本提交不进去。
#   2) 渲染收尾用 `ps -A -o pid=,ppid=` 枚举进程树回收 Chrome 子进程，环境禁 ps 会 EPERM。
# 正常终端里这两个限制都不存在。
set -euo pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="$HOME/.npm-global/bin:$PATH"

RUN="productions/ad-clone/runs/final.svrun"
AUTHOR="productions/ad-clone/authors/main.svml"

echo "════════════ 环境自检 ════════════"
command -v hypit       >/dev/null 2>&1 || { echo "✗ 找不到 hypit —— npm i -g @hypit/hypit@0.1.10"; exit 1; }
command -v hyperframes >/dev/null 2>&1 || { echo "✗ 找不到 hyperframes —— npm i -g hyperframes@0.7.101"; exit 1; }
command -v ffmpeg      >/dev/null 2>&1 || { echo "✗ 找不到 ffmpeg"; exit 1; }
echo "  hypit        $(hypit --version 2>/dev/null)"
echo "  hyperframes  $(hyperframes --version 2>/dev/null | head -1)"
echo "  ffmpeg       $(ffmpeg -version 2>/dev/null | head -1 | cut -d' ' -f1-3)"

cd "$PROJECT"

echo
echo "════════════ 1. 选择 Runtime Profile（本地 / 零模型费用）════════════"
hypit runtime use hypit.runtime.json --workspace . >/dev/null && echo "✓ 已选择 hypit.runtime.json"

echo
echo "════════════ 2. 校验源码 ════════════"
hypit check "$AUTHOR" --workspace .

echo
echo "════════════ 3. 预演（确认不发任何付费请求）════════════"
hypit plan "$RUN" --workspace . | grep -E "Preflight|Requests|Local requests" || true

echo
echo "════════════ 4. 渲染（105s × 30fps = 3150 帧，单机约数分钟）════════════"
hypit build "$RUN" --workspace . --follow

echo
echo "════════════ 5. 导出成片 ════════════"
hypit list --workspace . 2>/dev/null | tail -5 || true
echo
echo "导出（把 <build-id> 换成上面列出的 id）："
echo "  hypit get <build-id> --output final.video --to output/final-homecook.mp4 --workspace ."
echo
echo "成片默认落在：$PROJECT/output/"
