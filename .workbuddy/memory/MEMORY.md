# videoHub 项目长期记忆

> 本文件只留**跨会话必用的判据**，细节全部指向源文件：
> - 技术细则 → `~/.workbuddy/skills/h3-film-production/SKILL.md`（973 行，唯一权威）
> - 生产规则 → `待生成_现代婚姻三部曲/AGENTS.md`（§零 硬标准 / §二 栅格 / §八 坑位）
> - 原始实测数据 → 同目录 `2026-09-1*.md`

## ★★★ 剧本生产硬标准（2026-09-18 起 · 所有剧本强制）

用户原话「**以后的剧本都要这么要求**」。任何新剧本进 manifest 之前必须过这一关，
完整条文见 `待生成_现代婚姻三部曲/AGENTS.md` **§零**。

- **S1 零字幕** — 无 `<d>` 标签 + 有 `strict_output_constraints` 段 + 文字道具带 `illegible`
- **S2 表情到位** — 微表情 ≥3 + 情绪过渡 ≥1 + 完全静态词 =0
- **S3 位置逻辑** — 多人镜方位锚点 ≥1 · 单人镜朝向锚点 ≥1 · 跨镜符合**场景空间坐标表**
- **S4 技术对齐** — prompt 时间戳末段 = duration · 工作流与 manifest 同源

三关：**自动扫描**（`_pipeline/review_v3.py`）→ **试拍目视**（每片挑最难镜）→ **复盘写回 AGENTS.md**。
★ 扫描只查「有没有写」，**写得好不好必须目视**。

两条机理（别再忘）：
- `<d>[Chinese]"…"</d>` 是 H3 dialogue 结构化指令 → 同时驱动口型**和**渲染屏幕字幕，
  尾部自然语言 `no subtitles` 压不过它。**彻底剥离比只去引号更保险。**
- H3 音频驱动：**干声定口型，面部神态全由 prompt 文字定**。写满 `unnervingly calm` = 木头人。

## 项目性质与路径

自建 ComfyUI + MiniMax H3 管线批量产 AI 短剧；本机只编排/后处理，重活跑远端 GPU。
- 工程：`~/Desktop/videoHub/`（git 仓库；根 `.gitignore` 统一排除 mp4/wav/png/jpg，**勿建子级**）
- 三部曲：`~/Desktop/videoHub/待生成_现代婚姻三部曲/`（3 片 × 8 镜 = 24 镜）
- 服务器 `kehu`（49.0.196.218）：**2× A100-PCIE-40GB / 125 GB 内存 / 16 核 / 148 GB 盘**，
  机房在**华为泰国**（2026-09-18 升级 + 系统重装后重建）
  - ★ 泰国机房 **ModelScope 9 B/s 等于不通**，权重**一律走 HuggingFace**（35–42 MB/s）。
    避坑：测速必须 `curl -L`，否则量到 302 页面误判成 KB/s
  - 驱动 **580.95.05**（CUDA 13.0）；torch `2.14.0+cu130`；ComfyUI **v0.36.0 @ `ee71d5c4`**（2026-09-18 升级）；
    `comfy-kitchen==0.2.34`（启用 H3 专有 CausalConv3d/RMSNorm/RoPE 算子融合）；
    T8 节点 v1.79.6 @ `e12d8af`
  - **双卡 = 双实例**：ComfyUI 不支持单进程跨卡 → `CUDA_VISIBLE_DEVICES=0 --port 8188`
    与 `=1 --port 8189 --database-url sqlite:////workspace/instance_b.db` 两个进程（**实例 B 必须加 database-url 隔离防 SQLite 锁死**），
    24 镜拆 `keys_a/keys_b` 各 12 镜（单实例仅 45 GB 内存）
  - ★ 权重在本地盘 → 启动**不带** `--disable-mmap`
  - 重建素材源：本地快照 `~/Desktop/github/h3-remote-snapshot/`（README + 权重映射表）
- 提交器 **`/root/s2/submit_api.py`**（吃 API JSON，**无 `--set`**），本地备份
  `~/Desktop/videoHub/h3-films/_a100work/submit_api.py`；
  `80_run_workflow_remote.py` 在 A100 上**不存在**，别再找

## ★★ 双重栅格（排期唯一权威）

H3 `length` ∈ **17n+5**（step 17 / 向上吸附）→ LTX `frame_policy=trim_to_8n_plus_1`（向下取 8m+1）。
- **两阶段**：成片 = trim(H3 帧)。10–15 s 仅 8 个合法档；**345 帧 = 14.375 s 唯一双对齐无损**
- **一步直出**：不经 LTX，成片 = H3 帧 → manifest `duration` 必须存 H3 值（全片比 trim 口径 +3.75 s）
- **禁止填任意秒数**：填 13.0 → 吸附 328 帧 → 实际 13.375 s，**字幕轴静默错位**

## ★ 计时口径（混用会差 4 倍）

| 口径 | 单镜 | 24 镜 |
|---|---|---|
| 两阶段 · 热态批处理 | **149 s** | ≈ 1.1 h ← 旧排期 |
| 一步直出 768×1344（旧版 v0.35.0） | 590 s/镜/卡 | 24 镜 ≈ **2.0 h** |
| **一步直出 · 双卡并行（v0.36.0 实测）** | **469 s/镜/卡** | 24 镜 ≈ **1.56 h（1h34m）** ← **现在排期用这个（快 20.5%）** |

比值 **3.2–3.7×**。★ A100 **冷启 = 热态 4–5 倍**（首镜 382 s → 热态 74 s），**全项目最大记账陷阱**。

## ★ 显存 / 内存铁律

1. 权重 50.2 GB > 显存 40 GB → **一次只让一套权重在场**；段边界必
   `POST /free {"unload_models":true,"free_memory":true}`（★ 返回 200 但**响应体 0 字节**，别 `json.loads`）
2. **ComfyUI 跑完不自动释放**（常驻 20–29 GB 而利用率 0%）→ **显存高 ≠ 在忙**。
   点火前必查 `/queue` 的 `queue_running`，并主动 free
3. 显存是**瓶颈**不是余量 → 「闲置显存换速度」不存在（搬 20 GB 仅占 0.27%）

## ★ 会静默毁结果的坑（详见 AGENTS.md §八）

- `SaveVideo.format/codec` 是 `COMFY_DYNAMICCOMBO_V3`，`ui_to_api.py` 白名单不认
  → 参数连键带值消失，前面节点全跑完才报 `missing 'format'`
- API 工作流顶层不能有 `_meta`（报 `missing_node_type: ID #_meta`）
- **`s2_adapt.py` 只吃 API 格式**：官方模板是 UI 格式，直喂 → 三处改造静默不执行 + **谎报「已适配」**
  + `parametrize` `KeyError: '3'`。正确链路：
  `官方UI → ui_to_api → raw.api → s2_adapt(A/B/C+identity) → tpl.api → s2_adapt(--shot/--draft) → per-shot.api`
- **`pkill -f <name>` 会匹配到执行它的 ssh 命令行 → 自杀式断连**（表现为"命令静默失败"）。
  排查用 `ps -eo pid,args --no-headers`
- stage2 取草稿前缀 `f1s02` vs 实际 `f1_s02`（带下划线）→ 匹配为空，stage2 全跳
- **权重路径带子目录**：工作流要 `text_encoders/minimax_h3/qwen3vl_32b_...`，
  放错到 `text_encoders/` 根 → 400 `value_not_in_list`（提交阶段就炸，好查）
- **服务器必须装 ffmpeg**（`apt install ffmpeg`）：T8 保存节点 H.264 长视频要它，
  缺了会**生成跑满 590 s 后在最后一步报**
  `FFmpeg is required for isolated H.264 long-video encoding`
- **shell 优先级**：`cd X && A & B &` 里 B 跑在**原 cwd** → 后台提交一律用绝对路径

## 三部曲现状（2026-09-18 从 story 迁入 videoHub）

- 生成模式已切 **一步直出 768×1344**：两阶段精修糊 —— stage2 从 384 草稿上采样补细节，
  有涂抹感/动态拖影；一步直出是全噪声去噪，明显更锐
- 24 镜 prompt 已过四条硬标准（微表情 4.8/镜、情绪过渡 2.3/镜、`<d>` 残留 0）
- **2026-09-18 18:08 双卡全量 24 镜已启动**（`run_dual.sh a|b` → run_a.log / run_b.log，
  产出 `/workspace/ComfyUI/output/MiniMaxH3/trilogy_one/`）
- 试拍 f1s01：768×1344 / 含音轨 / 15.084 s，与 manifest 15.083 **一帧不差**（新机复现一致）
- **待办**：24 镜回收 → **按 H3 duration 重算字幕轴** → 后期处理道具文字
