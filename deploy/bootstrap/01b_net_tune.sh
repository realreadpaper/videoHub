#!/usr/bin/env bash
# ============================================================
# 01b_net_tune.sh — 目标机网络栈调优 + 国内源切换（幂等，可重复跑）
#
# 在 01_provision_os.sh 之后、02_build_stack.sh 之前执行。
#
# 背景（2026-09-19 在 gpu1 实测得出，非推测）：
#   · 服务器在【国内】时，瓶颈不在链路而在【源站选择】
#     - GitHub 直连 0.045 MB/s（跨境乱序：rcv_ooopack 140、minrtt 78ms）→ 必须中转
#     - HuggingFace 官方不通 → 必须走 hf-mirror
#   · 服务器在【境外】时（旧机 kehu），瓶颈是跨境丢包
#     - cubic 遇丢包把 cwnd 打到 2 个 MSS，单流 0.11 MB/s；开 BBR 后 6 MB/s
#   · ★ BBR 只优化本机【发包】方向。从 GitHub/HF 下载时本机是接收方，
#     拥塞控制由对方决定，开 BBR 救不了下载。下载要靠换源/多连接/中转。
#   · ★ 大缓冲对【接收】有直接收益：hf-mirror 单流 7.79 → 39.96 MB/s
#
# 用法： bash 01b_net_tune.sh
# ============================================================
set -eu

APT_MIRROR=${APT_MIRROR:-mirrors.aliyun.com}
PIP_MIRROR=${PIP_MIRROR:-https://mirrors.aliyun.com/pypi/simple/}
HF_MIRROR=${HF_MIRROR:-https://hf-mirror.com}
TS=$(date +%Y%m%d%H%M%S)

say() { printf '\n########## %s ##########\n' "$*"; }

say "0/6 备份"
mkdir -p /root/net-tune-backup
for f in /etc/apt/sources.list.d/ubuntu.sources /etc/pip.conf /etc/environment; do
  [ -f "$f" ] && cp -n "$f" "/root/net-tune-backup/$(basename "$f").bak.$TS" 2>/dev/null || true
done
echo "  备份目录 /root/net-tune-backup"

say "1/6 内核网络栈"
cat > /etc/sysctl.d/99-net-speed.conf <<'EOF'
# 跨机房/跨境大文件传输（权重下载、产出回传）
# BBR 基于带宽-时延积建模，对丢包/乱序不敏感；
# 缓冲区默认 208 KB 远不够 100 ms × 100 Mbps 的 BDP。
net.core.default_qdisc = fq
net.ipv4.tcp_congestion_control = bbr

net.core.rmem_max = 33554432
net.core.wmem_max = 33554432
net.core.rmem_default = 1048576
net.core.wmem_default = 1048576
net.ipv4.tcp_rmem = 4096 262144 33554432
net.ipv4.tcp_wmem = 4096 262144 33554432

net.ipv4.tcp_window_scaling = 1
net.ipv4.tcp_mtu_probing = 1
net.ipv4.tcp_slow_start_after_idle = 0
net.ipv4.tcp_fastopen = 3
net.ipv4.tcp_tw_reuse = 2
net.ipv4.tcp_fin_timeout = 30
net.ipv4.tcp_notsent_lowat = 131072
net.core.netdev_max_backlog = 16384
net.core.somaxconn = 8192
net.ipv4.tcp_max_syn_backlog = 8192
net.ipv4.ip_local_port_range = 10240 65535
EOF
echo tcp_bbr > /etc/modules-load.d/bbr.conf
modprobe tcp_bbr 2>/dev/null || true
sysctl --system >/dev/null
printf '  cong=%s  qdisc=%s  rmem_max=%s\n' \
  "$(sysctl -n net.ipv4.tcp_congestion_control)" \
  "$(sysctl -n net.core.default_qdisc)" \
  "$(sysctl -n net.core.rmem_max)"

say "2/6 apt 源（自动选最快的国内镜像）"
SU=/etc/apt/sources.list.d/ubuntu.sources
if [ -f "$SU" ]; then
  # ★ 国内镜像质量随时间剧烈波动（实测阿里云 12 MB/s ↔ 0.22 MB/s 都出现过），
  #   所以不写死，每次部署现测现选。
  if [ -n "${APT_MIRROR_FIXED:-}" ]; then
    BEST="$APT_MIRROR_FIXED"; echo "  使用指定镜像 $BEST"
  else
    PROBE_PATH=/ubuntu/dists/noble/universe/binary-amd64/Packages.gz
    BEST=""; BEST_SP=0
    for m in mirrors.aliyun.com mirrors.ustc.edu.cn repo.huaweicloud.com \
             mirrors.cloud.tencent.com mirrors.tuna.tsinghua.edu.cn; do
      sp=$(curl -sL -m 10 -r 0-8388608 -o /dev/null -w '%{speed_download}' "https://$m$PROBE_PATH" 2>/dev/null || echo 0)
      case "$sp" in ''|*[!0-9.]*) sp=0 ;; esac
      printf '  %-32s %8.2f MB/s\n' "$m" "$(awk -v s="$sp" 'BEGIN{print s/1048576}')"
      if awk -v a="$sp" -v b="$BEST_SP" 'BEGIN{exit !(a>b)}'; then BEST="$m"; BEST_SP="$sp"; fi
    done
    [ -n "$BEST" ] || BEST="$APT_MIRROR"
    echo "  → 选中 $BEST（$(awk -v s="$BEST_SP" 'BEGIN{printf "%.2f", s/1048576}') MB/s）"
  fi

  # 注意分隔符用 # 而非 |：模式里有 (archive|security) 交替，用 | 当分隔符会撞车
  sed -i -E "s#https?://(archive|security)\.ubuntu\.com/ubuntu#https://${BEST}/ubuntu#g" "$SU"
  sed -i -E "s#https?://mirrors\.[a-z0-9.-]+/ubuntu#https://${BEST}/ubuntu#g" "$SU"
  # 去掉用不到的 noble-backports，省一份索引
  sed -i 's/^Suites: noble noble-updates noble-backports$/Suites: noble noble-updates/' "$SU"
  grep -E '^(URIs|Suites):' "$SU" | sed 's/^/  /'
  APT_MIRROR="$BEST"
else
  echo "  ⚠ 未找到 $SU，请手工确认源"
fi

say "3/6 apt 取数优化"
cat > /etc/apt/apt.conf.d/99-fast.conf <<'EOF'
// Translation-* 占索引体积的大头，服务器用不到本地化描述
Acquire::Languages "none";
// 实测 apt 的索引下载单连接只有 ~150 KB/s（同 URL curl 12-40 MB/s），
// 关掉管道化与 IPv6 回退，减少不必要的等待
Acquire::http::Pipeline-Depth "0";
Acquire::https::Pipeline-Depth "0";
Acquire::ForceIPv4 "true";
Acquire::Retries "5";
Acquire::http::Timeout "30";
Acquire::https::Timeout "30";
EOF
cat > /etc/apt/apt.conf.d/99-noextra.conf <<'EOF'
// 服务器不需要桌面软件中心用的索引（图标 / DEP-11 / Contents / c-n-f）
Acquire::IndexTargets::deb::DEP-11 { DefaultEnabled "false"; };
Acquire::IndexTargets::deb::DEP-11-icons { DefaultEnabled "false"; };
Acquire::IndexTargets::deb::DEP-11-icons-small { DefaultEnabled "false"; };
Acquire::IndexTargets::deb::Contents-deb { DefaultEnabled "false"; };
Acquire::IndexTargets::deb::Contents-udeb { DefaultEnabled "false"; };
Acquire::IndexTargets::deb::Contents-deb-legacy { DefaultEnabled "false"; };
Acquire::IndexTargets::deb::cnf { DefaultEnabled "false"; };
EOF
echo "  已写入 99-fast.conf / 99-noextra.conf"
echo "  ★ 关于 apt 慢：2026-09-19 实测【根因是选错镜像】，不是 apt 实现问题。"
  echo "    阿里云当时只有 151 KB/s（update 189 s / 28 MB），换中科大后 5.1 MB/s（5 s）。"
  echo "    所以上面第 2 步做了自动选源 —— 这一步比下面这些调优项都值钱。"

say "4/6 pip 源 → ${PIP_MIRROR}"
# ★ 与 apt 同理：国内 pypi 镜像质量也会波动，主源 + 备用源都写上。
#   若 pip 慢，用 net_diag.sh 的方法现测（下载一个 wheel 计时）后改这里。
cat > /etc/pip.conf <<EOF
[global]
index-url = ${PIP_MIRROR}
extra-index-url = https://mirrors.ustc.edu.cn/pypi/simple/
                  https://pypi.tuna.tsinghua.edu.cn/simple
trusted-host = mirrors.aliyun.com
               mirrors.ustc.edu.cn
               pypi.tuna.tsinghua.edu.cn
timeout = 120
retries = 5
EOF
echo "  已写入 /etc/pip.conf（阿里云为主，中科大/清华备用）"

say "5/6 HuggingFace → ${HF_MIRROR}"
grep -q '^HF_ENDPOINT=' /etc/environment 2>/dev/null || \
  echo "HF_ENDPOINT=${HF_MIRROR}" >> /etc/environment
cat > /etc/profile.d/00-hf-mirror.sh <<EOF
# HuggingFace 国内镜像
# ⚠ /etc/environment 只对 PAM 登录会话生效；非交互 ssh 命令读不到。
#   脚本里请显式 `source /etc/profile.d/00-hf-mirror.sh`，或内联传环境变量。
export HF_ENDPOINT=${HF_MIRROR}
EOF
chmod 644 /etc/profile.d/00-hf-mirror.sh
echo "  /etc/environment 与 /etc/profile.d/00-hf-mirror.sh 均已写入"

say "6/6 apt update + 安装下载/诊断工具"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq 2>&1 | tail -2 || true
apt-get install -y -qq aria2 mtr-tiny ca-certificates 2>&1 | tail -2 || true
printf '  aria2c: %s\n' "$(command -v aria2c || echo 未装上)"
printf '  mtr   : %s\n' "$(command -v mtr || echo 未装上)"

cat <<'EOM'

============================================================
网络调优完成。后续下载请按【源】选通道：

| 内容 | 通道 | 实测速度 |
|---|---|---|
| 模型权重（71 GB） | aria2c -x16 走 hf-mirror | 51 MB/s（≈25 分钟） |
| HuggingFace 官方 | 不通，必须 HF_ENDPOINT=hf-mirror | — |
| ComfyUI 源码 / custom_nodes | ★ 不要在本机直接 clone | 0.045 MB/s |
|   └ 方案 A | 本机（Clash 代理）拉好后 scp 上来 | 9.66 MB/s 拉 + 6.25 MB/s 推 |
|   └ 方案 B | 从旧机 kehu 直接 scp（境外机 GitHub 快） | ~6 MB/s |
| apt 索引 / 装包 | 自动选最快的国内镜像 | 中科大 31.84 MB/s（update 189s→5s） |
| torch wheel（~2.5 GB） | ⚠ 待实测：阿里云 / 交大有 pytorch-wheels 镜像；官方源波动 0.03–5.8 MB/s | 装之前先测 |

★ **镜像质量随时间剧烈波动**：同一台机实测阿里云在 12 MB/s ↔ 0.2 MB/s 之间跳，
清华在 403 ↔ 0.15 MB/s。所以本脚本不写死镜像，**每次部署现测现选**。
pip 同理 —— 若 pip 慢，用同样的方法现测再改 `/etc/pip.conf`。

排错用 bash net_diag.sh —— 它把这轮的判据都固化了。
EOM
