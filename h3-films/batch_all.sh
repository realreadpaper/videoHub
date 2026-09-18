#!/usr/bin/env bash
# 两片全量生产（远端 4090 串行使用，避免队列争抢）
#
#   export SSHPASS='远端密码'
#   bash batch_all.sh                 # 两片全跑：film1 draft→refine→concat，再 film2
#   bash batch_all.sh film1           # 只跑片1
#
# 前置：deploy_voice.sh 已投送（40 份工作流 + 两片干声已在远端 input/tts_dry/）
set -euo pipefail
cd "$(dirname "$0")"

HOST="${1:-root@117.50.188.156}"; PORT="${2:-23}"
ONLY="${3:-all}"
: "${SSHPASS:?请先 export SSHPASS=远端密码}"

case "$ONLY" in
  all)   FILMS="film1 film2" ;;
  film1) FILMS="film1" ;;
  film2) FILMS="film2" ;;
  *) echo "用法: bash batch_all.sh [host] [port] [all|film1|film2]"; exit 1 ;;
esac

SSH="sshpass -e ssh -p $PORT -o StrictHostKeyChecking=no -o ServerAliveInterval=30 $HOST"

echo "== 启动远端批量：$FILMS =="
$SSH "
set -e
for f in $FILMS; do
  case \$f in film1) slug=douyin-office ;; film2) slug=douyin-blinddate ;; esac
  cd /workspace/films/\$slug
  echo ''
  echo '############################################################'
  echo \"#  \$f · \$slug  草稿 20 镜（锁音轨）\"
  echo '############################################################'
  /workspace/venv/bin/python 11_run_voice_film.py --film \$f --shots 1-20 --stage draft
  echo ''
  echo '############################################################'
  echo \"#  \$f · \$slug  LTX 精修 20 镜\"
  echo '############################################################'
  /workspace/venv/bin/python 11_run_voice_film.py --film \$f --shots 1-20 --stage refine
  echo ''
  echo '############################################################'
  echo \"#  \$f · \$slug  合成全片\"
  echo '############################################################'
  /workspace/venv/bin/python 11_run_voice_film.py --film \$f --concat
  echo \"[\$f] 完成，产物在 /workspace/films/\$slug/final/\"
done
"
echo
echo "全部结束。取片："
echo "  scp -P $PORT $HOST:/workspace/films/douyin-office/*_全片.mp4 ."
echo "  scp -P $PORT $HOST:/workspace/films/douyin-blinddate/*_全片.mp4 ."
