# deploy/ — 换服务器重新部署的总入口

> **这份文件就是给"下一个拿到这个仓库的人/Agent"看的。** 读完它 + 跑完 `bootstrap/` 里的脚本，
> 就能在一台全新的 GPU 服务器上把整条 MiniMax-H3 短剧生产线跑起来。
>
> 配套的详尽版：`docs/新服务器部署手册.html`（含背景、实测基准、血泪坑位）
>
> **`server-assets/` 的完整性已核对**：1413 个受管文件逐文件 md5 比对，
> 0 漏拉 / 0 损坏，唯一 4 处差异是有意修复 → 见 **[`VERIFY_2026-09-19.md`](VERIFY_2026-09-19.md)**

---

## 0. 一句话说清这套东西是什么

本机 macOS 只做**编排 + 后处理**，真正的视频生成跑在远端 GPU 服务器上（旧机叫 `kehu`，
2×A100-PCIE-40GB）。本仓库里存的是**剧本 / 工作流 json / 编排脚本 / 运行脚本**，
GPU 服务器上存的是 **ComfyUI + 权重 + 生产脚本 + 输入资产**。

换服务器 = 把「GPU 侧那一半」重建一遍。本目录就是这一半的完整快照 + 重建剧本。

**当前生产形态（重要）**：**一步直出 768×1344**，不经 LTX 精修。
历史上的两阶段（H3 草稿 384×672 → LTX 精修）**已废弃**——
它依赖的 `/root/ui_to_api.py` 和 `/workspace/films/s2_adapt.py` 在旧机上已不存在，
`/workspace/trilogy/run_server.sh`（两阶段脚本）是**dead code，不要照着跑**。

**三条在跑的生产线**：

| 产线 | 工作流 | 规模 | 资源引用 |
|---|---|---|---|
| 现代婚姻三部曲 | `trilogy/wf_one/` | 24 镜 | TTS 干声 `tts_dry/trilogy/` |
| 抖音关键镜 / 骨架 | `dy_key/wf/` | 39 镜 | 干声 `dy_voice/` + 参考图 `dy_refs/` |
| **抖音全量复刻** | **`dy_key/wf_full/`** | **373 镜** | **原片音轨切片 `dy_full_a/` + 原片关键帧 `dy_full_ref/`** |

> ★ 全量复刻线的三个关键设计（2026-09-19 定）：
> ① 音频用**原片该镜的音轨切片**（不是 TTS）→ 音色/环境音/口型天然对；
> ② 参考图用**原片该镜的关键帧**（已 crop 底部 10% 防把原片字幕带进新片）；
> ③ `length` = 原片镜长**向上吸附 17n+5**（22–175 帧，均值 90），不再一律 354 帧
> → 373 镜 GPU 总机时 6.57 h，双卡挂钟约 3.37 h。

---

> ### ★★ 卡数：现行形态是「只租 1 张 A100」
>
> 单卡的**部署步骤与本文件完全一致**（`bootstrap/` 的 7 个脚本与卡数无关），
> 但 **启动方式 / 跑批脚本 / 内存门槛 / 时间账** 都不同 ——
> 单卡请配套读 **`deploy/single-gpu/README.md`** 与 **`docs/单卡A100部署手册.html`**。
>
> 两者关系一句话：**单卡只影响「排队长度」，不影响「单镜速度」** ——
> 每一镜本身的 9 分 18 秒（558 s）与卡数无关，373 镜从 3.4 h 变成 6.6 h 而已。
>
> ⚠ 本文件 §5 的跑批命令是**双卡口径**。单卡照抄会只用上 GPU0，**另一张卡白付租金**。

---

## 1. 目标机硬要求（不满足就别开）

| 项 | 要求 | 为什么 |
|---|---|---|
| GPU | ≥1 张，**compute capability ≥ 7.5**（本项目基准是 SM80 / A100） | CUDA13 / INT8 量化权重需要 |
| 显存 | **≥ 21 GB/卡**（基准 40 GB） | 瓶颈是 50.2 GB 权重的前向计算分片，不是激活值 |
| 卡数 | **1 张即可**（现行形态）。2 张 = 吞吐 ×1.950，单镜不快 | 一镜拆不到两卡。**单卡请配合 `deploy/single-gpu/` 使用** |
| 内存 | **单卡 ≥ 96 GB** / 双卡 ≥ 100 GB（基准 125 GB） | ★ 空闲 ComfyUI 常驻 ~57 GB **每个实例**，别选 64 GB 机型 |
| 磁盘 | **≥ 150 GB**（旧机 148 GB 用掉 104 GB） | 权重 71 GB + ComfyUI/venv 8 GB + 输出 |
| 驱动 | **≥ 580**（基准 580.95.05） | torch cu130 自带 CUDA 13 运行时，系统不用装 CUDA Toolkit |
| OS | Ubuntu 22.04（基准） | 脚本按 apt 写 |
| 网络 | 能直连 HuggingFace | 旧机在泰国机房，ModelScope 实测 9 B/s 等于不通 |

**注意**：A100 是 SM80，**没有原生 FP8**。所以 SageAttention / FP8 权重 / `--fast`
这些加速路线在本项目全部实测无效或 NaN。详见 `docs/h3-acceleration-2xa100.md`。

---

## 2. 两条恢复路径

### 路径 A · 旧服务器还在 → 整盘 rsync（最快，20 分钟）

权重占 71 GB，重下一遍要好几个小时。只要旧机器还活着，**优先整盘搬**：

```bash
# 在新机上执行（新机需能 ssh 到旧机，或反过来在新机拉）
rsync -avzP --info=progress2 root@旧机:/workspace/  /workspace/
rsync -avzP root@旧机:/root/s2/ /root/s2/
rsync -avzP root@旧机:/etc/sysctl.d/99-net-speed.conf root@旧机:/etc/sysctl.d/99-swap.conf /etc/sysctl.d/

# 整盘搬完必须做的两件事：
#   1) 删掉旧机残留的实例 B 数据库锁（否则 8189 起不来）
rm -f /workspace/instance_b.db.lock /workspace/ComfyUI/user/comfyui.db.lock
#      ★ 单卡形态：连 instance_b.db 本体一起删掉，单卡不需要它
rm -f /workspace/instance_b.db
#   2) 重新装 venv（venv 里写死了绝对路径，跨机搬过来基本是坏的，别偷懒）
mv /workspace/venv /workspace/venv.broken && bash deploy/bootstrap/02_build_stack.sh
```

### 路径 B · 旧服务器已关 → 从零重建（3~6 小时，大头是下权重）

```bash
# 新机上
bash deploy/bootstrap/00_check_target.sh     # 体检，只读
bash deploy/bootstrap/01_provision_os.sh     # 系统层：apt / swap / BBR
bash deploy/bootstrap/02_build_stack.sh      # venv + torch + ComfyUI + 3 节点
bash deploy/bootstrap/03_dl_weights.sh       # 71 GB 权重（最慢的一步，可 tmux 挂着睡一觉）
bash deploy/bootstrap/04_launch_comfy.sh both

# 回到本机（GitHub 上 clone 本仓库后）
bash deploy/bootstrap/05_push_assets.sh <新机别名>
# 目标机上
bash deploy/bootstrap/verify.sh --run
```

---

## 3. 清单：到底要搬哪些东西

### 3.1 软件（全部可公开获取，**必须锁 commit**）

| 组件 | 仓库 | 锁定 commit | 备注 |
|---|---|---|---|
| ComfyUI | github.com/comfyanonymous/ComfyUI | `ee71d5c4993f29086b27fde1629a945ae48425bf` | **v0.36.0**（2026-09-15）。升级到 v0.36.0 带来单步采样 −28%，是本项目已落地的最大单项收益 |
| T8 节点 | github.com/T8mars/comfyui-minimax-h3-audio-T8 | `e12d8af8ac85540da9895cb629836a4947e221ca` | v1.79.6。**H3 全部业务节点都在这里** |
| KJNodes | github.com/kijai/ComfyUI-KJNodes | `b3ec064dde7d122b333660918e1200e928e67ff1` | 提供 `PathchSageAttentionKJ` 等；依赖 color-matcher |
| TeaCache | github.com/Icyoung/ComfyUI-MiniMaxH3-TeaCache | `4cbb50d69c73a19a5d6ec42c5aec1989d5a04b6f` | **装了但禁用**，见 §4 坑位 5。留着仅为对照 |

| 依赖 | 版本 | 备注 |
|---|---|---|
| torch / torchvision / torchaudio | `2.14.0+cu130` / `0.29.0+cu130` / `2.11.0+cu130` | **必须走 `--index-url https://download.pytorch.org/whl/cu130`** |
| comfy-kitchen | **`0.2.34`** | ★ 必须 ≥0.2.34，内建 H3 专用融合算子（`group_norm_silu_pad3d` / `rms_rope_split_half`） |
| comfyui-frontend-package | `1.52.7` | 与 v0.36.0 匹配 |
| comfyui-workflow-templates | `0.11.62` | |
| av | `17.1.0` | |
| 系统 | `ffmpeg` / `aria2c` / `sqlite3` | ffmpeg **必须有**，T8 存 H.264 长视频依赖它 |

完整 120 个包的锁定版本：目标机上跑 `02_build_stack.sh` 会生成 `/workspace/pip-freeze-lock.txt`。

### 3.2 权重（6 个，约 71 GB，**文件名不能改**）

| # | 落盘路径（相对 `ComfyUI/models/`） | 大小 | 来源 | 用途 |
|---|---|---|---|---|
| 1 | `diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors` | 19.5 GiB | [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3) | 主干 · 无参考音/静音轮 |
| 2 | `diffusion_models/Minimax-h3_Singularity_ref2va_Pruned_v1.3_int8.safetensors` | 19.5 GiB | [WarmBloodAban/Minimax-h3_Singularity](https://huggingface.co/WarmBloodAban/Minimax-h3_Singularity) | 主干 · 参考图/原声锁轮 |
| 3 | `text_encoders/minimax_h3/qwen3vl_32b_minimax_h3_int8_convrot.safetensors` | 25.3 GiB | Comfy-Org/MiniMax-H3 | **★注意子目录** |
| 4 | `vae/minimax_h3_video_vae_fp16.safetensors` | 4.85 GiB | Comfy-Org/MiniMax-H3 | |
| 5 | `vae/minimax_h3_audio_vae_fp32.safetensors` | 577 MiB | Comfy-Org/MiniMax-H3 | |
| 6 | `loras/minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors` | 592 MiB | [drbaph/MiniMax-H3-Turbo-Lora-ComfyUI](https://huggingface.co/drbaph/MiniMax-H3-Turbo-Lora-ComfyUI) | 4 步加速 LoRA |

> 工作流 json 里**写死了这 6 个文件路径**。改名 → ComfyUI 直接 400 `value_not_in_list`。

### 3.3 服务器侧自制脚本（本目录已存档，`server-assets/`）

| 文件 | 作用 |
|---|---|
| `root/s2/submit_api.py` | **提交器**。只吃 API 格式工作流，主动剥离顶层非节点键（`_meta` 会让 /prompt 400） |
| `trilogy/run_one_step_dual.sh` | 双卡一步直出跑批（现行主力）：队列空校验 → 轮转分 keys → 双 worker |
| `trilogy/run_one_step.sh` | 单卡一步直出 |
| `trilogy/convert_to_pipeline_wf.py` | UI 工作流 → 管线格式（**会插 TeaCache，现不用**） |
| `dy_key/run_worker.sh` | 按 key 列表单卡顺序提交 + gates 断点续跑 |
| `dy_key/pipeline_worker.sh` | 目录扫描式：每卡一个 worker 抢 `wf/` 下未完成镜，`mkdir` 原子锁防抢。支持 `WF_DIR`/`GATE_DIR` 切产线；**已加 `.fail` 标记**（修失败镜无限重试） |
| `single-gpu/run_dy_single.sh` | **单卡跑批**（抖音 `full` / `key` 两条线）。内置队列预检、残留 `lock` 自动清理、有别的 worker 在跑时拒绝启动 |
| `single-gpu/run_trilogy_single.sh` | **单卡跑批**（三部曲 24 镜）。单 worker，不切分 keys |
| `dy_key/tryA.sh` `dy_key/tryB.sh` | 全量复刻试跑 6 镜（A: dy1_s001/s002/s070 · B: dy2_s001/dy3_s001/dy3_s100）。当时因为 `pipeline_worker.sh` 写死 `wf/` 才临时写的，现在可直接用 `WF_DIR` |
| `dl/build_env.sh` `dl/build_env2.sh` | 旧机环境重建脚本（**已过时，用 `bootstrap/02`**） |
| `install_sage.sh` `install_sage2.sh` | SageAttention 编译（SM80 无 FP8，**最终未采用**） |
| `sysctl.d/99-net-speed.conf` | BBR + 16 MB 收发缓冲 |
| `sysctl.d/99-swap.conf` | `vm.swappiness=10` |

### 3.4 输入资产（`server-assets/inputs/`，**不在 git 里**，必须手动传）

这些是 `*.wav` / `*.jpg`，被仓库 `.gitignore` 拦掉了（媒体一律不入库），但**生产必需**：

| 目录 | 内容 | 工作流里的引用形式 |
|---|---|---|
| `inputs/tts_dry/trilogy/` | 三部曲 24 镜中文干声（15 MB） | `LoadAudio.audio = "tts_dry/trilogy/f1_s01_dry.wav"` |
| `inputs/dy_voice/` | 抖音关键镜 31 条干声（14 MB） | `"dy_voice/dy1_s01_open_kick.wav"` |
| `inputs/dy_refs/` | 9 张角色/产品参考图（132 KB） | `LoadImage.image = "dy_refs/product_pouch.jpg"` |
| **`inputs/dy_full_a/`** | **全量复刻 373 条原片逐镜音轨切片（32 MB）** | `"dy_full_a/dy1_s001.wav"` |
| **`inputs/dy_full_ref/`** | **全量复刻 373 张原片关键帧（31 MB，已裁底部 10% 防带字幕）** | `"dy_full_ref/dy1_s001.jpg"` |
| **`inputs/dy4_{ref,first,last,voice}/`** | **2026-09-19 试点 4 条单元的首尾帧 / 参考图 / 干声（各 4 个，共 2.1 MB）** | `"dy4_voice/dy4_u007_stomp.wav"`、`"dy4_ref\|dy4_first\|dy4_last/dy4_u007_stomp.jpg"` |
| `inputs/dy_full_{first,last}{4,5}/`、`ref_v5/` | 参考帧抽检样本（26 张，5.3 MB），供新机复现清洗判据 | 不直接引用 |
| `inputs/silent_15s.wav` | 15 秒静音垫（472 KB），纯审画面的轮次挂它 | `"silent_15s.wav"` |

> ★ **`dy4_*` 是「正在用」的资产**：`videos/douyin_refs/2026-09-19/_remake/wf/wf_dy4_*.json`
> 直接引用它们，缺了这 4 条试点单元在新机上一条都跑不起来。

> 传到目标机的 `ComfyUI/input/` 下，**目录层级必须一致**（工作流用的是相对路径）。
> 三部曲干声本机无副本（只在旧服务器上），已抢救到 `inputs/tts_dry/`，**这是唯一的备份，别丢**。
> 需要重生成时用 `待生成_现代婚姻三部曲/_pipeline/tts_dry.py`。

### 3.5 历史状态快照（`server-assets/state/`，★ 只留档，**不要推到新机**）

旧机关停前抓下来的门禁与 worker 现场，用来回答「上次跑到哪了」：

| 路径 | 内容 | 读出来的事实 |
|---|---|---|
| `state/dy_key/gates/` | 39 个 `.done` | 关键镜/骨架 39 个全部完成 |
| `state/dy_key/gates_full/` | 12 个 `.done` | ★ **373 镜全量真实进度只有 12/373，其余 361 镜从未开始** |
| `state/dy_key/gates_full/*.lock/` | `dy1_s009`、`dy1_s010` | ★ **lock 残留 → 这 2 镜会被永久静默跳过**，接手前先 `find gates* -maxdepth 1 -type d -name '*.lock' -exec rmdir {} \;` |
| `state/trilogy/gates_one/` | 2 个 `.done` | 三部曲 24 镜只跑了 f1s01/f1s02 |
| `state/dy_key/full_worker.sh` | 28 行 | 373 镜专用 worker；功能已被 `pipeline_worker.sh` 的 `WF_DIR`/`GATE_DIR` 覆盖 |

> **为什么刻意不推**：新机上没有对应成片，把 `.done` 推过去会让这些镜被误判为「已完成」而永久跳过。
> 要续跑就让它从干净状态重跑；要接着旧机进度，**必须先搬 `output/` 成片、再搬 gates**，顺序反了会丢镜。

---

## 4. 血泪坑位（照抄旧脚本会踩的）

1. **旧 `build_env.sh` 里的 `COMFY_COMMIT=f42b24e` 是 0.35 的旧值**。用它装出来是 v0.35，
   少 28% 采样速度。现行是 **v0.36.0 `ee71d5c4`**。
2. **`requirements_headless.txt` 里写的是 `comfy-kitchen==0.2.33`**。必须改 **0.2.34**，
   否则 H3 的融合算子缺失（`group_norm_silu_pad3d` 等），速度掉回旧水平。
3. **旧 `launch_comfy.sh` 的 `start_one()` 漏了 `--database-url`**。双实例同开会
   `Database is locked`，任务批量失败。8189 必须带
   `--database-url sqlite:////workspace/instance_b.db`（**四个斜杠**）。
4. **两阶段流程已死**。`run_server.sh` 引用的 `/root/ui_to_api.py`、`/workspace/films/s2_adapt.py`
   在旧机上已不存在。别照跑，别去"修复"它。
5. **TeaCache 装了但禁用**（2026-09-19 决定）。4 步采样下尾段有拖影/涂抹。
   `wf_one/` 里 0 个 TeaCache 节点，`wf_pipeline/` 里 25 个（已废弃）。
   **不要往 wf_one 里加 TeaCache**。
6. **后台任务必须 `setsid nohup ... > log 2>&1 < /dev/null &`**。少一个 stdin 重定向，
   ssh 断开会把任务带走。
7. **`pkill -f "ComfyUI/main.py"` 会自杀式断连**——那条命令行本身会被 `-f` 匹配到。
   清队列用 `POST /queue {"clear":true}` + `POST /interrupt`，杀进程用 `ps -eo pid,args` 精确定位。
8. **`POST /free` 返回 200 但响应体是 0 字节**。别对它 `json.loads()`。
9. **显存高 ≠ 在忙**。ComfyUI 跑完不自动释放，空闲实例也常驻 ~57 GB 内存。
   点火前必查 `/queue` 并主动 `/free`。
10. **回传慢不是带宽问题，是跨境丢包**。判据：
    `ss -tnpi state established "( sport = :22 )"` 看 `cwnd` 个位数 + `retrans` 上千 → 开 BBR。
    旧机实测 0.11 → 6 MB/s（约 50 倍）。
11. **权重路径带子目录**：Text Encoder 必须在 `text_encoders/minimax_h3/`，放错根目录 → 400。
12. **`SaveVideo.format/codec` 是 `COMFY_DYNAMICCOMBO_V3`**，API 提交时白名单不认，
    参数会消失，跑完才报 `missing 'format'`。本项目一律用 `MiniMaxH3SafeAVSaveT8Advanced`。
13. **shell 优先级**：`cd X && A & B &` 里 **B 跑在原 cwd**。后台提交一律用绝对路径。
14. **A100 冷启 = 热态 4~5 倍**（首镜 382 s → 热态 74 s）。这是全项目最大的记账陷阱，
    冷启只在一个批次的第一镜付一次，**绝不乘镜数**。
15. **一镜拆不到两卡**。双卡 = 吞吐翻倍，不是单镜提速。N 镜分布 ⌈N/2⌉ + ⌊N/2⌋，
    挂钟由跑得多的那张卡决定，另一张提前空闲属正常。
16. **★ 单卡时别选 64 GB 内存的机型**。单张 40 GB 卡装不下 50.2 GB 权重，必然 offload 到内存，
    旧机实测**单个空闲 ComfyUI 就常驻 57 GB**。内存不够会在跑到一半时 OOM，
    gates 断点虽能续跑，但已烧的机时白费。单卡门槛 **≥ 96 GB**（`00_check_target.sh` 会判定）。
17. **在双卡机器上跑单卡脚本 = 白付一半租金**。`04_launch_comfy.sh single` 只启 GPU0；
    双卡机器请用 `both` + 双 worker。反过来，单卡机器上起两个实例只会互相 OOM。
18. **失败镜会被无限重试**（原版 `pipeline_worker.sh`）。FAIL 后只写 `failed_*.txt` 并释放 lock，
    下一轮扫描又领到同一个镜 → 死循环烧机时。双卡时不易察觉，**单卡长跑会直接卡死**。
    归档版已加 `.fail` 标记（失败即跳过，删掉才重跑）——旧机上是老版本，要用就推过去覆盖。
19. **★ 系统 `http_proxy` 会劫持 localhost 检查**（2026-09-19 实测踩到）。
    只要环境里有 `http_proxy=http://127.0.0.1:xxxxx`（WorkBuddy / Clash / 公司代理都会设），
    `curl http://127.0.0.1:8188/system_stats` 就会**走代理**，拿到 `502` 或 `000`，
    于是所有检查脚本都报「ComfyUI 没响应」——**而 ComfyUI 其实跑得好好的**。
    症状极具误导性：你会去翻 ComfyUI 日志、查端口、反复重启实例，全都不解决问题。<br>
    **正确做法**：脚本开头 `export no_proxy="127.0.0.1,localhost,::1"`（大写 `NO_PROXY` 一起设）。
    `bootstrap/04`、`verify.sh`、两个 `single-gpu/run_*.sh`、
    `server-assets/trilogy/{run_one_step_dual,run_dual,resume}.sh` 都已内置；
    `resume.sh` 是远程执行，用的是前置赋值 `no_proxy=… curl …` 形式。<br>
    自查：`curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8188/system_stats`
    返回 502/000 但端口确实在监听 → 就是这个坑。
20. **变量后紧跟中文标点会炸 bash**。脚本以 `set -u` 运行时，
    `echo "端口 $PORT）"`（变量后紧跟全角括号）在非 UTF-8 locale 下会被当成变量名
    `PORT\xef\xbc\x89` → 报 `unbound variable`；若没开 `set -u` 则更糟——
    **静默展开成空串**，日志里少个字，很难看出来。写脚本时变量一律用 `${VAR}` 形式。

---

## 5. 起服务与跑批

### 启动

```bash
bash deploy/bootstrap/04_launch_comfy.sh single        # ★ 单卡机器：只起 GPU0→8188
bash deploy/bootstrap/04_launch_comfy.sh both          # 双卡：GPU0→8188, GPU1→8189
bash deploy/bootstrap/04_launch_comfy.sh status        # 看存活实例数 + 队列 + 显存
```

> `single` 与 `both` 的区别只有一处：**单卡只起一个进程，因此不需要 `--database-url`**
> （单进程独占 sqlite，不会 `Database is locked`）。这是双卡最常翻的车，单卡天然免疫。

等价的手写命令（**注意两个实例的差异**）：

```bash
# 实例 A · GPU0 · 8188
CUDA_VISIBLE_DEVICES=0 setsid nohup /workspace/venv/bin/python /workspace/ComfyUI/main.py \
  --listen 127.0.0.1 --port 8188 --vram-headroom 1 --use-ck-attention \
  > /workspace/logs/comfy_a.log 2>&1 < /dev/null &

# 实例 B · GPU1 · 8189（★ 独立 sqlite，四个斜杠）
CUDA_VISIBLE_DEVICES=1 setsid nohup /workspace/venv/bin/python /workspace/ComfyUI/main.py \
  --listen 127.0.0.1 --port 8189 --vram-headroom 1 --use-ck-attention \
  --database-url sqlite:////workspace/instance_b.db \
  > /workspace/logs/comfy_b.log 2>&1 < /dev/null &
```

`--use-ck-attention` = 走 comfy-kitchen 的 INT8 注意力（A100 上唯一有效的注意力加速）。
`--vram-headroom 1` = 动态显存多留 1 GB 余量。

### 任务形态 · 双卡口径

> ⚠ 下表是**双卡**命令。只租一张卡请看下面的「单卡口径」。

| 任务 | 命令（目标机） | 说明 |
|---|---|---|
| 三部曲 24 镜一步直出 | `cd /workspace/trilogy && bash run_one_step_dual.sh` | gates 断点续跑；热态约 550 s/镜/卡，24 镜双卡 ≈1.5 h（不含首镜冷启） |
| 抖音关键镜 / 骨架 | `cd /workspace/dy_key && WF_DIR=$PWD/wf GATE_DIR=$PWD/gates bash pipeline_worker.sh A 8188 &`<br>`cd /workspace/dy_key && WF_DIR=$PWD/wf GATE_DIR=$PWD/gates bash pipeline_worker.sh B 8189 &` | 目录扫描式，原子锁防两卡抢镜 |
| **抖音全量复刻 373 镜** | `cd /workspace/dy_key && WF_DIR=$PWD/wf_full GATE_DIR=$PWD/gates_full bash pipeline_worker.sh A 8188 &`<br>`cd /workspace/dy_key && WF_DIR=$PWD/wf_full GATE_DIR=$PWD/gates_full bash pipeline_worker.sh B 8189 &` | **★ 用独立的 `gates_full`，别和关键镜的 gates 混**；373 镜双卡挂钟 ≈3.37 h |
| 单镜试拍 | `/workspace/venv/bin/python /root/s2/submit_api.py /workspace/trilogy/wf_one/wf_f1s01.json --host http://127.0.0.1:8188 --timeout 2400` | 冷启约 600 s |

> **`WF_DIR` / `GATE_DIR` 是 2026-09-19 新加的**。原版 `pipeline_worker.sh` 把 `wf/` 写死了，
> 跑全量复刻只能另写一个脚本（当时的 `tryA.sh` / `tryB.sh` 就是为此临时写的）。
> 归档里的版本已支持环境变量切换——**旧服务器上跑的还是老版本，需要时把它推过去覆盖**。

### 任务形态 · 单卡口径（★ 只租一张卡时用这个）

| 任务 | 命令（目标机） | 单卡挂钟 |
|---|---|---|
| **抖音全量 373 镜** | `cd /workspace/dy_key && setsid nohup bash run_dy_single.sh full > run_full.log 2>&1 < /dev/null &` | **≈6h34m** |
| 抖音关键镜 39 镜 | `cd /workspace/dy_key && setsid nohup bash run_dy_single.sh key > run_key.log 2>&1 < /dev/null &` | ≈5h15m |
| 三部曲 24 镜 | `cd /workspace/trilogy && setsid nohup bash run_trilogy_single.sh > run_single.log 2>&1 < /dev/null &` | ≈3h45m |
| 单镜试拍 | 同双卡（`submit_api.py … --host http://127.0.0.1:8188`） | 冷启 ≈820 s |

两个 `run_*_single.sh` 由 `05_push_assets.sh` 自动推到目标机，无需手工 scp。

**换算式（好记）**：双卡报告里的「**GPU 总机时**」= 单卡下的「**挂钟**」。
因为双卡 = 两卡合计的机时被摊到两条并行的线上。
实测依据：抖音关键镜 33 镜总机时 18908 s = 5h15m（双卡挂钟 2h35m，加速比 1.950×）。
完整推导与单卡专属坑位见 `single-gpu/README.md`。

### 回传成片（低带宽友好）

```bash
# 本机执行。★ 远端的 *.mp4 一律用 tar 分卷或直接 scp，不要走 git
scp -q kehu:/workspace/ComfyUI/output/dy_skel/'*.mp4' ./videos/douyin_refs/2026-09-18/_remake/out/
# 更省：远端先 ffmpeg 压成 720p 预览 mp4 再拉，只有终稿才拉全质量
ssh kehu 'cd /workspace/ComfyUI/output/dy_skel && for f in *.mp4; do ffmpeg -y -loglevel error -i "$f" -vf scale=-2:720 -crf 28 /tmp/prev_"$f"; done && tar cf /tmp/prev.tgz -C /tmp $(ls /tmp | grep "^prev_")'
```

---

## 6. 验收

```bash
bash deploy/bootstrap/verify.sh          # 静态检查：实例 / 权重 / 资源引用 / 节点 / ffmpeg
bash deploy/bootstrap/verify.sh --run    # 加真出一镜（约 10 分钟，含冷启）
```

全绿 = 链路通。然后按 §5 跑批。

---

## 7. 本机侧（macOS）要什么

| 需求 | 说明 |
|---|---|
| ssh 别名 | `~/.ssh/config` 里加 `Host kehu2 / HostName <ip> / User root / IdentityFile ~/.ssh/xxx.pem` |
| 私钥 | `~/.ssh/*.pem`（**仓库里出现过 `kehu-JiangLong.pem`，那是私钥，别提交**） |
| ⚠ 透明代理 | TUN 模式（Clash Verge 等）会把境外 IP 的 22 端口掐断，症状 `Connection closed by <IP> port 22`。放行写法与诊断：`~/.workbuddy/skills/ssh-tun-hijack-diagnosis/` |
| Python | 本机脚本（`_pipeline/*.py`）用系统 python3 即可，**不要**在本机装 torch |
| 剪辑 | 剪映专业版 11.4.0/11.4.2 + `repos/jianying-headless`（Apple Silicon） |

仓库里的 5 个 submodule 与本部署**无关**（hypit / FastVideo / jianying-headless / reelbench-skills / TaoMate-H3）：
它们是本机编排与剪辑侧的工具，GPU 服务器上不需要。clone 时加 `--recurse-submodules` 只为本机使用。

---

## 8. 目录速查（目标机最终形态）

```
/workspace/
├── ComfyUI/                    # v0.36.0 (ee71d5c4)
│   ├── custom_nodes/
│   │   ├── comfyui-minimax-h3-audio-T8/       e12d8af8  ← H3 业务节点
│   │   ├── ComfyUI-KJNodes/                   b3ec064d
│   │   └── ComfyUI-MiniMaxH3-TeaCache/        4cbb50d6  ← 装了不用
│   ├── models/{diffusion_models,text_encoders/minimax_h3,vae,loras}/   ← 71 GB / 6 个文件
│   ├── input/                  ← 输入资产
│   │   ├── tts_dry/trilogy/    (24)  三部曲干声
│   │   ├── dy_voice/           (31)  抖音关键镜干声
│   │   ├── dy_refs/            ( 9)  角色/产品参考图
│   │   ├── dy_full_a/          (373) 全量复刻·原片音轨切片
│   │   ├── dy_full_ref/        (373) 全量复刻·原片关键帧  ★ 现行版（_v3 是历史迭代，别用）
│   │   ├── dy4_{first,last,ref,voice}/ (各 4) 2026-09-19 试点首尾帧/参考/干声
│   │   ├── dy_full_{first,last}{4,5}/ · dy_full_ref_v5/  参考帧抽检样本
│   │   └── silent_15s.wav            静音垫
│   └── output/{dy_key,dy_skel,dy_full,MiniMaxH3/trilogy_one}/
├── venv/                       # python 3.10.12 · torch 2.14.0+cu130
├── trilogy/                    # 三部曲：wf_one/ (24) · wf_pipeline/ (25 废弃)
│                               #   run_one_step_dual.sh(双卡) · run_trilogy_single.sh(单卡)
├── dy_key/                     # 抖音：wf/ (39) · wf_full/ (373) · gates/ gates_full/
│                               #   pipeline_worker.sh · run_worker.sh · run_dy_single.sh(单卡)
├── dl/                         # 环境重建脚本（留档）· launch_comfy.sh
├── logs/                       # 单卡 comfy_single.log ／ 双卡 comfy_a.log + comfy_b.log
├── instance_b.db               # ★ 仅双卡需要；单卡不要建
└── pip-freeze-lock.txt         # 120 个包的确切版本
/root/s2/submit_api.py          # 提交器
/etc/sysctl.d/99-net-speed.conf # BBR
/etc/sysctl.d/99-swap.conf      # swappiness=10
/swapfile                       # 8 GB
```
