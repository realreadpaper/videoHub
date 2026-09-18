#!/bin/bash
# 《现代婚姻三部曲》两段流水线（服务器端执行）
# ★ 硬约束：stage1 全部跑完 → 强制释放显存 → 才加载 stage2 权重。绝不逐镜交替。
set -u
BASE=/workspace/trilogy
CO=/workspace/ComfyUI
OUT=$CO/output/MiniMaxH3/trilogy
REF=$CO/output/MiniMaxH3/trilogy_refined
IN=$CO/input/trilogy_drafts
PY=/workspace/venv/bin/python
SUB=/root/s2/submit_api.py
S2A=/workspace/films/s2_adapt.py
U2A=/root/ui_to_api.py
OFFICIAL=$CO/custom_nodes/comfyui-minimax-h3-audio-T8/examples/workflows/22-sol-engine-h3-super/2026-08-30_H3_Sol_Engine_LTX25_Identity_Preserve_3Step_Advanced_EXP.json
API=http://127.0.0.1:8188

mkdir -p $BASE/gates $REF $IN $CO/output/MiniMaxH3/trilogy
cd $BASE
KEYS=$(cat keys.txt)
echo "[$(date +%H:%M:%S)] 待跑: $KEYS"

# ───────── 阶段 A：全部 stage1 草稿（H3 权重） ─────────
echo "=========== 阶段 A · Stage1 草稿 ==========="
for k in $KEYS; do
  if [ -f gates/$k.s1.done ]; then echo "  [skip] $k stage1 已完成"; continue; fi
  echo "  [A] $k 提交中..."
  if $PY $SUB wf/wf_$k.json --timeout 2400; then
    touch gates/$k.s1.done; echo "  [A] $k OK"
  else
    echo "  [A] $k FAILED"; echo "$k" >> failed_s1.txt
  fi
done

# ───────── 段边界：强制释放（硬步骤，不是可选优化） ─────────
echo "=========== 段边界 · 强制释放显存 ==========="
curl -s -m 60 -X POST $API/free -H "Content-Type: application/json" \
     -d '{"unload_models":true,"free_memory":true}' >/dev/null 2>&1
sleep 25
nvidia-smi --query-gpu=memory.used --format=csv,noheader

# ───────── 阶段 B：全部 stage2 精修（LTX 权重） ─────────
echo "=========== 阶段 B · Stage2 精修（identity 保脸） ==========="
# ★★ 顺序是硬性的，颠倒会静默毁结果（2026-09-18 血泪）：
#   官方 .json 是 **UI 格式**（含 nodes 数组），而 s2_adapt 的 adapt_template 与
#   parametrize 全部按 **API 格式**（顶层 key=节点 id）操作。
#   若直接把 UI 模板喂给 s2_adapt：所有 d["8"]/d["9"] 取值为空 → A/B/C 三处改造
#   一条都不执行，还谎报"模板已是适配态"；随后 parametrize 找 d["3"] 直接 KeyError。
#   正确链路： 官方UI --ui_to_api--> raw.api --s2_adapt(A/B/C+preset)--> tpl.api
#              --s2_adapt(parametrize)--> 每镜.api
echo "  [B0] 官方 UI → API ..."
$PY $U2A "$OFFICIAL" --out s2_raw.api.json || { echo "  ✗ ui_to_api 失败"; exit 1; }
echo "  [B0] 适配三处（融合UNET / 删LoRA / VAEDecode）+ identity ..."
$PY $S2A --template s2_raw.api.json --out s2_tpl.api.json --preset identity \
  || { echo "  ✗ 模板适配失败"; exit 1; }
$PY - <<'CHK'
import json
d=json.load(open("s2_tpl.api.json"))
u=d["8"]["inputs"].get("unet_name","")
assert "distilled" in u, "A 失败: UNET 未换融合版 -> %s" % u
assert "9" not in d, "B 失败: LoRA 未删"
assert d.get("17",{}).get("class_type")=="VAEDecode", "C 失败: 解码器未换 VAEDecode"
print("  [B0] ✓ 三处改造校验通过 | %s" % u)
CHK
[ $? -ne 0 ] && { echo "  ✗ 模板校验未过，终止阶段B"; exit 1; }

for k in $KEYS; do
  if [ -f gates/$k.s2.done ]; then echo "  [skip] $k stage2 已完成"; continue; fi
  # ★ stage1 filename_prefix 形如 MiniMaxH3/trilogy/f1_s02（带下划线），
  #   而 k 形如 f1s02（不带）。必须做 f1s02 -> f1_s02 的映射，否则匹配为空。
  PREFIX_K="${k:0:2}_${k:2}"
  DRAFT=$(ls $OUT/${PREFIX_K}_*.mp4 2>/dev/null | head -1)
  if [ -z "$DRAFT" ]; then
    # 兜底：万一输出是 f1s02_ 形式
    DRAFT=$(ls $OUT/${k}_*.mp4 2>/dev/null | head -1)
  fi
  if [ -z "$DRAFT" ]; then echo "  [B] $k 缺草稿，跳过"; echo "$k" >> failed_s2.txt; continue; fi
  cp "$DRAFT" $IN/$k.mp4
  # seed 与 stage1 对齐（从 wf json 提取，保证同镜两阶段同源）
  SEED=$(awk -v k="$k" '$1==k{print $2}' seeds.txt 2>/dev/null)
  [ -z "${SEED:-}" ] && { echo "  [B] $k 无 seed，回退 42"; SEED=42; }
  echo "  [B] $k 精修中... (draft=$(basename $DRAFT) seed=$SEED)"
  $PY $S2A --template s2_tpl.api.json --shot ${k#*s} \
      --draft trilogy_drafts/$k.mp4 \
      --prompt-file prompts/$k.txt \
      --seed "$SEED" \
      --preset identity --width 768 --height 1344 \
      --prefix MiniMaxH3/trilogy_refined/$k \
      --out s2_$k.api.json &&
  $PY $SUB s2_$k.api.json --timeout 2400 &&
  touch gates/$k.s2.done && echo "  [B] $k OK" || { echo "  [B] $k FAILED"; echo "$k" >> failed_s2.txt; }
done

echo "=========== 收尾 ==========="
nvidia-smi --query-gpu=memory.used --format=csv,noheader
ls -la $REF/ | head -30
echo "[$(date +%H:%M:%S)] 阶段 B 结束"
