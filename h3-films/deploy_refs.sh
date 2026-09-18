#!/usr/bin/env bash
# 把「产品参考图 + 关键帧锚定图 + 图条件工作流」投送到远端 4090，并复验槽位。
#
#   export SSHPASS='远端密码'
#   bash deploy_refs.sh                 # 默认投 refs + frames + 3 份工作流
#   bash deploy_refs.sh --dry-run       # 只看要传什么，不连远端
#   bash deploy_refs.sh --shot 15       # 只投某一镜
#
# 为什么必须先跑 probe：ref_images 这个槽在模板 JSON 里**原本不存在**（未连接的
# optional 槽不落盘），生成器是按 SLOT_FALLBACK 的顺序 append 到索引 8 的。
# 一旦 T8 节点版本升级改了顺序，接线就会静默错位 —— 生成出来的是别的参数。
# 所以投送后第一步永远是 probe，核对 h3_slots.json 里的索引与期望一致。
set -euo pipefail
cd "$(dirname "$0")"

HOST="${HOST:-root@117.50.188.156}"; PORT="${PORT:-23}"
SLUG="douyin-office"
DRY=0; ONLY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --shot) shift; ONLY="$1" ;;
    *) echo "未知参数 $1"; exit 2 ;;
  esac
  shift
done

PY=/Users/hejianglong/.workbuddy/binaries/python/envs/default/bin/python

echo "== 1/5 重新生成图条件工作流（幂等，口径以 p1_data 为准）=="
if [ -n "$ONLY" ]; then SHOTS="$ONLY"; else SHOTS="13 15 18"; fi
for n in $SHOTS; do
  case "$n" in
    13|15)
      "$PY" build_voice_workflow.py --shot "$n" --ref-images refs/prod_P2_white.png \
        --out "_remote/i2v/stage1_ref2va_film1_s$(printf %02d "$n").json" >/dev/null
      echo "   镜$n → Ref2VA 参考图 (refs/prod_P2_white.png)"
      ;;
    18)
      "$PY" build_voice_workflow.py --shot "$n" --first-frame frames/film1_shot18_first.png \
        --out "_remote/i2v/stage1_i2v_film1_s18.json" >/dev/null
      echo "   镜$n → FL2VA 首帧锚定 (frames/film1_shot18_first.png)"
      ;;
    *) echo "   ⚠ 镜$n 还没定义图条件路由，跳过" ;;
  esac
done

echo "== 2/5 校验本地资产 =="
for f in _refs/prod_P2_white.png _frames/film1_shot18_first.png; do
  [ -s "$f" ] || { echo "   ✘ 缺 $f —— 先跑 make_product_refs.py / make_first_frame.py"; exit 1; }
  echo "   ✔ $f"
done
ls _remote/i2v/*.json >/dev/null 2>&1 || { echo "   ✘ _remote/i2v 下没有工作流"; exit 1; }
echo "   ✔ 工作流 $(ls _remote/i2v/*.json | wc -l | tr -d ' ') 份"

if [ "$DRY" = "1" ]; then
  echo
  echo "[dry-run] 将要上传："
  echo "  _refs/*.png            → /workspace/ComfyUI/input/refs/"
  echo "  _frames/*.png          → /workspace/ComfyUI/input/frames/"
  echo "  _remote/i2v/*.json     → /workspace/films/$SLUG/workflows/"
  echo "  probe_h3_nodes.py      → 远端执行，产出 h3_slots.json"
  exit 0
fi

: "${SSHPASS:?请先 export SSHPASS=远端密码}"
SSH="sshpass -e ssh -p $PORT -o StrictHostKeyChecking=no -o ConnectTimeout=15 $HOST"
SCP="sshpass -e scp -P $PORT -o StrictHostKeyChecking=no"

echo "== 3/5 远端建目录 =="
$SSH "mkdir -p /workspace/ComfyUI/input/refs /workspace/ComfyUI/input/frames /workspace/films/$SLUG/workflows
      echo '   ok'"

echo "== 4/5 投送资产 + 工作流 =="
$SCP _refs/*.png "$HOST:/workspace/ComfyUI/input/refs/" >/dev/null
echo "   refs: $(ls _refs/*.png | wc -l | tr -d ' ') 张"
$SCP _frames/film1_shot18_first.png "$HOST:/workspace/ComfyUI/input/frames/" >/dev/null
echo "   frames: film1_shot18_first.png"
$SCP _remote/i2v/*.json "$HOST:/workspace/films/$SLUG/workflows/" >/dev/null
echo "   workflows: $(ls _remote/i2v/*.json | wc -l | tr -d ' ') 份"
$SCP probe_h3_nodes.py "$HOST:/tmp/probe_h3_nodes.py" >/dev/null
$SCP build_voice_workflow.py "$HOST:/tmp/build_voice_workflow.py" >/dev/null

echo "== 5/5 槽位复验（关键：ref_images 是否真在索引 8）=="
$SSH "/workspace/venv/bin/python /tmp/probe_h3_nodes.py --dump-slots /workspace/films/$SLUG/h3_slots.json 2>&1 | tail -22"

cat <<EOF

投送完成。接下来两件事（都在远端）：

  ssh -p $PORT $HOST

  # ① 单镜通路验证（挑最省的：122 帧小画布先探路）
  cd /workspace/films/$SLUG
  /workspace/venv/bin/python 11_run_voice_film.py --film film1 --shots 15

  # ② 把 h3_slots.json 拉回本地，让生成器改用实测索引
  #    本地执行：scp -P $PORT $HOST:/workspace/films/$SLUG/h3_slots.json .
EOF
