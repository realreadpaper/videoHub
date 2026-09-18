# videoHub / h3-films 项目长期记忆

> 2026-09-18 精简重写（18.3KB → 本版），只留跨会话必用的判据与结论。
> 细节查：`~/.workbuddy/skills/h3-film-production/`（SKILL.md + 脚本）、
> `h3-films/分镜v2审查_对比v1.html`、`A100优化执行清单.md`、`.workbuddy/memory/2026-09-17.md`（全部原始实测数据）。

## 项目性质

自建 ComfyUI + MiniMax H3 两阶段管线（H3 草稿 384×672 → LTX-2.5 精修 768×1344）批量产 AI 短剧成片。
本机 macOS 只做编排/后处理，重活跑远端 GPU（当前 A100 40G）。工程目录 `~/Desktop/videoHub/h3-films/`。

## ★ 硬件门控（换卡判据 —— 不是显存容量）

四条硬约束（缺一不可行）：① CUDA 13 工具链 → **SM ≥ 7.5**；② INT8 tensor core → **SM ≥ 7.5**；
③ 原生 bf16 → **SM ≥ 8.0**；④ **显存 ≥ 21 GB**（UNET 20.97 GB 常驻）。
V100 32G（SM7.0）**不可行**；A100 40G 可跑但 CLIP 须换 `qwen3vl_32b_minimax_h3_int8_convrot`（27.14 GB）；
RTX 4090 48G（SM8.9）换卡首选（零改动，2.27 元/卡时 < A100 2.60）。自检 `scripts/check_gpu_compat.py`。
**RAM ≠ VRAM** —— RAM 只是 offload 中转站（64 GB 够），不会把「显存不够」变「够」。

## ★★ 计时口径（唯一权威表，混用会得出差 4 倍的工期）

| 口径 | 4090 24G | A100 40G | 说明 |
|---|---|---|---|
| S1 草稿 384×672 **热态** | 72.5 s | 73.9 / 74.3 s | 两卡同档 → **草稿这段卡不是变量** |
| S2 精修 768 **热态** | 90.6(估)/139.4 | 75.0 / 75.3 s | 两边配置不同，不当硬件结论 |
| **单镜 · 热态批处理** | 163 s | **149 s** | ★ **排期一律用这个** |
| 单镜 · 逐镜交替 | 248 s | — | 每镜多付一次权重装卸 |
| 单镜 · 两步各自冷启 | — | ≈624 s | 最差口径，**绝不能乘 20** |

- ★ **A100 冷启 vs 热态差 4–5 倍**（首镜 382 s → 热态 74 s）。**全项目最大的记账陷阱。**
- ★★ **两步走 vs 一步到位（全 768 直出）= 3.7 倍**：两步 `S1批 353+19×74.3` + `S2批 271.6+19×75.3`
  = 3 467 s = 0.96 h；一步到位 `冷启 826 + 19×631` = 12 815 s = 3.56 h。
  早前 2.5（跨卡相除）/3.5–4（含糊）/3.6 全部作废。
- 贵 3.7 倍的原因：① 像素 4× → 单步 **11×**（12.4→138.5 s，按 **N^1.76**）；② 一步到位从 sigma=1.0
  **全噪声**去噪，S2 只从 0.5 补细节；③ 最贵那步落在最重的模型上。
- **A100 20 镜排期 ≈ 76–78 min**。产品镜 ≈152 s ≈ 普通镜 149 s（**无例外**；早前"产品镜打平"是记账错误）。

## ★★ `length` 参数 —— v2 分镜的核心问题（2026-09-17 定论）

`MiniMaxH3AudioConditioningT8`(node 6) 的 `length`：**default 124 / min 5 / step 17**，
tooltip 原文 `"24fps; snapped up to the 17n+5 H3 grid"` → 栅格 **17n+5**：
5, 22, 39, 56, 73, 90, 107, 124, …, 345, **362**。
**三份模板与 `preview_flow.py` 都没设 length → 一律吃默认 362 帧满窗**（= Mode A）。
→ v2 两片生成 52 852 帧、进成片 13 993 帧 = **利用率 26.5%**，白扔约 27 min 素材。
→ **判据「窗口覆盖率」= 正片时长 ÷ 实际生成时长，>1.5 就是拿满窗钱买短镜内容**：
v1 1.01×（省来自镜少不是效率高）／ v2 Mode A **3.69×** ／ v2 Mode B 1.09×。

**短镜成本（实测 log-log 拟合，A100 热态）**：草稿 `t = 0.0243·n^1.362`、精修 `t = 0.050·n^1.243`
→ **每帧成本随时长上升**（0.137→0.177→0.202 s/帧）→ 短窗口更划算。
- 3.0 s 镜 = 73 帧 → **19 s**（vs 满窗 149 s，**快 8.0×**）
- 4.5 s 镜 = 107 帧 → **31 s**（快 4.8×）
- ★ 因 snap 到栅格，3s 实际 3.04s、4s 可上取 107 帧（4.46s）或下取 90 帧（3.75s），差 ≤0.7 s，剪辑忽略。

- ★★ **双重栅格（排期必用，2026-09-18 算平）**：H3 `length` ∈ **17n+5** 之后，
  LTX `MiniMaxH3SolEngineDraftToLTXT8Advanced.frame_policy` 默认 **`trim_to_8n_plus_1`**
  （A100 `/object_info` 核实，只裁不补、向下取 8m+1）→ **成片 = trim(H3帧)，不是 H3 帧**。
  10–15s 只有 8 个合法档：H3 帧 243/260/277/294/311/328/345/362 →
  成片 **10.042 / 10.708 / 11.375 / 12.042 / 12.708 / 13.375 / 14.375★ / 15.042** s。
  ★ **345 帧（14.375s）唯一双对齐无损**（裁 0 帧）；其余被裁 1–7 帧 = 0.042–0.292s。
  **禁止填任意秒数**（填 13.0 → 吸附 328 → 裁 321 = 实际 13.375s，字幕轴全错）。
  排期落地见 `~/.workbuddy/skills/` 之外：`~/Desktop/story/待生成_现代婚姻三部曲/_后期/retime_shots.py`。

**三档成本（两片合计）**：v1 1.66 h ／ Mode A **9.52 h** ／ Mode B **2.35–4.46 h** ／ Mode B+并碎切 2.04–3.59 h。
⚠ 区间两端 = 两个成本模型：① 贴实测幂律 → 2.35 h；② 线性保守 `25+49×(n/362)` → 4.46 h。
**两者都在 124 帧以下外推，单镜验证前按 4.46 h 排期。**
**Mode B 验证四问**（`STORYBOARD.md` 自规"验证前不得排期"）：① 短窗能否正常出片 ② 画质与 362 帧是否同档
③ `audio_mode=lock_source` 音轨是否仍对齐 ④ ★ LTX `frame_policy=trim_to_8n_plus_1` 把 90 裁成 **89 帧 = 3.708 s**
→ 字幕时间轴要跟着走（最易漏）。
- ★★ **实测校准（2026-09-18 从 A100 history 反推）**：v3run 一步直出 768×1344 = **平均 406 s/镜**
  （实测 328/341/341/388/448/501）→ 两阶段 ≈ **150 s/镜** → 24 镜 ≈ **60 分钟**。
  与账本里的 149 s/镜、60 min **独立吻合**。★ 注意两个比值别混用：
  **2.7×** = 纯热态单镜（一步直出 vs 两步走）；**3.7×** = 含冷启摊分的全片口径。
- ★ **启动前必查 `curl http://127.0.0.1:8188/queue` 的 `queue_running`** —— 曾撞上 v3 的补跑任务
  单进程占 40042/40960 MiB，此时提交会 OOM 或互相挤掉。

**其它**：26 镜 ref2va 直出 768 占成本 **47–49%**（631 s/镜 = 两阶段的 4.2 倍）；
**120 镜 T2V `ref_images` 是空数组** → 人物一致性 = 146 次独立摇号。

## ★ 显存账本（三条硬结论）

VRAM 40 440 / RAM 64 108 MB。① S1 TE 25 882 + UNET 19 995 = **113%，物理上不可共存**；
2. S1(52G)+S2(37G)=89 GB > 64 GB；权重后备是**文件 mmap + OS 页缓存**（冷读 25.9 GB ≈ 50 s vs PCIe 2.6 s，**差 20 倍**）
→ **一次只让一套权重在场**，段边界 `POST /free {"unload_models":true,"free_memory":true}`
（26.7G→0.6G；★ 返回 **200 但响应体 0 字节**，不要 `json.loads`）；
3. ★★ **显存是瓶颈不是余量**：采样期显存 98.4% / SM 100% / 功耗 234/250 W **三项同时贴满**，
搬 20 GB 走 PCIe 仅 1.7 s（占 631 s 的 0.27%）→ **吃时间的是前向计算，"闲置显存换速度"不存在**，
换 80 GB 卡也不快一秒。★ 瓶颈是**权重**（50.2 GB > 40 GB）不是激活值 → 提分辨率几乎不占显存，**代价全在时间**。

**两个会静默毁结果的坑**：① `SaveVideo.format/codec` 类型 `COMFY_DYNAMICCOMBO_V3`，
`ui_to_api.py` 白名单不认 → 两参数连键带值消失，前面节点全跑完才报 `missing ... 'format'`；
② API 工作流顶层不能有 `_meta`，否则 `/prompt` 报 `missing_node_type: ID #_meta`。

**加速件盘点：一个能直接用的都没有。** Sage 全局 `--use-sage-attention` **全 NaN** —— H3 核硬依赖
`_sageattn_int8_fp8_nhd`（INT8 QK + **FP8 PV**），A100 无原生 FP8；正解是 MODEL 分支 `PathchSageAttentionKJ`
（可省 30%，**本机未装 KJNodes**）。SLA / Progressive / PDD 8 步 / `--fast-disk` 均为 ❌。

## ★ 其余高分结论（一句话版）

- **Stage2 精修**（`scripts/stage2/`）：官方工作流开箱跑不了（缺 `dev-transformer` / `distilled-lora-450` /
  `taeltx2_3_wide.pth`）→ 用**融合版** `ltx-2.5-22b-distilled-transformer-comfy-int8-convrot` 顶替 + 删 LoRA + TAEHV 换回 `VAEDecode`。
  ★ **默认必须 `--preset identity`**：与官方版只差 `#10` 一个节点，官方 sigmas 起点 **91% 是噪声**（近乎重画，
  实测把品牌名画成 `Fayee` 乱码、把女主换成人），identity 起点 0.5 保留中文印刷与同一张脸，**且零成本**（75.0 vs 75.3 s）。
  参考图注入 `s2_adapt.py --guide refs/x.png --guide-frame N`（原生 `LTXVAddGuide`，接线 `#26+#7 → #91 → #14/#16` 三路都要改）。
- **一致性缺口在 S1 不在 S2**：prompt 里的 `<Character reference ... same face>` 只是**形容词**，
  `ref_images` 槽（最多 9 张）才是硬约束。三级策略：统一 seed → 角色定妆照常驻 `ref_images` → 首帧锚定链。
  ★ **换装镜**两个造型要各配参考图。
- **Ref2VA 有独立权重** `minimax_h3_ref2va_int8_convrot` + `minimax_h3_ref2v_turbo_*`（**ref2v** 不是 fl2v），
  不能用 fl2va 顶替。`edit_image` 恒为 `<Picture 1>`，附加图编号须连续，上限 9 图/3 视频/3 音频。
  ~~短边 <512px 崩坏~~ **已推翻**（384×672 跑通，袋面印刷正常）。
- **产品高清的像素门槛**（`scripts/pixel-gate/`）：**根因不是参考图不够清晰，是产品在画面里占的像素太少**
  （参考图只给外观先验）。原方案袋面仅 226×296 px、竖排汉字每字 ~5×3 latent 格 → 物理上画不出来。
  公式 `产品可用像素 = 帧宽 × 占画面比例`、`latent 格宽 = 像素 ÷ 8`、**竖排汉字需 ≥ 8 格宽**。
  四组同镜实测：原方案(中景) ≈631 s／只改构图 360 s→~70% 可读／构图+提分辨率 631 s→~100%／特写草稿再走 S2 640 s→~95%。
  ★ **改构图零成本**（采样成本只由 latent 尺寸 × 步数 × 模型决定）。**落地四步**：① 产品镜改特写构图（≥70% 画面、正面朝向）
  ② S1 保持 384×672 **不**提分辨率 ③ S2 一律 identity ④ 关键产品镜加四角透视合成贴图（生成画字是概率性的，100% 正确必须兜底）。
  画布上限 **1920×1088 参考面积**；S2 输出封顶 768×1344。

## ★★★ A100 上怎么跑 H3 —— 照抄 v3 流水线（2026-09-18 定论，比本文件其它任何节都先看）

**已跑通的事实**：`h3-films/_deliver/v3/成片_film1.mp4`(223MB) / `成片_film2.mp4`(256MB)，
2026-09-18 08:14/08:16 出片。**就在 A100（kehu）上跑的** —— `deliver_v3.sh` 第 6 行
`SRV="kehu:/workspace/ComfyUI/output/MiniMaxH3/v3run"`，产出 51 个 mp4（前缀 `f1sNN_`/`f2sNN_`）。

**★ 提交器不是 `80_run_workflow_remote.py`（它在 A100 上不存在，别再找了），
而是 `/root/s2/submit_api.py`** —— 接口 `submit_api.py api_json [--host --timeout --poll --json-out]`，
**吃 API 格式 JSON、没有 `--set`**。→ **A/B 选型 = B，不用选，照抄即可。**

**链路**：`build_workflows_v3.py --one <key>`（参数直接写进 JSON：`wf["6"]["inputs"]["prompt"]`、
`width/height`、`wf["13"]["inputs"]["audio"]`=原声锁、`wf["12"]["inputs"]["filename_prefix"]`、
`wf["9"]["inputs"]["noise_seed"]`）→ 落 `_remote/v3run/wf_<key>.json`（API 格式，
模板在 `_remote/v2prev_tpl/s16.api.json` t2va / `pg_B.api.json` ref2va）
→ `run_v3.sh` 循环 `python3 /root/s2/submit_api.py wf_$k.json`。
**断点续跑 = 从 `keys.txt` 删掉已成功的 key。**

**★ 批处理是写死的**：`run_v3.sh` 注释原文「顺序（模型只装两次，**绝不交替**）：
T2V(f1 16) → T2V(f2 18) → I2V(f1 7) → I2V(f2 7)」；`keys.txt` 前 34 个全 T2V、后 13 个才 I2V。
`PIPELINE.md` 算过：拆两批 56.5 分 vs 交替 96.1 分，**省 39.6 分**，「唯一无代价的优化就是拆两批」。

**★ 但 v3 是「一步直出 768×1344」（只有 t2va/ref2va，无 Stage2），不是两阶段精修。
照抄 = 提交机制 + 批处理思想；不照抄 = 工作流模板。**
两阶段模板链路已在 A100 实跑验证通：
`s2_adapt.py --template <官方> --preset identity --width 768 --height 1344 --out s2.json`（→10 节点 UI）
→ `/root/ui_to_api.py s2.json --out s2.api.json`（→22 节点 API，含 `#3 MiniMaxH3SolEngineDraftToLTXT8Advanced`）
→ `submit_api.py`。官方保脸工作流现成：
`.../22-sol-engine-h3-super/2026-08-30_H3_Sol_Engine_LTX25_Identity_Preserve_3Step_Advanced_EXP.json`。
★ 转换时可见 `[20] SaveVideo widgets 1/3` —— 白名单坑正在生效，**A 路子（补 --set）必踩**。

**★ 两阶段比一步直出快 3.7 倍**（0.96 h vs 3.56 h，同 20 镜）→ 坚持两阶段不只是质量选择，也是成本选择。
**★ v3 走「原声锁」**：`wf["13"]["inputs"]["audio"] = s["audio_file"]`，中文是外部 TTS 干声锁进去的。
与 `11_run_voice_film.py` 的注明一致：让 H3 自己说中文**台词不稳**。新片有中文台词就应走原声锁。

## 铁律

1. **成片一律不烧字幕** —— 独立 `.srt`/`.vtt` 与成片同名同目录交付。
2. **禁字三层防线** —— `NO_TEXT_CLAUSE` 声明 + `build.py with_style` 终检（缺锚点 `SystemExit`）+
   `scan_text_band.py` 目视（OCR 认不出 H3 伪汉字，不可靠）。
3. **时间轴口径** —— 字幕绝对时间 = Σ前序镜实际时长 + 镜内时间/倍率，绝不能用 `(镜号-1)×单镜时长`。
4. **产品镜权威来源** —— prompt 用 `<Subject P>` 锚定，**不能搜 "pack"**（STYLE 含 package 会全命中）；
   参考图路线须用 `<Picture N>` 标签否则不被认领。
