#!/bin/bash
# ==============================================================================
# A1 一键应用 · 生成「完整 VAE 解码」版 Stage2 精修工作流
#
# 干什么：
#   在远端把官方 Stage2 工作流里的 TAEHV 解码节点换成标准 VAEDecode，
#   生成一份补丁工作流，分发到三部片子的 workflows/ 目录。
#   之后 10_run_film.py 会自动优先使用它（无需再改任何东西）。
#
# 用法：
#   bash a1_apply.sh                    # 三部片子都装
#   bash a1_apply.sh --inspect          # 只看原始工作流结构，不写文件
#   bash a1_apply.sh --tiled            # 生成 VAEDecodeTiled 版（显存不够时用）
#   bash a1_apply.sh --film 1           # 只装《三十八万八》
#
# 端口坑：该服务器只开 23，所有 ssh/scp 必须带 -p 23（scp 是大写 -P）。
# ==============================================================================
set -uo pipefail

REMOTE_HOST="root@117.50.188.156"
PORT="23"
SSHP="ssh -p ${PORT} -o StrictHostKeyChecking=no -o ConnectTimeout=15"
SCPP="scp -P ${PORT} -o StrictHostKeyChecking=no"
RYPY="/workspace/venv/bin/python"

# 官方原始工作流（UI 格式示例文件）
OFFICIAL="/workspace/ComfyUI/custom_nodes/comfyui-minimax-h3-audio-T8/examples/workflows/22-sol-engine-h3-super/2026-08-29_H3_Sol_Engine_Super_Acceleration_LTX25_Advanced_EXP.json"
# 远端存放补丁脚本与中转产物的位置
PATCHER_REMOTE="/workspace/patch_stage2_vaedecode.py"
SHARED="/workspace/films/_shared/stage2_vaedecode.json"

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCHER_LOCAL="${DIR}/patch_stage2_vaedecode.py"

C_OK=$'\033[32m'; C_BAD=$'\033[31m'; C_DIM=$'\033[2m'; C_0=$'\033[0m'
ok()   { echo "${C_OK}  ✔ ${C_0}$1"; }
bad()  { echo "${C_BAD}  ✘ ${C_0}$1"; }
dim()  { echo "${C_DIM}    ${C_0}$1"; }
hdr()  { echo; echo "════════════════════════════════════════════════════════════════════════════════"; echo "  $1"; echo "════════════════════════════════════════════════════════════════════════════════"; }

# ---- 解析参数 -----------------------------------------------------------------
DECODE_NODE="VAEDecode"
INSPECT=""
ONLY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --tiled)    DECODE_NODE="VAEDecodeTiled" ;;
    --inspect)  INSPECT="--inspect" ;;
    --film)     shift; ONLY="$1" ;;
    -h|--help)
      sed -n '2,17p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "未知参数：$1（用 --help 看用法）"; exit 2 ;;
  esac
  shift
done

ALL_FILMS=("1:thirty_eight_eight:01_周星驰_三十八万八"
           "2:laozi_buqule:02_姜文_老子不娶了"
           "3:jiaming_zhiye:03_奉俊昊_加名之夜")

# ---- 0. 前置检查 ---------------------------------------------------------------
hdr "A1 应用 · 解码器 TAEHV → ${DECODE_NODE}"

if [ ! -f "$PATCHER_LOCAL" ]; then
  bad "找不到补丁脚本：$PATCHER_LOCAL"
  exit 2
fi
ok "补丁脚本就位：$(basename "$PATCHER_LOCAL")"

echo
dim "检查远端连通性（${REMOTE_HOST}:${PORT}）…"
if ! $SSHP "$REMOTE_HOST" 'echo CONNECTED' 2>/dev/null | grep -q CONNECTED; then
  bad "连不上远端服务器。"
  echo
  dim "服务器可能仍处于关机/释放状态。等它开机后再跑本脚本即可，脚本本身不需要改。"
  dim "如果已经开机但还是连不上，先确认端口：ssh -p 23 ${REMOTE_HOST}"
  exit 4
fi
ok "远端已连通"

# ---- 1. 上传补丁脚本 -----------------------------------------------------------
echo
dim "上传补丁脚本 → ${PATCHER_REMOTE}"
if $SCPP "$PATCHER_LOCAL" "${REMOTE_HOST}:${PATCHER_REMOTE}" >/dev/null 2>&1; then
  ok "已上传"
else
  bad "上传失败，请检查远端 /workspace 是否可写"
  exit 3
fi

# ---- 2. 确认官方工作流存在 ------------------------------------------------------
echo
dim "确认官方工作流存在…"
if ! $SSHP "$REMOTE_HOST" "[ -f '$OFFICIAL' ] && echo FOUND" 2>/dev/null | grep -q FOUND; then
  bad "远端找不到官方工作流："
  dim "  $OFFICIAL"
  dim "请确认插件目录名或版本（ls /workspace/ComfyUI/custom_nodes/ | grep minimax）"
  exit 3
fi
ok "官方工作流就位"

# ---- 3. inspect 模式：只看结构，不写文件 ---------------------------------------
if [ -n "$INSPECT" ]; then
  hdr "inspect · 原始工作流结构"
  $SSHP "$REMOTE_HOST" "$RYPY '$PATCHER_REMOTE' --src '$OFFICIAL' --inspect"
  echo
  dim "以上是原始结构。确认「解码目标」和「VAE 候选」两处正确后，"
  dim "去掉 --inspect 再跑一次即可生成补丁工作流。"
  exit 0
fi

# ---- 4. 生成补丁工作流 ---------------------------------------------------------
hdr "生成补丁工作流（${DECODE_NODE}）"
$SSHP "$REMOTE_HOST" "mkdir -p '$SHARED' 2>/dev/null; mkdir -p /workspace/films/_shared"
RESULT=$($SSHP "$REMOTE_HOST" "$RYPY '$PATCHER_REMOTE' --src '$OFFICIAL' --out '$SHARED' --decode-node '$DECODE_NODE'" 2>&1)
echo "$RESULT" | sed 's/^/    /'

if ! echo "$RESULT" | grep -q "已写出"; then
  bad "生成失败（见上方输出）"
  exit 3
fi
if echo "$RESULT" | grep -q "一致性自检发现问题"; then
  bad "一致性自检未通过，**不要**继续使用这份工作流，请把上面的问题反馈回来"
  exit 3
fi
ok "补丁工作流已生成：${SHARED}"

# ---- 5. 分发到各片工程 ---------------------------------------------------------
hdr "分发到片目录"
for entry in "${ALL_FILMS[@]}"; do
  IDX="${entry%%:*}"; REST="${entry#*:}"; REMOTE_DIR="${REST%%:*}"; LOCAL_NAME="${REST#*:}"
  if [ -n "$ONLY" ] && [ "$ONLY" != "$IDX" ]; then
    dim "跳过 ${LOCAL_NAME}（--film ${ONLY}）"
    continue
  fi
  DEST="/workspace/films/${REMOTE_DIR}/workflows/stage2_vaedecode.json"
  if $SSHP "$REMOTE_HOST" "mkdir -p /workspace/films/${REMOTE_DIR}/workflows && cp '$SHARED' '$DEST' && echo DONE" 2>/dev/null | grep -q DONE; then
    ok "${LOCAL_NAME}  →  ${DEST}"
    # 顺带在本地也放一份，方便离线查看与版本管理
    LOCAL_WF="${DIR}/../${LOCAL_NAME}/workflows"
    mkdir -p "$LOCAL_WF" 2>/dev/null
    $SCPP "${REMOTE_HOST}:${DEST}" "${LOCAL_WF}/stage2_vaedecode.json" >/dev/null 2>&1 \
      && dim "     并已取回本地：${LOCAL_NAME}/workflows/stage2_vaedecode.json"
  else
    bad "${LOCAL_NAME} 分发失败"
  fi
done

# ---- 6. 校验 -------------------------------------------------------------------
hdr "校验"
CHECK=$($SSHP "$REMOTE_HOST" "$RYPY - <<'PYEOF'
import json
p = '$SHARED'
w = json.load(open(p))
if 'nodes' not in w:
    print('FAIL: 不是 UI 格式工作流'); raise SystemExit
n17 = [n for n in w['nodes'] if n.get('type') == '$DECODE_NODE']
loader = [n for n in w['nodes'] if n.get('type') == 'VAELoader']
taehv = [n for n in w['nodes'] if 'TAEHVDecode' in str(n.get('type',''))]
print('OK: %s 节点 %d 个；VAELoader %d 个；残留 TAEHVDecode %d 个'
      % ('$DECODE_NODE', len(n17), len(loader), len(taehv)))
if n17:
    print('  解码节点 id=%s  inputs=%s' % (n17[0]['id'], json.dumps(n17[0]['inputs'], ensure_ascii=False)))
PYEOF" 2>&1)
echo "$CHECK" | sed 's/^/    /'
echo "$CHECK" | grep -q "^OK" && ok "工作流结构正确" || bad "结构校验未通过"

# ---- 7. 下一步 -----------------------------------------------------------------
hdr "完成 · 下一步"
cat <<EOF
  补丁工作流已就位。10_run_film.py 会自动优先使用它，无需其他改动。

  ${C_DIM}① 先跑单镜验证（约 3 分钟，重点看峰值显存）${C_0}
     ssh -p ${PORT} ${REMOTE_HOST} "cd /workspace/films/thirty_eight_eight && \\
       ${RYPY} 10_run_film.py --shots 1 --stage refine"

  ${C_DIM}② 显存不够（逼近 22 GiB 或 OOM）就换分块解码${C_0}
     bash $(basename "${BASH_SOURCE[0]}") --tiled
     # 或手工加参数：--decode-node VAEDecodeTiled --tile-size 512 --overlap 64

  ${C_DIM}③ 做 A/B 对照（同一镜分别用两种解码器各出一版）${C_0}
     ${RYPY} 10_run_film.py --shots 1 --stage refine                # A1 版
     ${RYPY} 10_run_film.py --shots 1 --stage refine --keep-taehv   # 官方版

  ${C_DIM}④ 全片重跑（8 镜，预计 17 分钟）${C_0}
     ${RYPY} 10_run_film.py --shots 1-8 --stage refine

  ${C_DIM}前提提醒${C_0}
     · 先确认 672×384 草稿还在：ls /workspace/films/*/output MiniMaxH3 的草稿目录
     · 草稿在 → 只跑 --stage refine（快）；草稿没了 → 跑 --stage both（慢一倍）
EOF
