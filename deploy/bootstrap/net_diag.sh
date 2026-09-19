#!/usr/bin/env bash
# ============================================================
# net_diag.sh — 网络"慢"的一分钟定位（只读；不改任何配置）
#
# 固化了 2026-09-19 在 gpu1 / kehu 上验证过的三条判据：
#   ① 是不是管道带宽上限？    → 并行 vs 单流，**不涨就是上限**，别再折腾内核
#   ② 丢包还是乱序？          → ss -tnpi 看 cwnd / retrans / rcv_ooopack
#   ③ 源站选对了吗？          → 逐源测速（多数"慢"其实是源站不对）
#
# 用法：
#   bash net_diag.sh            # 全套快照
#   bash net_diag.sh --live URL # 下载 URL 期间抓 15 秒 TCP 内部状态
# ============================================================
set -u

IFACE=$(ip route 2>/dev/null | awk '/^default/{print $5; exit}')
IFACE=${IFACE:-eth0}
rx() { cat /sys/class/net/$IFACE/statistics/rx_bytes 2>/dev/null || echo 0; }
hr() { printf '%s\n' "------------------------------------------------------------"; }
say() { printf '\n=== %s ===\n' "$*"; }

if [ "${1:-}" = "--live" ] && [ -n "${2:-}" ]; then
  URL="$2"
  say "抓 TCP 内部状态：$URL （15 秒）"
  curl -sL -o /dev/null "$URL" >/dev/null 2>&1 &
  CP=$!
  sleep 4
  R0=$(rx); sleep 10; R1=$(rx)
  echo "  网卡实测速率: $(( (R1-R0)/1024/10 )) KB/s  （$(( (R1-R0)/1048576 )) MB / 10 s）"
  echo
  echo "  443 连接的 TCP 内部状态："
  ss -tnpi state established '( dport = :443 )' 2>/dev/null \
    | grep -oE 'cwnd:[0-9]+|rtt:[0-9.]+/[0-9.]+|retrans:[0-9]+/[0-9]+|rcv_ooopack:[0-9]+|delivery_rate [0-9]+|bw:[0-9]+bps|app_limited' \
    | sed 's/^/    /' | head -20
  kill $CP 2>/dev/null
  echo
  echo "  读法："
  echo "    cwnd 个位数 + retrans 成千  → 丢包型，开 BBR"
  echo "    rcv_ooopack 大              → 乱序型，跨境常见，靠多连接/中转"
  echo "    app_limited 且速率低        → 本机消费侧瓶颈（磁盘/CPU/工具实现）"
  exit 0
fi

say "0. 机器身份"
echo "  hostname : $(hostname)"
echo "  出口 IP  : $(curl -s -m 8 https://myip.ipip.net 2>/dev/null || curl -s -m 8 http://ip.3322.net 2>/dev/null || echo '取不到')"
echo "  到阿里 DNS 223.5.5.5 的 RTT : $(ping -c 2 -W 2 223.5.5.5 2>/dev/null | tail -1 | awk -F'/' '{print $5" ms"}' || echo '不通')"
echo "  到 8.8.8.8 的 RTT          : $(ping -c 2 -W 2 8.8.8.8 2>/dev/null | tail -1 | awk -F'/' '{print $5" ms"}' || echo '不通')"
echo "  （223.5.5.5 明显快于 8.8.8.8 → 本机大概率在国内）"

say "1. 内核网络栈"
for k in net.ipv4.tcp_congestion_control net.core.default_qdisc \
         net.core.rmem_max net.core.wmem_max net.ipv4.tcp_rmem net.ipv4.tcp_wmem \
         net.ipv4.tcp_mtu_probing net.ipv4.tcp_slow_start_after_idle net.ipv4.tcp_fastopen; do
  printf '  %-38s %s\n' "$k" "$(sysctl -n $k 2>/dev/null || echo '-')"
done

say "2. 网卡与协议栈健康度"
echo "  接口: $IFACE   MTU: $(cat /sys/class/net/$IFACE/mtu 2>/dev/null)"
for f in rx_dropped rx_errors tx_dropped tx_errors; do
  printf '  %-14s %s\n' "$f" "$(cat /sys/class/net/$IFACE/statistics/$f 2>/dev/null || echo '-')"
done
echo "  --- TCP 累计统计 ---"
nstat -az 2>/dev/null | grep -E 'TcpRetransSegs|TcpExtTCPLostRetransmit|TcpInErrs|TcpExtTCPOFOQueue' | sed 's/^/  /' || echo "  (nstat 不可用)"
echo "  ★ TcpExtTCPOFOQueue 很大 → 路径有乱序，BBR 比 cubic 更能扛"

say "3. 源站可用性矩阵（各取前 8 MB）"
probe() {
  local label="$1" url="$2"
  local out
  out=$(curl -sL -m 12 -r 0-8388608 -o /dev/null -w '%{http_code} %{speed_download}' "$url" 2>/dev/null)
  printf '  %-26s HTTP=%s  %8.2f MB/s\n' "$label" \
    "$(echo "$out" | awk '{print $1}')" "$(echo "$out" | awk '{print $2/1048576}')"
}
U=/ubuntu/dists/noble/universe/binary-amd64/Packages.gz
probe "hf-mirror"          "https://hf-mirror.com/Comfy-Org/MiniMax-H3/resolve/main/vae/minimax_h3_video_vae_fp16.safetensors"
probe "阿里云 apt"          "https://mirrors.aliyun.com$U"
probe "中科大 apt"          "https://mirrors.ustc.edu.cn$U"
probe "华为云 apt"          "https://repo.huaweicloud.com$U"
probe "pytorch 官方"        "https://download.pytorch.org/whl/cu130"
probe "GitHub codeload ★"   "https://codeload.github.com/comfyanonymous/ComfyUI/tar.gz/ee71d5c4993f29086b27fde1629a945ae48425bf"
probe "GitHub raw"          "https://raw.githubusercontent.com/comfyanonymous/ComfyUI/master/README.md"

say "4. apt 分两段量（索引 vs 装包，别混为一谈）"
echo "  apt 源: $(grep -m1 '^URIs:' /etc/apt/sources.list.d/ubuntu.sources 2>/dev/null | sed 's/URIs: //' || echo '-')"
R0=$(rx); T0=$(date +%s)
apt-get update -qq >/dev/null 2>&1 || true
T1=$(date +%s); R1=$(rx)
EL=$((T1-T0)); [ "$EL" -eq 0 ] && EL=1
echo "  索引 apt-get update : ${EL}s, $(( (R1-R0)/1048576 )) MB → $(( (R1-R0)/1024/EL )) KB/s"
echo "  ★ 实测经验：索引慢（~150 KB/s）是 apt 自身行为，但【装包】正常。
    只要 install 快，就不必绕开 apt。归档大文件请用 aria2c -x16。"

cat <<'EOM'

============================================================
判据与处方（按此顺序排查，别跳步）
============================================================
① 先量"是管道还是单流"
   并行多路 vs 单流：不涨 → 管道带宽上限，改不了，只能压文件/分时传
                     涨了 → 单流受限，往下查
② 再看 TCP 内部状态（--live，或传输中手工 ss -tnpi）
   cwnd 个位数 + retrans 上千 → 丢包型 → 开 BBR
   rcv_ooopack 大             → 乱序型 → 多连接 + 中转
   app_limited 且速率低       → 本机消费侧（工具实现/磁盘/CPU）
③ 最后看源站
   同一 URL 换工具测：curl 快而 apt 慢 → 是工具实现问题，不是网络
   GitHub 直连慢 → 用代理/中转，别指望开 BBR
EOM
