#!/bin/bash
# 服务器重启后一键续跑（本地执行）
# 用法： bash _pipeline/resume.sh
#
# 特性：
#   · 自动拉起 ComfyUI（若 8188 未响应）
#   · gates 断点续跑：已完成的 s1.done / s2.done 会自动跳过
#   · 不再等待 v3（重启后 v3 进程已消失，不会再来抢卡）
set -u
SRV=kehu
RMT=/workspace/trilogy
CO=/workspace/ComfyUI
API=http://127.0.0.1:8188
# ★ 远程 curl 也要绕开代理：若服务器上设了 http_proxy，curl 127.0.0.1 会拿到 502，
#   脚本就会误判「ComfyUI 未响应」并反复拉起实例。前置赋值形式，无需 export。
NP="no_proxy=127.0.0.1,localhost NO_PROXY=127.0.0.1,localhost"

echo "▶ 探测服务器..."
ssh -o ConnectTimeout=25 -o BatchMode=yes $SRV 'echo ok' 2>/dev/null || { echo "✗ SSH 不通，服务器未恢复"; exit 1; }
echo "  ✓ SSH 通"

echo "▶ 检查 ComfyUI..."
ALIVE=$(ssh -o ConnectTimeout=20 $SRV "$NP curl -s -m 6 -o /dev/null -w '%{http_code}' $API/system_stats 2>/dev/null" 2>/dev/null)
if [ "${ALIVE:-000}" != "200" ]; then
  echo "  ! ComfyUI 未响应(HTTP ${ALIVE:-000})，尝试拉起..."
  ssh $SRV "cd $CO && setsid nohup /workspace/venv/bin/python main.py --listen 0.0.0.0 --port 8188 --disable-auto-launch > /tmp/comfy_reboot.log 2>&1 < /dev/null &"
  echo "  等待 90s 启动..."
  for i in $(seq 1 18); do
    sleep 10
    A=$(ssh -o ConnectTimeout=15 $SRV "$NP curl -s -m 5 -o /dev/null -w '%{http_code}' $API/system_stats 2>/dev/null" 2>/dev/null)
    if [ "${A:-000}" = "200" ]; then echo "  ✓ ComfyUI 已就绪（等待 $((i*10))s）"; break; fi
    if [ $i = 18 ]; then echo "  ✗ ComfyUI 拉起失败，看 /tmp/comfy_reboot.log"; exit 1; fi
  done
else
  echo "  ✓ ComfyUI 正常"
fi

echo "▶ 检查显存 / v3 残留..."
ssh $SRV "nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader; pgrep -af 'submit_api.py /root/v3run' | head -2 || echo '  v3 无残留'"

echo "▶ 确认 gates（断点续跑）..."
ssh $SRV "cd $RMT && echo \"  s1 已完成: \$(ls gates/*.s1.done 2>/dev/null | wc -l)\"; echo \"  s2 已完成: \$(ls gates/*.s2.done 2>/dev/null | wc -l)\"; echo \"  待跑: \$(tr '\n' ' ' < keys.txt)\""

echo "▶ 强制清显存后启动流水线..."
ssh $SRV "$NP curl -s -m 60 -X POST $API/free -H 'Content-Type: application/json' -d '{\"unload_models\":true,\"free_memory\":true}' >/dev/null 2>&1; sleep 15; cd $RMT && setsid nohup bash run_server.sh > run.log 2>&1 < /dev/null &"
sleep 5
echo "▶ 已启动。看进度： ssh $SRV 'tail -30 $RMT/run.log'"
