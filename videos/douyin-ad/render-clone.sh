#!/usr/bin/env bash
# 复刻工程渲染脚本 —— 必须在 Termimal.app 里跑，不要在受限环境里跑。
# 原因：Hypit 渲染收尾用 `ps -A -o pid=,ppid=` 枚举进程树回收 Chrome 子进程，受限环境禁用 ps 会 EPERM。
set -euo pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="$HOME/.npm-global/bin:$PATH"

command -v hypit >/dev/null 2>&1 || { echo "✗ 找不到 hypit，请先 npm install -g @hypit/hypit"; exit 1; }
command -v hyperframes >/dev/null 2>&1 || { echo "✗ 找不到 hyperframes，请先 npm install -g hyperframes@0.7.101"; exit 1; }

cd "$PROJECT"

RUN="productions/ad-clone/runs/final.svrun"

echo "════ 1. 选择 Runtime Profile ════"
hypit runtime use hypit.runtime.json --workspace . >/dev/null && echo "✓ 已选择 hypit.runtime.json"

echo
echo "════ 2. 校验源码 ════"
hypit check productions/ad-clone/authors/main.svml --workspace .

echo
echo "════ 3. 预演（确认零模型费用）════"
hypit plan "$RUN" --workspace . | grep -E "Preflight|Requests|Local requests" || true

echo
echo "════ 4. 渲染（约 2832 帧，请耐心等待）════"
hypit build "$RUN" --workspace . --follow

echo
echo "════ 5. 导出成片 ════"
# 列出本次 Build，取最近一条的 id
hypit list --workspace . 2>/dev/null | tail -5 || true
echo
echo "导出命令（把 <build-id> 换成上面列出的 id）："
echo "  hypit get <build-id> --output final.video --to output/final-ad-clone.mp4 --workspace ."
echo
echo "完成后成片默认落在 $PROJECT/output/"
