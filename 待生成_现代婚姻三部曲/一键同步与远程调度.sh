#!/bin/bash
# ==============================================================================
# 现代婚姻三部曲：本地同步与远程自动化调度控制台
#
# 端口坑：本机 ssh/scp/rsync 默认走 22，该服务器只开 23。
# 所有远程调用必须带 -p 23（或 -e "ssh -p 23"）。已配置免密，不会再卡密码。
# ==============================================================================

REMOTE_HOST="root@117.50.188.156"
PORT="23"
SSH="ssh -p ${PORT} -o StrictHostKeyChecking=no -o ConnectTimeout=15"
RSYNC="rsync -avzP -e ssh -p ${PORT} -o StrictHostKeyChecking=no"
PY="/workspace/venv/bin/python"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 本地目录 -> 远端目录
P1=("01_周星驰_三十八万八" "thirty_eight_eight")
P2=("02_姜文_老子不娶了"   "laozi_buqule")
P3=("03_奉俊昊_加名之夜"   "jiaming_zhiye")

sync_projects() {
  echo "=== 同步三部工程 -> /workspace/films/ (端口 $PORT) ==="
  $SSH $REMOTE_HOST "mkdir -p /workspace/films/thirty_eight_eight /workspace/films/laozi_buqule /workspace/films/jiaming_zhiye" || { echo "远程目录创建失败"; return 1; }

  # 注意：远端未装 rsync，用 scp（走 sftp 子系统，openssh 自带）
  for pair in "P1" "P2" "P3"; do
    eval "local=(\"\${${pair}[@]}\")"
    L="$DIR/${local[0]}"; R="${local[1]}"
    echo "--> ${local[0]}  ->  /workspace/films/$R/"
    scp -r -P "$PORT" -o StrictHostKeyChecking=no -q "$L/." "$REMOTE_HOST:/workspace/films/$R/" || echo "  !! 同步失败: ${local[0]}"
  done
  echo "✔ 同步完成"
}

# $1=远端目录名  $2=显示名  $3=传给驱动的参数
_run() {
  echo "=== 启动【$2】生产 ==="
  # nohup 后台跑，避免 ssh 断连导致任务中断；日志落到 logs/run_all.log
  $SSH $REMOTE_HOST "cd /workspace/films/$1 && mkdir -p logs && nohup $PY 10_run_film.py $3 > logs/run_all.log 2>&1 &
    sleep 3; echo '--- 已提交 ---'; tail -5 logs/run_all.log"
}

run_film_1() { _run "thirty_eight_eight" "周星驰《三十八万八》" "$*"; }
run_film_2() { _run "laozi_buqule"      "姜文《老子不娶了》"   "$*"; }
run_film_3() { _run "jiaming_zhiye"     "奉俊昊《加名之夜》"   "$*"; }

status() {
  $SSH $REMOTE_HOST 'for d in thirty_eight_eight laozi_buqule jiaming_zhiye; do
    echo "--- $d ---"
    ls /workspace/films/$d/final/ 2>/dev/null | wc -l | xargs echo "  成片数:"
    pgrep -f "10_run_film.py" >/dev/null && echo "  运行中: 是" || echo "  运行中: 否"
  done
  nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader
  echo "(GPU 上数据)"
'
}

case "$1" in
  --sync)   sync_projects ;;
  --run-1)  sync_projects; shift; run_film_1 "$@" ;;
  --run-2)  sync_projects; shift; run_film_2 "$@" ;;
  --run-3)  sync_projects; shift; run_film_3 "$@" ;;
  --run-all) sync_projects; run_film_1; run_film_2; run_film_3 ;;
  --status) status ;;
  *)
    cat <<EOF
==========================================================
  现代婚姻三部曲 · 调度控制台  (port $PORT)
==========================================================
  $0 --sync          仅同步三部工程到远程
  $0 --run-1 [args]  同步并启动《三十八万八》
  $0 --run-2 [args]  同步并启动《老子不娶了》
  $0 --run-3 [args]  同步并启动《加名之夜》
  $0 --run-all       同步并按序生产三部
  $0 --status        查看远端进度与 GPU

  args 例：--shots 1-8 --stage both --concat
  推荐先跑单镜验证：--shots 1 --stage both
==========================================================
EOF
    ;;
esac
