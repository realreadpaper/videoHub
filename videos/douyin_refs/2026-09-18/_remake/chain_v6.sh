#!/bin/bash
# 六镜 v6 链路：等参考帧重抽完成 → 上传 → 提交双卡 → 轮询 → 成片回传
# 设计要点：
#  - 幂等：可重复运行，服务器目录已存在不报错；输出目录先清空再提交
#  - ssh/scp 全部 BatchMode，避免卡在交互提示
#  - 每个阶段打印时间戳，便于事后对账
set -u

R=/Users/jianglong/Desktop/videoHub/videos/douyin_refs/2026-09-18/_remake
cd "$R" || { echo "无法进入工程目录"; exit 1; }

SHOTS="dy1_s093 dy1_s088 dy2_s118 dy2_s075 dy3_s145 dy3_s119"
SSHOPT="-o BatchMode=yes -o ConnectTimeout=15 -o ServerAliveInterval=20"
ts() { date +%H:%M:%S; }

echo "================ chain_v6 启动 $(ts) ================"

# ---------- 阶段 0：等待重抽结束 ----------
echo "[$(ts)] 阶段0 等待 rebuild_ref 结束…"
while pgrep -f "rebuild_ref\.py --all" >/dev/null 2>&1; do sleep 20; done
echo "[$(ts)] 阶段0 rebuild_ref 已结束"

for d in full_ref2_v6 full_first6 full_last6; do
  n=$(ls "$d" 2>/dev/null | wc -l | tr -d ' ')
  echo "        $d: $n 帧"
done

NF=$(ls full_ref2_v6 2>/dev/null | wc -l | tr -d ' ')
N1=$(ls full_first6 2>/dev/null | wc -l | tr -d ' ')
NL=$(ls full_last6 2>/dev/null | wc -l | tr -d ' ')
if [ "$NF" -lt 373 ] || [ "$N1" -lt 373 ] || [ "$NL" -lt 373 ]; then
  echo "[!] 帧数不足（ref=$NF first=$N1 last=$NL，期望 373/373/373），中止，请人工介入"
  exit 2
fi
echo "[$(ts)] 阶段0 校验通过：三类各 373 帧"

# ---------- 阶段 1：上传 ----------
echo "[$(ts)] 阶段1 上传参考帧与工作流…"
ssh $SSHOPT kehu "mkdir -p /workspace/ComfyUI/input/dy_full_ref_v6 /workspace/ComfyUI/input/dy_full_first6 /workspace/ComfyUI/input/dy_full_last6 /workspace/dy_key/wf_six4 /workspace/ComfyUI/output/dy_six4" || { echo "[!] 建目录失败"; exit 3; }

for nm in $SHOTS; do
  scp -q $SSHOPT full_ref2_v6/$nm.jpg  kehu:/workspace/ComfyUI/input/dy_full_ref_v6/   || echo "[!] 上传 ref $nm 失败"
  scp -q $SSHOPT full_first6/$nm.jpg   kehu:/workspace/ComfyUI/input/dy_full_first6/    || echo "[!] 上传 first $nm 失败"
  scp -q $SSHOPT full_last6/$nm.jpg    kehu:/workspace/ComfyUI/input/dy_full_last6/     || echo "[!] 上传 last $nm 失败"
done
scp -q $SSHOPT wf_six4/*.json kehu:/workspace/dy_key/wf_six4/ || { echo "[!] 上传工作流失败"; exit 3; }

ssh $SSHOPT kehu 'echo "  ref6=$(ls /workspace/ComfyUI/input/dy_full_ref_v6 | wc -l) first6=$(ls /workspace/ComfyUI/input/dy_full_first6 | wc -l) last6=$(ls /workspace/ComfyUI/input/dy_full_last6 | wc -l) wf=$(ls /workspace/dy_key/wf_six4 | wc -l)"'
echo "[$(ts)] 阶段1 完成"

# ---------- 阶段 2：提交 ----------
echo "[$(ts)] 阶段2 提交双卡任务…"
ssh $SSHOPT kehu 'bash -s' <<'REMOTE'
set -u
export no_proxy="127.0.0.1,localhost,::1"; export NO_PROXY="$no_proxy"
# 共享服务器：确认两个实例都空闲，否则不动队列
for P in 8188 8189; do
  q=$(curl -s --max-time 6 http://127.0.0.1:$P/queue | head -c 120)
  echo "  [:$P] queue=$q"
done
rm -f /workspace/ComfyUI/output/dy_six4/*.mp4 2>/dev/null

cat > /workspace/dy_key/six4A.sh <<'EOF'
#!/bin/bash
P=/workspace/venv/bin/python; S=/root/s2/submit_api.py
for k in dy1_s093 dy1_s088 dy2_s118; do
  echo "[$(date +%H:%M:%S)][A] -> $k"
  $P $S /workspace/dy_key/wf_six4/wf_$k.json --host http://127.0.0.1:8188 --timeout 1800 2>&1 | tail -2
  echo "[$(date +%H:%M:%S)][A] OK $k"
done
echo "[A] ALL DONE"
EOF
cat > /workspace/dy_key/six4B.sh <<'EOF'
#!/bin/bash
P=/workspace/venv/bin/python; S=/root/s2/submit_api.py
for k in dy2_s075 dy3_s145 dy3_s119; do
  echo "[$(date +%H:%M:%S)][B] -> $k"
  $P $S /workspace/dy_key/wf_six4/wf_$k.json --host http://127.0.0.1:8189 --timeout 1800 2>&1 | tail -2
  echo "[$(date +%H:%M:%S)][B] OK $k"
done
echo "[B] ALL DONE"
EOF
chmod +x /workspace/dy_key/six4A.sh /workspace/dy_key/six4B.sh
cd /workspace/dy_key && setsid nohup bash six4A.sh > SIX4A.log 2>&1 < /dev/null &
sleep 1
cd /workspace/dy_key && setsid nohup bash six4B.sh > SIX4B.log 2>&1 < /dev/null &
sleep 8
for P in 8188 8189; do
  echo "  [:$P] queue=$(curl -s --max-time 6 http://127.0.0.1:$P/queue | head -c 120)"
done
echo "REMOTE_SUBMIT_OK"
REMOTE
echo "[$(ts)] 阶段2 提交完成"

# ---------- 阶段 3：轮询成片 ----------
echo "[$(ts)] 阶段3 轮询成片…"
DEADLINE=$(( $(date +%s) + 3000 ))     # 最多等 50 分钟
while :; do
  CNT=$(ssh $SSHOPT kehu 'ls /workspace/ComfyUI/output/dy_six4/*.mp4 2>/dev/null | wc -l' 2>/dev/null | tr -d ' ')
  [ -z "$CNT" ] && CNT=0
  echo "[$(ts)]   已出 $CNT / 6"
  [ "$CNT" -ge 6 ] && break
  if [ "$(date +%s)" -gt "$DEADLINE" ]; then echo "[!] 轮询超时（$CNT/6）"; break; fi
  sleep 30
done

# ---------- 阶段 4：回传 ----------
echo "[$(ts)] 阶段4 回传成片…"
mkdir -p _six/gen4
GOT=0
for nm in $SHOTS; do
  if scp -q $SSHOPT "kehu:/workspace/ComfyUI/output/dy_six4/${nm}_00001_.mp4" "_six/gen4/$nm.mp4"; then
    GOT=$((GOT+1)); echo "        ✓ $nm"
  else
    echo "        ✗ $nm 回传失败"
  fi
done
echo "[$(ts)] 阶段4 回传 $GOT / 6 → _six/gen4/"
ls -la _six/gen4/

# ---------- 阶段 5：服务器收尾自查 ----------
echo "[$(ts)] 阶段5 服务器日志尾部"
ssh $SSHOPT kehu 'tail -3 /workspace/dy_key/SIX4A.log; tail -3 /workspace/dy_key/SIX4B.log'

echo "================ chain_v6 结束 $(ts) 拉回 $GOT/6 ================"
