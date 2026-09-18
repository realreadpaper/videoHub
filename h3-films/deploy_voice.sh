#!/usr/bin/env bash
# 把「中文干声 + 每镜 audio-lock 工作流 + 锁音轨 runner」一次性投送到远端 4090。
#
#   export SSHPASS='远端密码'
#   bash deploy_voice.sh                 # 两片全量（各 20 镜）
#   bash deploy_voice.sh film1           # 只投片1
#
# 前置：make_tts.py 已跑完（_tts/<film>/shotNN_dry.wav 齐）
set -euo pipefail
cd "$(dirname "$0")"

HOST="${1:-root@117.50.188.156}"; PORT="${2:-23}"
WANT="${3:-all}"
: "${SSHPASS:?请先 export SSHPASS=远端密码}"

PY=/Users/hejianglong/.workbuddy/binaries/python/envs/default/bin/python
SSH="sshpass -e ssh -p $PORT -o StrictHostKeyChecking=no -o ConnectTimeout=15 $HOST"
SCP="sshpass -e scp -P $PORT -o StrictHostKeyChecking=no"

FILMS=(film1 film2)
[ "$WANT" != "all" ] && FILMS=("$WANT")

echo "== 1/5 生成本地 audio-lock 工作流（每镜一份）=="
for f in "${FILMS[@]}"; do
  for n in $(seq 1 20); do
    "$PY" build_voice_workflow.py --shot "$n" --film "$f" >/dev/null
  done
  echo "   $f: 20 份 -> _remote/stage1_voice_${f}_sNN.json"
done

echo "== 2/5 校验干声齐备 =="
for f in "${FILMS[@]}"; do
  miss=""
  for n in $(seq 1 20); do
    w=$(printf "_tts/%s/shot%02d_dry.wav" "$f" "$n")
    [ -s "$w" ] || miss="$miss $n"
  done
  if [ -n "$miss" ]; then echo "   ✘ $f 缺镜:$miss"; exit 1; fi
  echo "   ✔ $f 20 份干声齐"
done

echo "== 3/5 远端建目录 + 清旧货（只清本次要投的片）=="
# 干声：整目录清空再投（避免残留上一版 v2 干声被误用）
# 产物：清空 output/final/logs —— prompt 与干声都变了，旧草稿/成片一律作废
CLEAN_DRY=""; CLEAN_OUT=""
for f in "${FILMS[@]}"; do
  CLEAN_DRY="$CLEAN_DRY /workspace/ComfyUI/input/tts_dry/$f/*.wav"
  slug=douyin-office; [ "$f" = film2 ] && slug=douyin-blinddate
  CLEAN_OUT="$CLEAN_OUT
      rm -rf /workspace/ComfyUI/output/MiniMaxH3/$slug/*
      rm -f /workspace/films/$slug/final/*.mp4 /workspace/films/$slug/logs/*.log
      mkdir -p /workspace/films/$slug/workflows /workspace/films/$slug/final /workspace/films/$slug/logs"
done
$SSH "mkdir -p /workspace/ComfyUI/input/tts_dry/film1 /workspace/ComfyUI/input/tts_dry/film2
      rm -f $CLEAN_DRY /workspace/ComfyUI/input/tts_dry/shot*_dry.wav
      $CLEAN_OUT
      echo '   旧干声/旧产物已清空（仅本次上片的）'"
# 注意：**不要**清 /workspace/ComfyUI/input/draft_voice_s*.mp4
# —— stage2 精修每镜都会 shutil.copyfile 覆盖同名文件，留着无害；
#    但若在另一片精修进行中删掉它，会踩到「刚拷入就被删」的竞态导致该镜失败。

echo "== 4/5 投送干声 + 工作流 + runner =="
for f in "${FILMS[@]}"; do
  slug=douyin-office; [ "$f" = film2 ] && slug=douyin-blinddate
  $SCP _tts/$f/shot*_dry.wav "$HOST:/workspace/ComfyUI/input/tts_dry/$f/" >/dev/null
  $SCP _remote/stage1_voice_${f}_s*.json "$HOST:/workspace/films/$slug/workflows/" >/dev/null
  echo "   $f -> $slug: 干声 20 + 工作流 20"
done
$SCP 11_run_voice_film.py "$HOST:/tmp/11_run_voice_film.py" >/dev/null
$SSH 'cp /tmp/11_run_voice_film.py /workspace/films/douyin-office/11_run_voice_film.py
      cp /tmp/11_run_voice_film.py /workspace/films/douyin-blinddate/11_run_voice_film.py
      chmod +x /workspace/films/douyin-office/11_run_voice_film.py /workspace/films/douyin-blinddate/11_run_voice_film.py'
echo "   11_run_voice_film.py"

echo "== 5/5 远端确认 =="
$SSH '
for p in douyin-office/film1 douyin-blinddate/film2; do
  s=${p%%/*}; f=${p##*/}
  echo "--- $s ---"
  echo "   干声: $(ls /workspace/ComfyUI/input/tts_dry/$f/*.wav 2>/dev/null | wc -l) 份"
  echo "   工作流: $(ls /workspace/films/$s/workflows/stage1_voice_${f}_s*.json 2>/dev/null | wc -l) 份"
done'

echo
echo "投送完成。远端单镜全链路验证（锁音轨草稿 + LTX 精修）："
echo "  ssh -p $PORT $HOST"
echo "  cd /workspace/films/douyin-office && /workspace/venv/bin/python 11_run_voice_film.py --film film1 --shots 5"
