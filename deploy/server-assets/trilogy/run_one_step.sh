#!/bin/bash
# 《现代婚姻三部曲》一步直出流水线（服务器端执行）
#
# 与两阶段的区别：不走 stage2 精修。
# 两阶段画质糊的根因 = stage2 从 384×672 草稿上采样补细节（identity 预设
# 只从 sigma 0.5 起步，保留一半草稿 latent）。一步直出 768×1344 是原生分辨率
# 全噪声去噪，画质更硬，代价是时间约 3.2×。
#
# ★ 注意：一步直出**不经过 LTX trim**，成片时长 = H3 帧数 / 24，
#   与 manifest 里 LTX trim 后的 duration 不同！字幕时间轴必须按 H3 帧数重算。
set -u
BASE=/workspace/trilogy
CO=/workspace/ComfyUI
OUT=$CO/output/MiniMaxH3/trilogy_one
PY=/workspace/venv/bin/python
SUB=/root/s2/submit_api.py
API=http://127.0.0.1:8188

mkdir -p $BASE/gates_one $OUT
cd $BASE
KEYS=$(cat keys.txt)
echo "[$(date +%H:%M:%S)] 一步直出 待跑: $(echo $KEYS | tr '\n' ' ')"
echo "[$(date +%H:%M:%S)] 分辨率 768×1344 · 单阶段（无 stage2 精修）"

OK=0; FAIL=0
for k in $KEYS; do
  if [ -f gates_one/$k.done ]; then echo "  [skip] $k 已完成"; OK=$((OK+1)); continue; fi
  echo "  [→] $k 提交中... ($(date +%H:%M:%S))"
  T0=$(date +%s)
  if $PY $SUB wf_one/wf_$k.json --timeout 2400; then
    touch gates_one/$k.done
    T1=$(date +%s)
    echo "  [✓] $k OK  用时 $((T1-T0)) s  (累计完成 $((OK+1)))"
    OK=$((OK+1))
  else
    echo "  [✗] $k FAILED"
    echo "$k" >> failed_one.txt
    FAIL=$((FAIL+1))
  fi
done

echo "=========== 收尾 ==========="
echo "[$(date +%H:%M:%S)] 完成 $OK 镜，失败 $FAIL 镜"
nvidia-smi --query-gpu=memory.used --format=csv,noheader
ls -la $OUT/ | head -30
