# VideoHub / MiniMax-H3 项目长期记忆与技术规范

> 本文件记录远端 GPU 服务器（`kehu`）拓扑、ComfyUI 部署规范、模型与算子加速基准，供所有会话与自动化 Agent 继承遵循。
>
> ★ **换服务器时不要凭本文件重建** —— 完整清单与逐条命令见 `docs/新服务器部署手册.html`
> 与 `deploy/README.md`（含 `deploy/bootstrap/` 六个可执行脚本）。本文件是**判据**，不是安装指南。

---

## 1. 远端服务器与硬件拓扑

* **SSH 别名**：`ssh kehu` → `124.81.178.140`（旧 IP `49.0.196.218` 已废）
* **硬件规格**：
  * GPU：2 × NVIDIA A100-PCIE-40GB（SM80，**无 NVLink**，卡间走 PCIe）
  * 驱动：**580.95.05** / CUDA 13.0；**torch `2.14.0+cu130` 自带 CUDA 13 运行时，系统无需装 CUDA Toolkit**
  * 系统内存：**125 GB**（`ram_total` ≈ 134.8e9 B）；16 核；148 GB 盘（用掉 104 GB）
  * 系统：Ubuntu 22.04.2 LTS / 内核 5.15.0-76 / Python 3.10.12
  * 机房：华为云泰国
* **工作目录**：
  * `ComfyUI` → `/workspace/ComfyUI`；`venv` → `/workspace/venv`
  * 三部曲生产区 → `/workspace/trilogy`（`wf_one/` 一步直出 24 镜 · `wf_pipeline/` 两阶段 25 镜【废弃】）
  * 抖音关键镜区 → `/workspace/dy_key`（`wf/` 36 个 · `gates/` 断点续跑）
  * 环境重建脚本留档 → `/workspace/dl`；日志 → `/workspace/logs`
  * 提交器 → `/root/s2/submit_api.py`
  * 实例 B 的独立数据库 → `/workspace/instance_b.db`（**仅双卡需要；单卡不要建**）
* ★ **卡数形态（2026-09-19 起）**：**后续只租 1 张 A100**。上述 2× 配置是旧机实测基准，
  单卡的启动 / 跑批 / 内存门槛 / 时间账都与双卡不同：
  * 启动：`04_launch_comfy.sh single`（只起 8188）；**不要 `--database-url`**（单进程独占 sqlite）
  * 跑批：单 worker，用 `deploy/single-gpu/run_dy_single.sh {full|key}` / `run_trilogy_single.sh`
  * 内存：**单卡仍需 ≥ 96 GB**（40 G 卡装不下 50.2 GB 权重，必然 offload；单实例常驻 57 GB）
  * 时间：单镜 558 s **不变**；373 镜挂钟 **6h34m**（双卡 3.37 h）。换算律：
    **双卡报告的「GPU 总机时」= 单卡「挂钟」**
  * 详见 `docs/单卡A100部署手册.html` + `deploy/single-gpu/README.md`
* ★ **连不上先怀疑本机 Clash Verge 的 TUN**，不是密钥 → 技能 `ssh-tun-hijack-diagnosis`

---

## 2. 当前生产形态（2026-09-19 口径）

**一步直出 768×1344**：原生分辨率全噪声去噪，单阶段，**不经 LTX 精修**。

* **两阶段（H3 草稿 384×672 → LTX 精修）已废弃**。它依赖的 `/root/ui_to_api.py` 与
  `/workspace/films/s2_adapt.py` 在机器上**已不存在**；`/workspace/trilogy/run_server.sh`
  是 dead code，**不要"修复"它**。
  画质理由：精修是在 384×672 草稿上补细节，一步直出是原生全噪声 → 直出更硬，代价约 3.2× 时间。
* **TeaCache 已禁用（2026-09-19 用户决定）**：4 步下尾段拖影/涂抹，宁可慢也要干净。
  工作流链路 = `UNet → LoRA → Sampler`，加速只剩 **Turbo LoRA + ck-attention**。
  `wf_one/` 里 0 个 TeaCache 节点，`wf_pipeline/` 里 25 个（已废弃）。**不要往 wf_one 里加回来**。

### 2.1 版本与核心依赖

| 组件 | 版本 / commit |
|---|---|
| ComfyUI | **v0.36.0** · `ee71d5c4993f29086b27fde1629a945ae48425bf` |
| comfyui-minimax-h3-audio-T8 | v1.79.6 · `e12d8af8ac85540da9895cb629836a4947e221ca` |
| ComfyUI-KJNodes | `b3ec064dde7d122b333660918e1200e928e67ff1` |
| ComfyUI-MiniMaxH3-TeaCache | `4cbb50d69c73a19a5d6ec42c5aec1989d5a04b6f`（**装了不用**） |
| comfy-kitchen | **`0.2.34`**（必须 ≥0.2.34，内建 H3 融合算子） |
| comfyui-frontend-package | `1.52.7`；comfyui-workflow-templates `0.11.62` |
| torch / torchvision / torchaudio | `2.14.0+cu130` / `0.29.0+cu130` / `2.11.0+cu130` |
| 系统 | `ffmpeg` **必装**（T8 的 `MiniMaxH3SafeAVSaveT8Advanced` 存 H.264 长视频依赖它）、`aria2c` |

⚠ 旧 `/workspace/dl/build_env.sh` 里写的 `COMFY_COMMIT=f42b24e`（0.35）与 `comfy-kitchen==0.2.33`
**都是过时值**，照抄会掉 28% 采样速度。以本表为准。

### 2.2 启动（铁律：必须重定向 stdin；双卡还必须隔离数据库）

**单卡（现行形态）—— 只起一个，不需要 `--database-url`：**

```bash
CUDA_VISIBLE_DEVICES=0 setsid nohup /workspace/venv/bin/python /workspace/ComfyUI/main.py \
  --listen 127.0.0.1 --port 8188 --vram-headroom 1 --use-ck-attention \
  > /workspace/logs/comfy_single.log 2>&1 < /dev/null &
```

**双卡（旧机形态）：**

```bash
# GPU 0 · 8188
CUDA_VISIBLE_DEVICES=0 setsid nohup /workspace/venv/bin/python /workspace/ComfyUI/main.py \
  --listen 127.0.0.1 --port 8188 --vram-headroom 1 --use-ck-attention \
  > /workspace/logs/comfy_a.log 2>&1 < /dev/null &

# GPU 1 · 8189  ★ 必须独立 sqlite（四个斜杠），否则 Database is locked
CUDA_VISIBLE_DEVICES=1 setsid nohup /workspace/venv/bin/python /workspace/ComfyUI/main.py \
  --listen 127.0.0.1 --port 8189 --vram-headroom 1 --use-ck-attention \
  --database-url sqlite:////workspace/instance_b.db \
  > /workspace/logs/comfy_b.log 2>&1 < /dev/null &
```

* `--use-ck-attention` = comfy-kitchen 的 INT8 注意力通路，**A100 上唯一有效的注意力加速**
  （与卡数无关，单卡也必须带）
* `--vram-headroom 1` = DynamicVRAM 多留 1 GB 空闲
* `setsid` + `</dev/null` **都不能少**，否则 ssh 断开会把任务带走
* 快捷方式：`bash deploy/bootstrap/04_launch_comfy.sh {single|both|a|b|stop|status}`
  （★ 注意：旧机 `/workspace/dl/launch_comfy.sh` 的 `start_one()` **漏了 `--database-url`**）

---

## 3. MiniMax-H3 模型栈与工作流资产

| 角色 | 文件（相对 `ComfyUI/models/`） | 何时用 |
|---|---|---|
| DiT 主干 · fl2va | `diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors`（19.5 GiB） | 静音轮 / 无参考图 |
| DiT 主干 · ref2va | `diffusion_models/Minimax-h3_Singularity_ref2va_Pruned_v1.3_int8.safetensors`（19.5 GiB） | 参考图 / 原声锁轮 |
| Text Encoder | `text_encoders/minimax_h3/qwen3vl_32b_minimax_h3_int8_convrot.safetensors`（25.3 GiB） | **★ 必须在 `minimax_h3/` 子目录**，工作流写的是 `minimax_h3/qwen3vl_32b_…` |
| Video VAE | `vae/minimax_h3_video_vae_fp16.safetensors` | |
| Audio VAE | `vae/minimax_h3_audio_vae_fp32.safetensors` | |
| Turbo LoRA | `loras/minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors`（4 步） | |

* **权重文件名是硬契约**：工作流 json 写死这 6 个路径字符串，改名 / 放错目录 →
  400 `value_not_in_list`，且**跑完才报**。
* 一步直出工作流的节点构成（`wf_one/wf_f1s01.json` 共 14 个）：
  `UNETLoader` · `LoraLoaderBypassModelOnly` · `CLIPLoader` · `VAELoader`×2 · `LoadAudio`
  · `MiniMaxH3AudioConditioningT8` · `MiniMaxH3AudioWindowT8` · `MiniMaxH3DualClockSamplerT8`
  · `BasicGuider` · `RandomNoise` · `SamplerCustomAdvanced` · `MiniMaxH3AVDecodeT8`
  · `MiniMaxH3OutputTrimT8` · `MiniMaxH3SafeAVSaveT8Advanced`
* **中文台词走原声锁**：外部 TTS 干声写进 `wf["13"].audio`（`LoadAudio`），H3 自己说中文不稳。
  纯审画面的轮次挂 `silent_15s.wav`，prompt 音景写死 `No speech, no voices, no dialogue`。

---

## 4. 实测基准数据（Benchmark Records）

> 测试规格：MiniMax-H3 768×1344，13 秒长片（311 帧视频 + AAC 音频），4 NFE 采样

| 阶段 / 指标 | 升级前（commit f42b24e / kitchen 0.2.33） | 升级后（v0.36.0 / kitchen 0.2.34） | 提升收益 |
| :--- | :--- | :--- | :--- |
| **模型初始化与冷加载** | 128.2 秒 | **96.8 秒** | 提速 24.5% |
| **单步扩散采样平均耗时** | 131.1 秒 / step | **94.3 秒 / step** | **提速 28.1%** |
| **4步采样总耗时** | 527.0 秒 | **377.0 秒** | 节省 150 秒 |
| **单镜端到端总用时** | 590.7 秒（9分50秒） | **469.3 秒（7分49秒）** | **整体提速 20.5%** |
| **全量 24 镜批处理总耗时** | 约 2.0 小时 | **约 1.56 小时（1h34m）** | **整批净省 26 分钟** |

机理：CausalConv3d 的 Norm/SiLU/Pad 融合进 `ck.group_norm_silu_pad3d`，RMSNorm+RoPE 融合进
`ck.rms_rope_split_half`，INT8 GEMM epilogue 融合 SwiGLU/residual，动态瓦片解码支持至多 4 tiles 并发。

### 4.1 计时口径（混用会差 4 倍）

| 口径 | 单镜 | 定义 |
|---|---|---|
| **A · 热态批处理** | **≈550 s** | 同进程连跑、权重已驻留 → **凡排期一律用这个** |
| C · 每镜冷启 | ≈2400 s | 每镜重读 45 GB 权重 → 反事实上界，**绝不乘镜数** |

★ **A100 冷启 = 热态 4~5 倍**（首镜 382 s → 热态 74 s），是全项目最大的记账陷阱。
★ **任何 attention 类加速的天花板 = 注意力占比**（实测 354 帧时占每步 62%、全流程 54%）。
A100 是 SM80 **无 FP8**（INT8 只比 FP16 快 2 倍）且已开 ck-attention → 现实收益 −12%~−20%（70–130 秒/镜），达不到 30%。

### 4.2 已被实测否决的优化（不要重试）

| 手段 | 结论 | 证据 |
|---|---|---|
| SageAttention / flash_attn / xformers | **全 NaN** | `--use-sage-attention` 后 `ValueError: nonfinite IMAGE`；int8_convrot 对注意力数值精度敏感 |
| `--fast` | 更慢 | SM80 无原生 FP8；冷启 472 s，热态无收益 |
| 降步数 | 已到下限 | 4 步已是 Turbo LoRA 最低档 |
| FP8 / NVFP4 权重 | 不可用 | 需 sm89+，低于此自动回退 bf16 反量化 |
| VSA 稀疏注意力 | 不可用 | 官方仅 T2VA，原生核只到 sm_100a/sm_103a（Blackwell） |
| 单任务双卡（SP=2） | 更慢 | 24 镜预估 2.4 h > 双实例 1.56 h |

★ 编译 SageAttention **不必装系统 CUDA 12.8**：CUDA Toolkit 是系统级 11.4，但 torch `cu130`
自带 CUDA 13，用 `pip install nvidia-cuda-nvcc-cu12` 提供 nvcc 即可（见 `/workspace/install_sage.sh`）。
**最终未采用**（见上表第一行）。

---

## 5. 批处理与日常运维准则

1. **每镜前释放显存**：`POST http://127.0.0.1:<port>/free` 带
   `{"unload_models":true,"free_memory":true}`。
   ★ **返回 200 但响应体 0 字节，别 `json.loads`**。
2. **卡数策略**：
   * **单卡（现行）**：一个实例 + 一个 worker。用 `run_dy_single.sh {full|key}` /
     `run_trilogy_single.sh`（含队列预检、残留 lock 自动清理、拒绝双 worker）。
     长批次按片顺序跑（字典序），可随时 kill 后靠 gates 续跑。
   * **双卡（旧机）**：A100-PCIE 拓扑下**双实例独立并行**吞吐最高。
     N 镜分 ⌈N/2⌉+⌊N/2⌋，挂钟由跑得多的那张卡决定，另一张提前空闲属正常。
   * **通用铁律**：**一镜拆不到两卡上**。多卡只加吞吐，**单镜耗时不变（558 s）**。
     换算律：**双卡报告的「GPU 总机时」= 单卡「挂钟」**（实测加速比 1.950×）。
3. **点火前必查 `/queue`**，两端口队列都空才开跑（`run_one_step_dual.sh` 已内置该校验）。
4. **显存高 ≠ 在忙**：ComfyUI 跑完不自动释放，**空闲也常驻 ~57 GB 内存**。
   内存告警时先查 `/queue`，**卸/停空闲实例比加 swap 更有效**；但卸权重要付冷启代价（热态 4–5 倍）。
   * 双卡：两个实例共吃 ~115 GB，近期要用就别卸
   * 单卡：只有一个实例，内存余量充足，空闲时卸掉即可（下次冷启约 820 s）
5. **批量任务监控**：
   * `cat /workspace/trilogy/run_*.log`、`/workspace/dy_key/P{A,B}.log`
   * `ls /workspace/trilogy/gates_one/*.done`、`ls /workspace/dy_key/gates/*.done`
6. **swap 8 G + `vm.swappiness=10`**（`/swapfile`，已写 `/etc/fstab` 与 `/etc/sysctl.d/99-swap.conf`）。
   它是**兜底防 OOM kill，不是扩内存**——真开始用 swap 会慢到像卡死。
7. **BBR 已持久化**（`/etc/sysctl.d/99-net-speed.conf`）。回传慢的判据：
   `ss -tnpi state established "( sport = :22 )"` 看 `cwnd` 个位数 + `retrans` 上千 = 丢包型限速，
   开 BBR 即解（0.11 → 6 MB/s，约 50 倍）。

---

## 6. 会静默毁结果的坑（速查）

| 坑 | 症状 / 正确做法 |
|---|---|
| `pkill -f <name>` | 会匹配到执行它的 ssh 命令行 → **自杀式断连**。排查用 `ps -eo pid,args` |
| shell 优先级 | `cd X && A & B &` 里 B 跑在**原 cwd** → 后台提交一律绝对路径 |
| 后台任务缺 `< /dev/null` | ssh 断开会把任务带走 |
| `SaveVideo.format/codec` | 是 `COMFY_DYNAMICCOMBO_V3`，API 提交时白名单不认 → 参数消失，**跑完才报** `missing 'format'`。一律用 `MiniMaxH3SafeAVSaveT8Advanced` |
| API 工作流顶层 `_meta` | 报 `missing_node_type: ID #_meta`。`submit_api.py` 会自动剥离 |
| `s2_adapt.py` | 只吃 **API** 格式（直喂 UI 会静默不改造 + 谎报"已适配"）。链路：`官方UI → ui_to_api → raw.api → s2_adapt(A/B/C+identity) → tpl.api → s2_adapt(--shot/--draft)`。**该链路现已停用** |
| 清队列 | 用 `POST /queue {"clear":true}` + `POST /interrupt`，**别用 pkill** |
| H3 `length` 栅格 | 只接受 **17n+5**（向上吸附）。一步直出不经 LTX trim，成片 = H3 帧数 ÷ 24，`duration` 必须存 H3 值，**禁止填任意秒数** |
| 字幕绝对时间 | = **Σ 前序镜实际时长**，不是 (镜号−1)×单镜时长 |
| 单卡选 64 GB 内存机型 | 40 G 卡装不下 50.2 GB 权重 → 必然 offload 到内存；单个空闲实例就吃 57 GB → 跑一半 OOM。**单卡门槛 ≥ 96 GB** |
| 原版 `pipeline_worker.sh` 失败镜无限重试 | FAIL 后释放 lock，下轮又领到同一个镜 → **死循环烧机时**。单卡长跑必现。归档版已加 `.fail` 标记（失败即跳过，删掉才重跑） |
| 门禁残留 `.lock` 目录 | 双卡 worker 被 kill 留下 → 该镜被**永久跳过**且不报错。接手前 `find gates* -name '*.lock' -exec rmdir {} \;` |

---

## 7. 相关文档索引

| 文档 | 内容 |
|---|---|
| `docs/新服务器部署手册.html` | **换机迁移权威手册**：硬要求 / 完整清单 / 逐条命令 / 17 条坑位 / 验收 |
| **`docs/单卡A100部署手册.html`** | **单卡版权威手册**：卡数对照 / 内存门槛 / 单卡跑批 / 时间账推导 / 单卡坑位 10 条 |
| `deploy/README.md` + `deploy/bootstrap/` | 可执行版迁移包（7 个脚本：体检 / 系统 / 栈 / 权重 / 启动 / 推送 / 验收，单卡双卡通用） |
| `deploy/single-gpu/` | 单卡跑批脚本 + 接手检查清单（门禁脏状态清理） |
| `docs/h3-acceleration-2xa100.md` | 加速路线盘点与双 A100 是否更快 |
| `docs/h3-1080p-quality-research.md` | 分辨率与画质路径 |
| `h3-films/A100优化执行清单.md` | 计时口径与有效杠杆 |
| `待生成_现代婚姻三部曲/AGENTS.md` | 生产规则、剧本硬标准（§零）、栅格（§二）、坑位（§八） |
