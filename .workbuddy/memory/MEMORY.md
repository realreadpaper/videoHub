# videoHub 项目长期记忆

> ★ **完整判据在 `DETAIL.md`**（本文件是索引，别堆细节）。
> 生产规则 → `待生成_现代婚姻三部曲/AGENTS.md`（§零 硬标准 / §二 栅格 / §八 坑位 17 条）。
> 技能：出片 `h3-key-shot-batch` / 拆解·下载·验收 `video-breakdown`·`douyin-download`·`acceptance-doc`。
> 文档：换机 `deploy/README.md` + `docs/{新服务器,单卡A100}部署手册.html` ·
> 流程与加速 `docs/H3生成流程与加速白皮书.html` · ★ 实测成本 `docs/H3实测成本模型与优化清单.html`。
> ⚠ 工程里残留 `/Users/hejianglong/...` 旧机路径（本机 `jianglong`）→ file not found。

## 当前状态（2026-09-19）

★★ **新机 `gpu1` 已全套部署就绪**（2026-09-19 深夜）—— 这是 kehu 的接替机，**单卡形态**：
`ssh gpu1` → `36.213.79.171:31233`（国内 KVM 直通 1×A100-PCIE-40G，hostname `app-01b4048b9ba820db`）。
8 核 / **62 GB 内存 + 40 GB swap** / 196 GB 盘 / Ubuntu 24.04 / 驱动 580.178.04。
已装齐：torch 2.14.0+cu130（CUDA 13.0）、ComfyUI v0.36.0 + T8/KJNodes/TeaCache、**71 GB 权重**、
104 MB 生产资产（wf_full 374 / 音轨切片 373 / 参考帧 373）。跑批走 `deploy/single-gpu/run_dy_single.sh`。
★ **内存 62 GB 低于单卡门槛 96 GB**（旧机实测空闲实例常驻 57 GB）→ 只能靠 swap 兜底，跑批必须盯 `free`。

373 镜复刻 = `videos/douyin_refs/2026-09-18/_remake/`。★ **全量进度仅 12/373**；关键镜 39/39 完成；三部曲跑了 f1s01/f2。
kehu 将关停；迁移包 `deploy/`（单卡版 `single-gpu/`）**已 md5 核对：1413 文件 0 漏拉 0 损坏**。
★★ **旧机全部产出已回传** → `videos/douyin_refs/_server_pull_2026-09-19/`（**2794 文件 / 1.65 GiB，md5 全通过**）：
115 成片（18 批次）+ 帧/音频素材 + 日志与门禁 + 全部工作流 JSON + `MANIFEST.tsv`。
★ 参考帧已换 `_v6`（`rebuild_ref.py` 重抽重洗）。★ 待办：**模型幻觉字幕**（dy3_s145 / dy2_s118，参考帧干净仍烧）。

## ★★★ 剧本硬标准（用户：「以后的剧本都要这么要求」）

**S1 零字幕**（无 `<d>` + `strict_output_constraints` + 文字道具 `illegible`）· **S2 表情**（微表情 ≥3、情绪过渡 ≥1）·
**S3 位置逻辑**（多人镜方位锚点 ≥1、单人镜朝向锚点 ≥1）· **S4 技术对齐**（末段时间戳 = scene_duration）。
三关：`_pipeline/review_v3.py` 扫 → 试拍目视 → 写回 AGENTS.md。★ 扫描只查「有没有写」，**好坏必须目视**。
`<d>[Chinese]"…"</d>` 同时驱动口型**与**字幕 → **彻底剥离**；干声定口型，神态全由 prompt 定。

## ★★ 实测铁律（2026-09-19，详见成本清单）

1. ★★ **124 帧（5.167 s）渲染地板**：`ensure_minimum_context=True` 把短镜补齐到 `MIN_TRAINED_FRAMES=124` 再渲、成片裁回
   → **地板以下同价**。373 镜 **93.3 % 在地板下**，付费帧 = 需要的 **1.94 倍**。
   → **「切短更便宜」是错的**（39 帧 67.7 s/镜秒 vs 345 帧 38.5 s/镜秒，**长镜更划算**）；实测 22–90 帧全部 110.1 s。
   ★ 切分单位仍是**台词句**（1 句 = 1 单元，`build_units.py`）；1.6s 短单元**不可合并**（金句是命门）。
2. **步数线性计价、非质量杠杆**：21.3 s/步（4/6/8/12 = 140/180/230/310 s）→ **保持 4 步**（全量线 = 单图 + 4 步）。
3. **参考图张数是第二大计价项**：1 张 110.1 s / 2 张 130.2 s / 3 张 145.0 s → 全量线用 1 张是对的。
4. ★★ **参考帧必须零文字**（模型会原样画进成片）；用**平移贴补**而非 inpaint（横带会被语义补全成字幕）。
5. **关键镜提示词必须人工写**；**角色与关系要显式写进 `<Characters and their relationship>` 段**。

## ★ 成本 / 排期 / 度量

373 镜真实 GPU 机时 ≈ **14 h**（双卡 ≈7 h / 单卡 ≈14 h）；★ 部署文档的 6.57 h **低估 ×2.1**（漏算地板补齐）。
★ `cost(N)` 的 **N 必须用「实渲帧数」= max(请求, 124) 再吸附 17n+5**。
★ **worker 日志的「用时」含排队**，不能做加速对比（S6 的 410.5 s 里 230 s 在排队）。

## 环境与坑（明细见 DETAIL.md / AGENTS.md §八）

- ★★ **现行服务器 `gpu1` = `36.213.79.171:31233`**（国内，1×A100-40G，62 GB 内存 + 40 GB swap，Ubuntu 24.04）。
  单卡只起 `:8188`、**不要 `--database-url`**，跑批用 `deploy/single-gpu/run_dy_single.sh`。
  ★ 国内机四件套：apt 现测选最快镜像 / pip 国内源 / **HF 必须 `HF_ENDPOINT=hf-mirror.com`** /
  **torch wheel 走交大镜像**（`mirror.sjtu.edu.cn/pytorch-wheels/cu130`，实测 **40.3 MB/s** vs 官方 4.6）。
  ★ **GitHub 直连仅 0.045 MB/s** → ComfyUI/节点必须本机代理拉好再 `scp`。
  ★ macOS 自带 rsync 是 openrsync 2.6.9、**无 `--info=stats2`**（`05_push_assets.sh` 已做能力探测）。
  ★ 部署脚本新增 `01c_gpu_driver.sh`（装驱动，01 只核对不装）；`02` 支持 `TORCH_INDEX=` 与 `SKIP_VENV=1`。
- 旧机 `kehu` 124.81.178.140（**已决定关停**），2×A100-40G / 125 GB / 华为云泰国；★ **连不上先怀疑本机 Clash TUN** → 技能 `ssh-tun-hijack-diagnosis`。
  双卡 = `:8188`/`:8189`（b 需 `--database-url …instance_b.db`）；单卡只起 `:8188`、**不要 database-url**。
  启动 `--vram-headroom 1 --use-ck-attention` + `setsid nohup … < /dev/null &`。★ 内存病根 = 空闲实例白吃 57 G → 先查 `/queue`。
  ★ 回传慢 = 跨境丢包，开 BBR 即解。★ 服务器共享，动队列前先看是不是自己的活。★ **A100 冷启 = 热态 4–5 倍**。
- ★ **`http_proxy` 劫持 localhost** → `curl 127.0.0.1:8188` 拿 502；解法 `no_proxy="127.0.0.1,localhost,::1"`（下载权重脚本别加）。
- ★ **`pkill -f <name>` 会匹配执行它的 ssh 命令行 → 自杀式断连**；用 `ps -eo pid,args | grep "[x]xx"`。
- ★ **门禁 `.lock` 残留 → 该镜永久跳过**；接手前 `find gates* -maxdepth 1 -type d -name '*.lock' -exec rmdir {} \;`。
- zsh 不做单词切分（用 `${=VAR}`）；`cd X && A & B &` 里 **B 跑在原 cwd**。
- 加速 L0–L3 清单见白皮书 §四–七；★ 天花板：attention 占每步 62 %、A100 无 FP8 → 还能省 −12~−20 %。

## 交付铁律 & 画面风格

不烧字幕，外挂 srt/vtt 同名同目录 · 字幕绝对时间 = **Σ前序镜实际时长** · 产品镜用 `<Subject P>` 锚定、参考图 `<Picture N>`。
**禁「油腻」**：`matte finish` + `visible pores` + `neutral white balance` + `muted naturalistic colour`。
