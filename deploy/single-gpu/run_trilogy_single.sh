#!/bin/bash
# ============================================================
# run_trilogy_single.sh — 《现代婚姻三部曲》24 镜 · 单卡一步直出
# 放到目标机 /workspace/trilogy/ 下执行（与 wf_one/ keys.txt 同目录）
#
# 与双卡版 run_one_step_dual.sh 的差别：
#   · 单 worker，不切分 keys（不再需要 keys_a/keys_b）
#   · 只对 8188 做队列校验和 /free
#   · gates_one 仍复用 —— 双卡时代跑过的镜会自动 skip，不重复烧机时
#
# 用法（服务器）：
#   cd /workspace/trilogy
#   setsid nohup bash run_trilogy_single.sh > run_single.log 2>&1 < /dev/null &
#   tail -f run_single.log
#
# 可选： bash run_trilogy_single.sh keys.txt      # 换 key 列表文件
# ★ 必须 setsid + nohup + </dev/null 三件套，否则 ssh 会话一断任务就被带走
# ============================================================
set -u

# ★ 防 http_proxy 劫持 localhost 检查：curl 访问 127.0.0.1 若走代理会拿到 502，
#   于是误报「8188 没响应」而 ComfyUI 其实跑得好好的。
export no_proxy="127.0.0.1,localhost,::1"
export NO_PROXY="127.0.0.1,localhost,::1"

BASE=/workspace/trilogy
CO=/workspace/ComfyUI
OUT=$CO/output/MiniMaxH3/trilogy_one
PY=/workspace/venv/bin/python
SUB=/root/s2/submit_api.py
PORT=8188
API=http://127.0.0.1:$PORT
KEYFILE=${1:-keys.txt}

mkdir -p "$BASE/gates_one" "$OUT"
cd "$BASE" || exit 1

echo "[$(date +%H:%M:%S)] === 单卡一步直出 · 768x1344 · 不含 stage2 精修 ==="
echo "[$(date +%H:%M:%S)] 端口 $PORT   key 文件 $KEYFILE"
echo "[$(date +%H:%M:%S)] 计时参考：热态 ~558 s/镜，首镜冷启 ~820 s。24 镜单卡挂钟约 3h45m。"

# ---------- 0) 端口必须在跑 ----------
if [ "$(curl -s -m 5 -o /dev/null -w '%{http_code}' "$API/system_stats")" != "200" ]; then
  echo "[abort] $API 没响应。先在目标机跑：bash deploy/bootstrap/04_launch_comfy.sh single"
  exit 2
fi

# ---------- 1) 队列必须为空（别叠别人的任务） ----------
BUSY=$(curl -s -m 8 "$API/queue" | $PY -c 'import json,sys;d=json.load(sys.stdin);print(len(d["queue_running"])+len(d["queue_pending"]))' 2>/dev/null || echo 99)
if [ "${BUSY:-99}" != "0" ]; then
  echo "[abort] 队列非空（$BUSY 个任务），拒绝点火。先看 /queue，必要时 POST /queue {\"clear\":true}"
  exit 2
fi

# ---------- 2) 清残留权重（权重常驻 != 在忙，但要给本批次腾干净显存） ----------
echo "[$(date +%H:%M:%S)] 清残留权重（/free）..."
curl -s -m 60 -X POST "$API/free" -H 'Content-Type: application/json' \
     -d '{"unload_models":true,"free_memory":true}' >/dev/null 2>&1
# ★ 注意：/free 返回 200 但响应体是 0 字节，不要对它 json.loads
sleep 15

# ---------- 3) 逐镜提交 ----------
KEYS=$(cat "$KEYFILE")
TOTAL=$(echo "$KEYS" | grep -c . )
echo "[$(date +%H:%M:%S)] 待跑 $(echo "$KEYS" | tr '\n' ' ')"
echo "[$(date +%H:%M:%S)] 合计 $TOTAL 镜（已完成的会 skip）"

OK=0; FAIL=0; DONE0=0
BATCH_T0=$(date +%s)
for k in $KEYS; do
  [ -z "$k" ] && continue
  if [ -f "gates_one/${k}.done" ]; then
    echo "  [skip] $k 已完成"
    DONE0=$((DONE0+1)); OK=$((OK+1)); continue
  fi
  echo "  [->] $k 提交中... ($(date +%H:%M:%S))"
  T0=$(date +%s)
  if $PY $SUB "wf_one/wf_${k}.json" --host "$API" --timeout 2400; then
    touch "gates_one/${k}.done"
    echo "  [OK] $k  $(( $(date +%s)-T0 ))s  (累计完成 $((OK+1))/$TOTAL)"
    OK=$((OK+1))
  else
    echo "  [XX] $k FAILED  $(( $(date +%s)-T0 ))s"
    echo "$k" >> failed_one.txt
    FAIL=$((FAIL+1))
  fi
done

# ---------- 4) 收尾 ----------
echo "=========== 收尾 ==========="
echo "[$(date +%H:%M:%S)] 完成 $OK 镜（其中 $DONE0 镜是此前已跑的），失败 $FAIL 镜"
echo "[$(date +%H:%M:%S)] 本批挂钟 $(($(date +%s)-BATCH_T0)) s"
[ -f failed_one.txt ] && { echo "失败清单："; cat failed_one.txt; }
curl -s -m 5 "$API/queue"; echo
nvidia-smi --query-gpu=index,memory.used --format=csv,noheader
echo "成片目录： $OUT"
ls -la "$OUT/" | head -30
