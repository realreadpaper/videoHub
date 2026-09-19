#!/usr/bin/env bash
# ============================================================
# 05_push_assets.sh — 从**本机**把生产资产推到新服务器
# 在本机（macOS 工作仓库根目录）执行，不是目标机上。
#
# 用法：
#   bash deploy/bootstrap/05_push_assets.sh <新机ssh别名> [--dry]
# 例：
#   bash deploy/bootstrap/05_push_assets.sh kehu2
#
# 推的内容（全部来自本仓库 + deploy/server-assets/）：
#   /root/s2/submit_api.py                     提交器（唯一的 API 侧脚本）
#   /workspace/trilogy/                          三部曲生产区（wf_one 24 镜 + keys + 运行脚本）
#   /workspace/dy_key/                           抖音关键镜区（wf + worker 脚本）
#   /workspace/ComfyUI/input/…                   干声 / 参考图 / 静音垫
#   /workspace/dl/ + install_sage*.sh            环境重建脚本（留档）
# ============================================================
set -eu

HOST=${1:?用法: bash 05_push_assets.sh <新机ssh别名> [--dry]}
DRY=${2:-}
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"      # 仓库根
SA="$ROOT/deploy/server-assets"
SRC_TRILOGY="$ROOT/待生成_现代婚姻三部曲/_pipeline"

[ -d "$SA" ] || { echo "✗ 找不到 $SA"; exit 1; }

# ★ macOS 自带的是 openrsync（自称 2.6.9），**没有 --info=stats2**，
#   直接照抄 GNU rsync 的选项会 unrecognized option 报错退出。
#   这里做一次能力探测：现代 rsync 用 --info=stats2，老/BSD 系退回 --stats。
#   实测 macOS 26 的 openrsync ↔ Ubuntu 24.04 的 rsync 3.2.7 通信正常（协议 29）。
RSYNC_OPTS="-az"
if rsync --info=stats2 --version >/dev/null 2>&1; then
  RSYNC_OPTS="$RSYNC_OPTS --info=stats2"
else
  RSYNC_OPTS="$RSYNC_OPTS --stats"      # openrsync / rsync 2.6.9 路径
fi
RSYNC="rsync $RSYNC_OPTS -e 'ssh -o ConnectTimeout=20'"
[ "$DRY" = "--dry" ] && RSYNC="$RSYNC --dry-run"
run() { echo "▶ $*"; eval "$RSYNC $*"; }

echo "=== 目标机: $HOST ==="
ssh -o ConnectTimeout=20 -o BatchMode=yes "$HOST" 'echo ok; hostname; nvidia-smi --query-gpu=name --format=csv,noheader' \
  || { echo "✗ SSH 不通，先解决连通性"; exit 1; }

echo
echo "=== 建目录 ==="
ssh "$HOST" 'mkdir -p /root/s2 /workspace/{trilogy,dy_key,dl,logs} \
  /workspace/ComfyUI/input/{tts_dry/trilogy,dy_voice,dy_refs} \
  /workspace/ComfyUI/input/{dy4_first,dy4_last,dy4_ref,dy4_voice} \
  /workspace/ComfyUI/output/{dy_key,dy_skel,MiniMaxH3/trilogy_one}'

echo
echo "=== 1/6 提交器 ==="
run "$SA/root/s2/submit_api.py  $HOST:/root/s2/"
ssh "$HOST" 'chmod +x /root/s2/submit_api.py'

echo
echo "=== 2/6 三部曲工作流（权威源 = 本机 _pipeline/wf_one，已与旧机 md5 一致）==="
echo "    wf_one: $(ls "$SRC_TRILOGY/wf_one" 2>/dev/null | wc -l) 个 · wf_pipeline: $(ls "$SRC_TRILOGY/wf" 2>/dev/null | wc -l) 个"
run "$SRC_TRILOGY/wf_one/       $HOST:/workspace/trilogy/wf_one/"
run "$SRC_TRILOGY/wf/           $HOST:/workspace/trilogy/wf_pipeline/"
run "$SRC_TRILOGY/keys.txt      $HOST:/workspace/trilogy/" 2>/dev/null || true
run "$SA/trilogy/run_one_step_dual.sh $SA/trilogy/run_one_step.sh $SA/trilogy/convert_to_pipeline_wf.py $HOST:/workspace/trilogy/"
run "$ROOT/deploy/single-gpu/run_trilogy_single.sh $HOST:/workspace/trilogy/"   # 单卡跑批

echo
echo "=== 3/7 抖音关键镜工作流 + worker ==="
echo "    dy_key/wf: $(ls "$SA/dy_key/wf" 2>/dev/null | wc -l) 个"
run "$SA/dy_key/wf/            $HOST:/workspace/dy_key/wf/"
run "$SA/dy_key/run_worker.sh $SA/dy_key/pipeline_worker.sh $HOST:/workspace/dy_key/"
run "$SA/dy_key/tryA.sh $SA/dy_key/tryB.sh $HOST:/workspace/dy_key/" 2>/dev/null || true
run "$ROOT/deploy/single-gpu/run_dy_single.sh $HOST:/workspace/dy_key/"          # 单卡跑批
ssh "$HOST" 'chmod +x /workspace/trilogy/*.sh /workspace/dy_key/*.sh'

echo
echo "=== 4/7 抖音全量复刻（373 镜）★★ 最大的生产资产 ==="
echo "    wf_full: $(ls "$SA/dy_key/wf_full" 2>/dev/null | wc -l) 个工作流"
echo "    ★ 关键：每镜的音频 = 原片该镜音轨切片，参考图 = 原片该镜关键帧（已裁底部 10%）"
echo "      资源引用形如 LoadAudio='dy_full_a/dy1_s001.wav' / LoadImage='dy_full_ref/dy1_s001.jpg'"
run "$SA/dy_key/wf_full/        $HOST:/workspace/dy_key/wf_full/"
[ -d "$SA/inputs/dy_full_a" ]   && run "$SA/inputs/dy_full_a/   $HOST:/workspace/ComfyUI/input/dy_full_a/" \
  || echo "    [warn] 缺 $SA/inputs/dy_full_a（373 条音轨切片）"
[ -d "$SA/inputs/dy_full_ref" ] && run "$SA/inputs/dy_full_ref/ $HOST:/workspace/ComfyUI/input/dy_full_ref/" \
  || echo "    [warn] 缺 $SA/inputs/dy_full_ref（373 张参考帧）"

echo
echo "=== 5/7 输入资产（干声 / 参考图 / 静音垫）==="
echo "    ★ 这些是 *.wav/*.jpg，仓库 .gitignore 不收录，只在 deploy/server-assets/inputs/ 本地留档"
for d in tts_dry dy_voice dy_refs; do
  [ -d "$SA/inputs/$d" ] || { echo "    [warn] 缺 $SA/inputs/$d"; continue; }
  run "$SA/inputs/$d/          $HOST:/workspace/ComfyUI/input/$d/"
done
[ -f "$SA/inputs/silent_15s.wav" ] && run "$SA/inputs/silent_15s.wav $HOST:/workspace/ComfyUI/input/"

echo
echo "=== 5b/7 2026-09-19 试点资产（dy4/dy5 四条单元）==="
echo "    ★ 被 videos/douyin_refs/2026-09-19/_remake/wf/wf_dy4_*.json 引用，缺了工作流就跑不了"
echo "      LoadAudio='dy4_voice/dy4_u007_stomp.wav'"
echo "      LoadImage='dy4_ref|dy4_first|dy4_last/dy4_u007_stomp.jpg'"
for d in dy4_first dy4_last dy4_ref dy4_voice; do
  [ -d "$SA/inputs/$d" ] || { echo "    [warn] 缺 $SA/inputs/$d（2026-09-19 试点必需）"; continue; }
  run "$SA/inputs/$d/          $HOST:/workspace/ComfyUI/input/$d/"
done

echo
echo "=== 5c/7 参考帧抽检样本（小体积，用于新机复现清洗判据）==="
for d in dy_full_first4 dy_full_first5 dy_full_last4 dy_full_last5 dy_full_ref_v5; do
  [ -d "$SA/inputs/$d" ] || continue
  run "$SA/inputs/$d/          $HOST:/workspace/ComfyUI/input/$d/"
done
echo "    注：dy_full_first_v3 / dy_full_ref_v3（各 373 张）是历史迭代版本，"
echo "        现行 wf_full 引用的是 dy_full_ref（已随 4/7 推送），**不要**推 v3 覆盖。"

echo
echo "=== 5d/7 历史状态快照（★ 只留档，不推送）==="
echo "    deploy/server-assets/state/ 是旧机的 gates 门禁与 full_worker.sh 快照："
echo "      gates(39 done) · gates_full(12/373 done，dy1_s009/s010 有 lock 残留) · gates_one(2/24 done)"
echo "    ★ 刻意不推：新机上没有对应成片，推过去会让这些镜被误判为『已完成』而永久跳过。"
echo "      要续跑就让它从干净状态重跑；要接着旧机进度，必须先搬 output/ 成片再搬 gates。"

echo
echo "=== 6/7 环境重建脚本留档 ==="
run "$SA/dl/                    $HOST:/workspace/dl/"
run "$SA/install_sage.sh $SA/install_sage2.sh $HOST:/workspace/"

echo
echo "=== 7/7 网络/系统配置片段留档 ==="
run "$SA/sysctl.d/              $HOST:/etc/sysctl.d/" 2>/dev/null || \
  echo "    [warn] 直接写 /etc 需要 root+权限；01_provision_os.sh 已生成同样的文件，可跳过"

echo
echo "=== 校验 ==="
ssh "$HOST" 'echo "  wf_one:      $(ls /workspace/trilogy/wf_one | wc -l) 个"; \
             echo "  dy_key/wf:   $(ls /workspace/dy_key/wf | wc -l) 个"; \
             echo "  dy_key/wf_full: $(ls /workspace/dy_key/wf_full 2>/dev/null | wc -l) 个"; \
             echo "  tts_dry:     $(ls /workspace/ComfyUI/input/tts_dry/trilogy | wc -l) 个"; \
             echo "  dy_voice:    $(ls /workspace/ComfyUI/input/dy_voice | wc -l) 个"; \
             echo "  dy_refs:     $(ls /workspace/ComfyUI/input/dy_refs | wc -l) 个"; \
             echo "  dy_full_a:   $(ls /workspace/ComfyUI/input/dy_full_a 2>/dev/null | wc -l) 条音轨"; \
             echo "  dy_full_ref: $(ls /workspace/ComfyUI/input/dy_full_ref 2>/dev/null | wc -l) 张参考帧"; \
             echo "  dy4_*:       $(for d in dy4_first dy4_last dy4_ref dy4_voice; do echo -n \"$(ls /workspace/ComfyUI/input/$d 2>/dev/null | wc -l) \"; done)（各应 4）"; \
             echo "  提交器:      $(test -f /root/s2/submit_api.py && echo OK || echo MISSING)"'
echo
echo "完成。目标机执行（按你的卡数选一条）："
echo "   单卡： bash 04_launch_comfy.sh single   → 然后 cd /workspace/dy_key && bash run_dy_single.sh full"
echo "   双卡： bash 04_launch_comfy.sh both     → 然后 cd /workspace/dy_key && bash pipeline_worker.sh A 8188 & bash pipeline_worker.sh B 8189 &"
echo "   验收： bash verify.sh --run"
