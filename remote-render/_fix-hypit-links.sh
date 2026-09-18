#!/usr/bin/env bash
# 修复 npm 全局安装的 @hypit/hypit 缺失的 workspace 包链接。
# 背景：@hypit/hypit 的 packages/* 里有大量 "private": true 的内部包（workspace:* 协议），
#      npm 发布版不会为它们建立 node_modules 链接，导致 provider 里
#      `import ... from "@hypit/hyperframes/project"` 报 ERR_MODULE_NOT_FOUND。
#      在 monorepo 里由 pnpm 完成这件事；全局安装时得手动补。
set -u

HB="${1:-$(npm prefix -g)/lib/node_modules/@hypit/hypit}"

echo "hypit 安装目录: $HB"
[ -d "$HB/packages" ] || { echo "找不到 packages 目录，路径对吗？"; exit 1; }

echo ""
echo "=== provider 目录 ==="
ls "$HB/packages/provider-hyperframes-local/" 2>/dev/null | head -10

echo ""
echo "=== 补全 workspace 包软链 ==="
mkdir -p "$HB/node_modules/@hypit"
cd "$HB/node_modules/@hypit" || exit 1

MADE=0
SKIP=0
for d in "$HB"/packages/*/; do
  [ -d "$d" ] || continue
  n="$(basename "$d")"
  if [ -e "$n" ]; then
    SKIP=$((SKIP + 1))
  else
    if ln -s "$d" "$n" 2>/dev/null; then MADE=$((MADE + 1)); fi
  fi
done

echo "新建软链 : $MADE"
echo "已存在   : $SKIP"
echo "链接总数 : $(ls -1 | wc -l)"

echo ""
echo "=== 关键包验证 ==="
for p in hyperframes media media-execution render-hyperframes endpoint-kit runtime protocol; do
  if [ -e "$p" ]; then echo "  ok   @hypit/$p"; else echo "  MISS @hypit/$p"; fi
done

echo ""
echo "=== 尝试解析 ==="
cd "$HB/packages/provider-hyperframes-local" || exit 1
node --input-type=module -e 'import("@hypit/hyperframes/project").then(()=>console.log("RESOLVE: OK")).catch(e=>console.log("RESOLVE: FAIL -", e.code))' 2>&1 | tail -3
