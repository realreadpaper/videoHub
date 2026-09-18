# videoHub 项目长期记忆

> 只留**跨会话判据**，细节一律指向源文件：
> - ⚠ **`~/.workbuddy/skills/h3-film-production/` 并不存在**（旧记忆一直在指这个幽灵路径），
>   替代件 = `~/.workbuddy/skills/h3-key-shot-batch/SKILL.md`（双卡出片 + 回收审查全流程）
> - 生产规则 → `待生成_现代婚姻三部曲/AGENTS.md`（§零 硬标准 / §二 栅格 / §八 坑位）
> - 拆解 / 下载 / 验收 → `~/.workbuddy/skills/{video-breakdown,douyin-download,acceptance-doc}/`
> ⚠ 工程里残留大量 `/Users/hejianglong/...` 旧机路径（本机是 `jianglong`），直接跑 file not found。

## ★★★ 剧本硬标准（2026-09-18 起 · 所有剧本强制）

用户原话「以后的剧本都要这么要求」。新剧本进 manifest 前必过，条文见 AGENTS.md §零。
- **S1 零字幕** — 无 `<d>` 标签 + 有 `strict_output_constraints` 段 + 文字道具带 `illegible`
- **S2 表情到位** — 微表情 ≥3 + 情绪过渡 ≥1 + 完全静态词 =0
- **S3 位置逻辑** — 多人镜方位锚点 ≥1 · 单人镜朝向锚点 ≥1 · 跨镜符合场景空间坐标表
- **S4 技术对齐** — prompt 时间戳末段 = scene_duration

三关：自动扫描（`_pipeline/review_v3.py`）→ 试拍目视（每片挑最难镜）→ 复盘写回 AGENTS.md。
★ 扫描只查「有没有写」，**写得好不好必须目视**。

两条机理：
- `<d>[Chinese]"…"</d>` 同时驱动口型**和**渲染屏幕字幕，尾部自然语言 `no subtitles` 压不过它
  → **彻底剥离**比只去引号保险。
- H3：**干声定口型，面部神态全由 prompt 文字定**。写满 `unnervingly calm` = 木头人。

## 路径与约定

工程 `~/Desktop/videoHub/`（git 仓库，根 `.gitignore` 统一排除 mp4/wav/png/jpg，**勿建子级**）。
- 生产线 `h3-films/`（广告片 film1-office 良心面试 / film2-blinddate）；广告工作区 `videos/`
- **参考视频落盘**：`videos/douyin_refs/YYYY-MM-DD/<视频ID>/`（mp4 + 拆解产物同目录）
- **验收文档**：`验收文档/YYYY-MM-DD/`（+ `_spec/` 可重跑输入）
- 外部仓库 5 个 submodule（`repos/hypit` `repos/FastVideo` `repos/jianying-headless`
  `reelbench-skills` `TaoMate-H3`）。★ 本机全局 git 有 `url.…insteadOf` 把 HTTPS 改成 SSH
  → 拉取前加 `GIT_CONFIG_GLOBAL=/dev/null`，否则 submodule 全拉不下来。
- 密钥一律放 `~/.workbuddy/secrets/`（**仓库外**）：`dashscope.key`（阿里云百炼）

## 服务器 kehu（124.81.178.140）

2×A100-PCIE-40GB / 125 GB 内存 / 16 核 / 148 GB 盘；华为泰国；主机名 `kehu-jianglong`。
- ★ **连不上先怀疑本机 Clash Verge 的 TUN**，不是密钥 → 技能 `ssh-tun-hijack-diagnosis`
- 驱动 580.95.05（CUDA 13.0）；torch `2.14.0+cu130`；ComfyUI **v0.36.0**；
  `comfy-kitchen 0.2.34`；T8 节点 v1.79.6；`ComfyUI-MiniMaxH3-TeaCache` 已装
- **双卡 = 双实例**：`:8188`(GPU0) / `:8189`(GPU1，需 `--database-url sqlite:////workspace/instance_b.db`
  **防锁死**)。启动一律带 `--vram-headroom 1 --use-ck-attention`；
  ★ 用 `setsid nohup … < /dev/null &`，否则 ssh 断开会把任务带走
- 权重：`minimax_h3_fl2va_pruned_int8_convrot`（无参考音/静音轮用）、
  `Minimax-h3_Singularity_ref2va_Pruned_v1.3_int8`（原声锁用）、
  `minimax_h3_turbo_v4_step600_ema` LoRA（4 步加速）
- 提交器 `/root/s2/submit_api.py <api_json> --host <url> --timeout N`（**无 `--set`**）
- ★ 权重走 **HuggingFace**（泰国机房 ModelScope 等于不通）；测速必须 `curl -L`
- 目录 `/workspace/{ComfyUI,trilogy,dy_key,logs}`；`ffmpeg` 必装（T8 存 H.264 长视频要它）
- ★ **回传慢 = 跨境丢包，不关服务器带宽**（服务器下外网 26 MB/s）。判据
  `ss -tnpi state established "( sport = :22 )"`：`cwnd` 个位数 + `retrans` 上千 = 丢包型限速，
  **开 BBR 即解**（0.11 → 6 MB/s，约 50 倍）；已持久化 `/etc/sysctl.d/99-net-speed.conf`
- **swap 8 G + `vm.swappiness=10`**（2026-09-19 加：`/swapfile`，已写 `/etc/fstab`
  与 `/etc/sysctl.d/99-swap.conf`）。加它是**兜底防 OOM kill，不是扩内存**——
  真开始用 swap 时会慢到像卡死，别当成容量用
- ⚠ 内存真紧张的**病根是空闲实例白吃内存**：ComfyUI 即便队列全空也常驻 ~57 G（2026-09-19
  实测 8189 空跑吃 56.6 G）。内存告警时先查 `/queue`，**卸/停空闲实例比加 swap 更有效**；
  但注意卸权重要付冷启代价（热态 4–5 倍），近期要用双卡就别卸

## ★ 栅格 / 计时 / 硬件（排期三件套）

- **栅格**：H3 `length` ∈ 17n+5（向上吸附）→ LTX `trim_to_8n_plus_1`。
  一步直出不经 LTX，成片 = H3 帧，`duration` 必须存 H3 值。**禁止填任意秒数**（会静默错位字幕轴）。
- **计时**（混用会差 4 倍）：一步直出 768×1344 单卡 ≈ **590 s/镜**（v0.35）；
  v0.36 + Turbo（4 步）冷启 641 s / 热态 551 s。
  ★ **TeaCache 已禁用（2026-09-19 用户决定）**：4 步下尾段拖影/涂抹，宁可慢也要干净，
  工作流链路 = UNet→LoRA→Sampler，加速只剩 Turbo LoRA + ck-attention。
  ★ **双卡 = 吞吐翻倍不是单镜提速**（一镜拆不到两卡）；N 镜分布 ⌈N/2⌉+⌊N/2⌋，
  挂钟由多跑那张卡决定，另一张提前空闲属正常。
  ★ **A100 冷启 = 热态 4–5 倍**（首镜 382 s → 热态 74 s），**全项目最大记账陷阱**。
- **硬件门控**：SM≥7.5（CUDA13/INT8）、bf16 需 SM≥8.0、显存≥21 G。瓶颈是
  **权重 50.2 G > 40 G 的前向计算**，非激活值 → 换 80G 卡不快。

## ★ 显存 / 内存铁律

1. 一次只让一套权重在场；段边界 `POST /free {"unload_models":true,"free_memory":true}`
   （★ 返回 200 但**响应体 0 字节**，别 `json.loads`）
2. **ComfyUI 跑完不自动释放** → **显存高 ≠ 在忙**。点火前必查 `/queue` 并主动 free
3. 显存是**瓶颈**不是余量 →「闲置显存换速度」不存在

## ★ 会静默毁结果的坑（完整版见 AGENTS.md §八）

- `SaveVideo.format/codec` 是 `COMFY_DYNAMICCOMBO_V3`，白名单不认 → 参数消失，跑完才报 `missing 'format'`
- API 工作流顶层不能有 `_meta`（报 `missing_node_type: ID #_meta`）
- **`s2_adapt.py` 只吃 API 格式**（直喂 UI 会静默不改造 + 谎报「已适配」）。
  链路：`官方UI → ui_to_api → raw.api → s2_adapt(A/B/C+identity) → tpl.api → s2_adapt(--shot/--draft)`
- **`pkill -f <name>` 会匹配到执行它的 ssh 命令行 → 自杀式断连**，排查用 `ps -eo pid,args`
- **shell 优先级**：`cd X && A & B &` 里 B 跑在**原 cwd** → 后台提交一律绝对路径
- 权重路径带子目录：要 `text_encoders/minimax_h3/...`，放错根 → 400 `value_not_in_list`
- 清队列用 `POST /queue {"clear":true}` + `POST /interrupt`，**别用 pkill**

## ★ 一致性 / 台词 / 产品 / 不油腻

- 一致性靠 **`ref_images` 槽位（≤9 张）**，prompt 写 "Character reference" 只是形容词、无约束力
- 中文台词走**原声锁**：外部 TTS 干声写进 `wf["13"].audio`（H3 自己说中文不稳）；
  纯审画面的轮次挂 `silent_15s.wav`，prompt 音景写死 `No speech, no voices, no dialogue`
- 产品高清根因 = **产品占画面像素太少** → 改特写构图（≥70% 画面、正面）**零成本**
- **禁「油腻」写法**（2026-09-19 起）：风格段显式写 `matte finish` + `visible pores` +
  `neutral white balance` + `muted naturalistic colour`，并加负向
  `no oily sheen / no glossy specular highlights / no beauty-filter / no plastic or waxy skin /
  no HDR glow / no over-sharpening / no orange or teal cast`

## 交付铁律

1. 成片不烧字幕，外挂 srt/vtt 同名同目录交付
2. 禁字三层防线：NO_TEXT_CLAUSE + `build.py` 终检（缺锚点 SystemExit）+ `scan_text_band.py` 目视
3. 字幕绝对时间 = **Σ前序镜实际时长**，不能 (镜号-1)×单镜时长
4. 产品镜 prompt 用 `<Subject P>` 锚定、参考图须 `<Picture N>` 标签

## 当前进度（2026-09-19 01:00）

- **三部曲**（现代婚姻 × 周星驰/姜文/奉俊昊）24 镜 prompt 已过硬标准，
  一步直出只跑过 f1s01/f1s02 试拍；**未全量出片**（8189 实例长期没起，实际单卡在跑）
- **抖音三片**（同一品牌佐味纪红烧酱，自有账号）已拆解完（99/119/155 镜）
  → 2026-09-19 起进入**复刻**：先每片出一镜关键镜审画面。
  工作区 `videos/douyin_refs/2026-09-18/_remake/`（`build_key_shots.py` 出 wf），
  服务器 `/workspace/dy_key/`（`run_worker.sh <TAG> <PORT> <keys…>` + `gates/` 断点续跑）
- 三片关键镜选定：报恩 f1 后门口「换我接您走」／继母 f2 拥抱「谢谢妈妈」／挑食 f3 餐桌验证
- ★ 数据最好的那条镜最慢（2.99s/镜）、产品出现最早（0:56）、唯一有「十年后回报」闭环
  → 判据：**慢一点、把产品写进人物命运里，比堆快切和打脸更有效**
