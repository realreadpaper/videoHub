#!/usr/bin/env bash
# ============================================================
# verify.sh — 端到端验收（在目标机执行）
# 目的：在正式跑批之前，用**最短路径**证明这条链路是通的。
#   1) 双实例存活 + 队列空
#   2) 权重路径与工作流里写死的文件名一一对上
#   3) ffmpeg 可用（T8 存 H.264 依赖它）
#   4) 真跑一镜（可选，--run 才跑；默认只做静态检查）
#
# 用法： bash verify.sh            # 静态检查（秒级）
#        bash verify.sh --run     # 静态检查 + 真出一镜（约 10 分钟）
# ============================================================
set -u

# ★ 防 http_proxy 劫持 localhost 检查（2026-09-19 实测踩到）：
#   WorkBuddy / Clash 等会设 http_proxy，curl 请求 127.0.0.1:8188 会走代理 →
#   拿到 502/000，于是报「实例无响应」而 ComfyUI 其实跑得好好的。
export no_proxy="127.0.0.1,localhost,::1"
export NO_PROXY="127.0.0.1,localhost,::1"

C=/workspace/ComfyUI
V=/workspace/venv
PY=$V/bin/python
SUB=/root/s2/submit_api.py
PASS=0; FAIL=0
ok(){ printf '  [ OK ] %s\n' "$*"; PASS=$((PASS+1)); }
no(){ printf '  [FAIL] %s\n' "$*"; FAIL=$((FAIL+1)); }
wn(){ printf '  [WARN] %s\n' "$*"; }

# ★ 实例端口按卡数自适应：单卡机器上 8189 不存在是**正常的**，不该报 FAIL
GPU_N=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | wc -l | tr -d ' ')
if [ "${GPU_N:-0}" -ge 2 ]; then
  PORTS="8188 8189"; LAUNCH="both"
else
  PORTS="8188";      LAUNCH="single"
fi

echo "=========== 1. 实例存活 ==========="
echo "  检测到 ${GPU_N:-?} 张卡 → 期望形态：${LAUNCH}（端口 $PORTS）"
for p in $PORTS; do
  code=$(curl -s -m 6 -o /dev/null -w '%{http_code}' http://127.0.0.1:$p/system_stats 2>/dev/null)
  if [ "$code" = "200" ]; then ok ":$p HTTP 200"; else no ":$p 无响应（HTTP ${code:-000}）→ bash 04_launch_comfy.sh $LAUNCH"; fi
  q=$(curl -s -m 6 http://127.0.0.1:$p/queue 2>/dev/null)
  n=$(echo "$q" | "$PY" -c 'import json,sys;d=json.load(sys.stdin);print(len(d["queue_running"])+len(d["queue_pending"]))' 2>/dev/null || echo "?")
  [ "$n" = "0" ] && ok ":$p 队列空" || wn ":$p 队列非空（$n）—— 点火前必须清空，别叠任务"
done

echo
echo "=========== 2. 权重与工作流的名字必须对得上 ==========="
M=$C/models
declare -A NEED=(
  ["$M/diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors"]="fl2va 主干（无参考音/静音轮）"
  ["$M/diffusion_models/Minimax-h3_Singularity_ref2va_Pruned_v1.3_int8.safetensors"]="ref2va 主干（原声锁/参考图轮）"
  ["$M/text_encoders/minimax_h3/qwen3vl_32b_minimax_h3_int8_convrot.safetensors"]="Text Encoder（★必须在 minimax_h3/ 子目录）"
  ["$M/vae/minimax_h3_video_vae_fp16.safetensors"]="Video VAE"
  ["$M/vae/minimax_h3_audio_vae_fp32.safetensors"]="Audio VAE"
  ["$M/loras/minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors"]="Turbo LoRA 4 步"
)
for f in "${!NEED[@]}"; do
  if [ -f "$f" ]; then ok "$(numfmt --to=iec "$(stat -c%s "$f")")  $(basename "$f")  — ${NEED[$f]}"
  else no "缺失：$f  — ${NEED[$f]}"; fi
done

echo
echo "=========== 3. 工作流里引用的资源是否都在 ==========="
# 从 wf_one / dy_key 各抽一个工作流，把 LoadAudio / LoadImage 的路径解析成绝对路径检查
check_wf () {
  local f=$1
  "$PY" - "$f" "$C/input" <<'PY' | while read -r line; do
import json,sys,os
wf=json.load(open(sys.argv[1])); base=sys.argv[2]
for k,v in wf.items():
    ct=v.get("class_type","")
    i=v.get("inputs",{})
    if ct=="LoadAudio": print("AUDIO\t%s\t%s"%(i.get("audio",""),os.path.join(base,i.get("audio",""))))
    if ct=="LoadImage": print("IMAGE\t%s\t%s"%(i.get("image",""),os.path.join(base,i.get("image",""))))
PY
    kind=${line%%$'\t'*}; rest=${line#*$'\t'}; rel=${rest%%$'\t'*}; abs=${rest#*$'\t'}
    [ -f "$abs" ] && ok "$kind $rel" || no "$kind $rel  → 不存在: $abs"
  done
}
for f in "$C/../trilogy/wf_one"/wf_f1s01.json "$C/../trilogy/wf_one"/wf_f2s05.json; do
  [ -f "$f" ] && { echo "  -- $(basename "$f")"; check_wf "$f"; }
done
for f in /workspace/dy_key/wf/wf_dy1_s01_open_kick.json /workspace/dy_key/wf/wf_dy1_prod_pour.json; do
  [ -f "$f" ] && { echo "  -- $(basename "$f")"; check_wf "$f"; }
done

echo
echo "=========== 4. 节点与工具 ==========="
for n in comfyui-minimax-h3-audio-T8 ComfyUI-KJNodes ComfyUI-MiniMaxH3-TeaCache; do
  [ -d "$C/custom_nodes/$n" ] && ok "节点 $n ($(git -C "$C/custom_nodes/$n" log -1 --format=%h 2>/dev/null))" || no "节点缺失 $n"
done
command -v ffmpeg >/dev/null && ok "ffmpeg $(ffmpeg -version 2>/dev/null | head -1 | awk '{print $3}')" || no "ffmpeg 缺失 → T8 存 H.264 会中断"
"$PY" -c 'import torch;assert torch.cuda.is_available();print("torch",torch.__version__)' >/dev/null 2>&1 \
  && ok "torch CUDA 可用" || no "torch CUDA 不可用"

echo
echo "=========== 5. 提交器 ==========="
[ -f "$SUB" ] && ok "submit_api.py 存在" || no "缺 $SUB（它只吃 API 格式，且拒绝顶层非节点键）"

if [ "${1:-}" = "--run" ]; then
  echo
  echo "=========== 6. 真跑一镜（约 10 分钟，含冷启）==========="
  K=f1s01
  [ -f /workspace/trilogy/wf_one/wf_$K.json ] || K=$(ls /workspace/dy_key/wf/*.json | head -1 | xargs basename | sed 's/^wf_//;s/\.json$//')
  WF=/workspace/trilogy/wf_one/wf_$K.json
  [ -f "$WF" ] || WF=/workspace/dy_key/wf/wf_$K.json
  echo "  用 $WF 提交到 :8188"
  t0=$SECONDS
  if "$PY" "$SUB" "$WF" --host http://127.0.0.1:8188 --timeout 2400; then
    ok "出镜成功，用时 $((SECONDS-t0))s（冷启首镜 600–850 s 属正常）"
    echo "  产物："
    find "$C/output" -name '*.mp4' -newermt "-30 minutes" -printf '    %12s  %p\n' 2>/dev/null | tail -5
  else
    LOGF=$([ "$LAUNCH" = "both" ] && echo /workspace/logs/comfy_a.log || echo /workspace/logs/comfy_single.log)
    no "提交失败，看日志： tail -50 $LOGF"
  fi
fi

echo
echo "============================================================"
echo "  通过 $PASS 项 · 失败 $FAIL 项"
[ "$FAIL" -eq 0 ] && echo "  ✓ 链路通，可以开始跑批" || echo "  ✗ 先修上面的 FAIL 再跑批"
echo "============================================================"
exit $([ "$FAIL" -eq 0 ] && echo 0 || echo 1)
