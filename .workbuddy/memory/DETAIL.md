# videoHub 项目判据 · 完整归档（DETAIL）

> 本文件是 `MEMORY.md` 的**归档详情**（MEMORY.md 超 3000 字会被截断，故细节挪到这里）。
> 主文件 `MEMORY.md` 只放跨会话必读判据与索引；**这里保留全部条文**，可能含已被新实测推翻的旧结论
> （例如「8 步更好」已被证否，见文末 2026-09-19 追加段）。冲突时以文末最新段为准。

> 只留**跨会话判据**，细节指向源文件。新条目先自问：能压缩成一句 + 一个路径吗？
> 生产规则 → `待生成_现代婚姻三部曲/AGENTS.md`（§零 硬标准 / §二 栅格 / §八 坑位 17 条）·
> 出片全流程 → 技能 `h3-key-shot-batch`（★ 旧记忆的 `h3-film-production/` **不存在**）·
> 拆解/下载/验收 → 技能 `video-breakdown`/`douyin-download`/`acceptance-doc` ·
> 换机 → `deploy/README.md` + `docs/{新服务器,单卡A100}部署手册.html`
> ⚠ 工程里残留 `/Users/hejianglong/...` 旧机路径（本机 `jianglong`），直接跑 file not found。

## ★★★ 剧本硬标准（用户：「以后的剧本都要这么要求」）

条文见 AGENTS.md §零。**S1 零字幕**（无 `<d>` + 带 `strict_output_constraints` + 文字道具 `illegible`）·
**S2 表情**（微表情 ≥3、情绪过渡 ≥1、静态词 =0）· **S3 位置逻辑**（多人镜方位锚点 ≥1、单人镜朝向锚点 ≥1）·
**S4 技术对齐**（prompt 末段时间戳 = scene_duration）。三关：`_pipeline/review_v3.py` 扫 → 试拍目视 → 写回 AGENTS.md。
★ 扫描只查「有没有写」，**好坏必须目视**。
机理：`<d>[Chinese]"…"</d>` 同时驱动口型**与**屏幕字幕，尾部 `no subtitles` 压不住 → **彻底剥离**；
**干声定口型，面部神态全由 prompt 文字定**（写满 `unnervingly calm` = 木头人）。

## ★★ 复刻任务：切分单位 = 台词句，不是镜

用户判据「一镜 15s、5s 一个动作太缓慢」→ **根因是切分单位**。
- **1 句台词 = 1 生成单元**（语音覆盖 96.6–99.7%、句间隙中位 0.00s）。工具 `h3-key-shot-batch/scripts/build_units.py`（放 `_remake/` 跑）。
- 实测 113→74 / 128→78 单元，双卡 **1.1 h/片**（拉满 354 帧要 11.4 h）。
- ★ **成本反直觉**：耗时是帧数**平方级** → **短镜每秒更便宜**（22 帧 19 s/s vs 354 帧 38 s/s）。切短治拖沓又省机时，**无取舍**。
- ★ **1.6s 短单元不可合并**（反应句/金句是命门）；安全下限 **39 帧 = 1.63s**；常用 **107 帧 = 4.458s**。
- ⚠ ASR 会把相邻说话人并进一句 → **人工拆**；复核只看 **≥5s 的单元**（约 1/3）。
- 拍点：起（静止进微动作）/承（dolly-in 8–12%）/**转**（过肩换轴，1人→2人层次）/合（反应落点）。**禁拖沓**：产品段不插空镜、对话不插慢镜。

## ★★ 构图锁死：步数不是杠杆（2026-09-19 实测）

同镜（dy1_s001，同 seed，Hybrid 双端钉帧）跑 4/6/8/12 步，SSIM vs 钉死首帧/末帧：
`4步 0.850/0.629 · 6步 0.659/0.671 · 8步 0.666/0.712 · 12步 0.651/0.657`（耗时 130/—/230/310 s）
- 目视：4 步帧0 完全等于钉首帧却帧19 已推成大特写；**6/12 步帧0 自己就是特写**（起点都没守住）；8 步帧0 变成"末帧那张"（两端打架）。
- → **步数不是杠杆且非单调（混沌）**。**保持 4 步**，省下的时间换多个 seed 备选。
- ★ **Hybrid 双端钉帧只保证首尾**，中段仍漂（模型在两端间用自身先验插值）。「自动动作文本 vs 人工动作文本」成片上**无稳定优劣** → 4 步下模型推镜倾向压过 prompt 措辞。

## ★★ 关键镜提示词必须人工写

- `build_directing.py` 动作池**与镜头大量错配**，且按镜长给静态镜硬塞推镜：dy2_s118 是拥抱戏却写「小优夹肉放进嘴里」、dy1_s093 固定机位却写「缓拉远」；EN 译文还会幻觉（餐桌戏译成"沙发上看绘本"）。
- **关系镜/产品镜必须人工写**动作 + 角色关系段，自动台本只当草稿。
- ★ **角色与关系要显式写进 prompt**（`<Characters and their relationship>`：身份 + 彼此关系 + 该镜微表情）才影响表演；只写 `speaker` 名无效。
- 实现：`build_wf_v2.py --six six.json --action_file six_action.json`（`videos/douyin_refs/2026-09-18/_remake/`）。

## 路径与约定

工程 `~/Desktop/videoHub/`（git，根 `.gitignore` 排除 mp4/wav/png/jpg，**勿建子级**）；生产线 `h3-films/`；广告 `videos/`；
参考视频 `videos/douyin_refs/YYYY-MM-DD/<ID>/`；验收 `验收文档/YYYY-MM-DD/`。
- ★ **镜头边界阈值：对白驱动/正反打密集短剧一律 0.04 起步**（**别按 AI vs 实拍二分**）。真切帧差可低至 0.046，`hypit media boundaries` 默认 `--threshold 0.1` **在源头滤掉** → 必须 `--threshold 0.04 --rate 12` 重跑（只改 build_shots.py 救不回）；校准用 **0.5s 密度**网格；0.04/0.1/0.15 跑一遍，**镜数差 >20% 就目视校准**。
  AI 短剧用**镜内渐变变形代替剪辑**（12.17s 长镜走完 现实→回忆→变形）→ **不是漏切，别切开**。
- ★ **带货短剧两特征**：① **0 个纯画面镜**（113/128 全有台词，7.0 字/秒），插慢镜/空镜立刻塌节奏；② **产品段是可跨片复用模板**（痛点→电饭锅颠覆→三步做法→脱骨验证→只洗一个内胆→比价→9.9 元 7 包），换片只换 1–2 卖点；产品**首次出现藏在"善举"里**（28–33% 处），不承担销售功能。
- git 全局 `url.…insteadOf` 把 HTTPS 改 SSH → 拉 submodule 前加 `GIT_CONFIG_GLOBAL=/dev/null`。密钥在 `~/.workbuddy/secrets/`（**仓库外**）：`dashscope.key`。

## 服务器 kehu（124.81.178.140）

2×A100-PCIE-40GB / 125 GB 内存 / 16 核 / 148 GB；华为云泰国；`kehu-jianglong`。
- ★ **连不上先怀疑本机 Clash Verge TUN**，不是密钥 → 技能 `ssh-tun-hijack-diagnosis`。
- **双卡 = 双实例** `:8188`/`:8189`（8189 需 `--database-url sqlite:////workspace/instance_b.db` **防锁死**）；**单卡 = 单实例**只起 `:8188`，**不需要 `--database-url`**。启动带 `--vram-headroom 1 --use-ck-attention`；`setsid nohup … < /dev/null &`。
- 驱动 580.95.05；torch `2.14.0+cu130`；ComfyUI **v0.36.0**；T8 节点 v1.79.6；ck-attention 已开。
  权重（**走 HuggingFace**，ModelScope 在泰国不通，测速必须 `curl -L`）：`minimax_h3_fl2va_pruned_int8_convrot`（静音轮）、`Minimax-h3_Singularity_ref2va_Pruned_v1.3_int8`（原声锁）、turbo LoRA `minimax_h3_turbo_v4_step600_ema`。
  提交器 `/root/s2/submit_api.py <api_json> --host <url> --timeout N`（**无 `--set`**）；目录 `/workspace/{ComfyUI,trilogy,dy_key}`；`ffmpeg` 必装。
- ★ **回传慢 = 跨境丢包**（服务器下外网 26 MB/s）。判据 `ss -tnpi state established "( sport = :22 )"`：`cwnd` 个位数 + `retrans` 上千 → **开 BBR**（0.11→6 MB/s），已持久化。
- ★ **内存病根是空闲实例白吃**（队列全空也常驻 ~57 G）→ 先查 `/queue`，**停空闲实例比加 swap 有效**；卸权重付冷启代价（热态 4–5 倍）。swap 8G + `swappiness=10` 只是**兜底防 OOM**。
- ★ **attention 加速天花板 = 注意力占比**（354 帧占每步 62%）。SM80 **无 FP8** → 现实收益 **−12%~−20%**。
- ⚠ **服务器是共享的**（2026-09-19 有另一会话在跑 `dy4_pilot/*`）→ 动队列前先看 `/queue` 里是不是自己的活。

## ★ 栅格 / 计时 / 硬件门控

- **栅格** `length` ∈ **17n+5（向上吸附）**；`duration` 必须存 H3 值（填任意秒数静默错位字幕轴）。
- **计时**：768×1344 一步直出 ≈ **590 s/镜**；v0.36+Turbo 冷启 641 / 热态 551 s。★ **TeaCache 已禁用**（4 步下尾段拖影）。
  按帧数**平方级**估：`cost(N) ≈ 0.812N + 0.002129N² − 1.3`（107/226/354 帧 → 110/291/553 s）；短镜 ~110 s 固定开销。
- ★ **多卡 = 吞吐翻倍，不是单镜提速**（一镜拆不到两卡）；N 镜 ⌈N/2⌉+⌊N/2⌋，另一张早空闲属正常。
- ★★ **单卡换算律：双卡报告的「GPU 总机时」= 单卡「挂钟」**（加速比 1.950×）→ 旧双卡数字 ×2。
- ★ **A100 冷启 = 热态 4–5 倍**（382→74 s），**全项目最大记账陷阱**。
- **门控**：SM≥7.5、bf16 需 SM≥8.0、显存 ≥21 G、**内存 单卡 ≥96 GB / 双卡 ≥100 GB**。瓶颈是**权重 50.2 G > 40 G 的前向计算** → 换 80G 卡不快。★ **别选 64 GB 内存机型**。

## ★ 显存 / 内存铁律

1. 一次只让一套权重在场；段边界 `POST /free {"unload_models":true,"free_memory":true}`（★ 返 200 但**响应体 0 字节**，别 `json.loads`）。
2. **ComfyUI 跑完不自动释放** → **显存高 ≠ 在忙**；点火前必查 `/queue` 并主动 free。
3. 显存是**瓶颈**不是余量 →「闲置显存换速度」不存在。

## ★ 会静默毁结果的坑（完整 17 条见 AGENTS.md §八）

- ★ **`http_proxy` 劫持 localhost**（最阴）：有 `HTTP_PROXY=…` 时 `curl http://127.0.0.1:8188/...` **走代理拿 502** → 检查脚本误报「ComfyUI 没响应」。
  自查：curl 返 502/000 但端口在监听。**解法 `export no_proxy="127.0.0.1,localhost,::1"`**（`NO_PROXY` 同设）；远程用前置赋值。★ **下载权重的脚本不能加**；`deploy/` 下 7 个脚本已内置。
- **`pkill -f <name>` 会匹配执行它的 ssh 命令行 → 自杀式断连**；用 `ps -eo pid,args | grep "[x]xx"` 拿 PID 再 kill。清队列用 `POST /queue {"clear":true}` + `POST /interrupt`。
- **zsh 不做单词切分**（`for x in $VAR` 整串当一个词）→ 用字面列表或 `${=VAR}`；**`cd X && A & B &` 里 B 跑在原 cwd** → 后台提交一律绝对路径。
- 工作流顶层不能有 `_meta`（报 `missing_node_type: ID #_meta`）；`SaveVideo.format/codec` 是动态 combo，白名单不认 → 参数静默消失；**`s2_adapt.py` 只吃 API 格式**（喂 UI 会静默不改造 + 谎报「已适配」）；权重路径要带 `text_encoders/minimax_h3/...`，放错根 → 400 `value_not_in_list`。
- ★ **门禁脏状态**（不报错，只静默跳过）：`gates*/<k>.lock` 残留 → 该镜**永久跳过**；`<k>.fail` = 失败过被跳过。接手前 `find gates* -maxdepth 1 -type d -name '*.lock' -exec rmdir {} \;`。

## ★ 一致性 / 台词 / 产品 / 不油腻

- 一致性靠 **`ref_images` 槽位（≤9 张，键名 `ref_images.ref_image_0`，0 起）**；prompt 写 "Character reference" 是形容词、**无约束力**。
- ★ **治构图漂移最有力 = `first_frame`**（`task_type` = `Hybrid`，**首字母大写**；可选 `first_frame`/`last_frame`/`final_audio`）。旧 prompt 对「几个人、在哪、什么景深」零约束 → 排成一行/糊成一团。
  ⚠ first_frame 绑定偏**弱**（MAE 29–75；last_frame 好，10–20）→ **product 镜若原片首帧是人物中景、目标是酱包特写，别挂 first_frame**。
- 中文台词走**原声锁**：外部干声写进 `wf["13"].audio`；纯审画面轮挂 `silent_15s.wav` 并写死 `No speech, no voices, no dialogue`。
- **产品高清根因 = 产品占画面像素太少** → 改特写构图（≥70% 画面、正面）**零成本**。
- **禁「油腻」**：`matte finish` + `visible pores` + `neutral white balance` + `muted naturalistic colour`；负向 `no oily sheen / no glossy specular highlights / no beauty-filter / no plastic or waxy skin / no HDR glow / no over-sharpening / no orange or teal cast`。
- ★ **原片帧 94–96% 带文字**（字幕坐 y≈66–73%，另有竖排角色名/时间戳）→ 参考图必须**逐像素笔画掩码 + `cv2.inpaint`**（整块高斯模糊毁构图）；`find_hits` 在 768×1344 误报率高，**验收必须目视**。

## 交付铁律（细节见 AGENTS.md）

不烧字幕、外挂 srt/vtt 同名同目录 · 禁字三层防线（NO_TEXT_CLAUSE + `build.py` 终检 + `scan_text_band.py` 目视）·
字幕绝对时间 = **Σ前序镜实际时长**（不是 (镜号-1)×单镜）· 产品镜用 `<Subject P>` 锚定、参考图须 `<Picture N>`。

## 迁移备忘（旧机将关停 → 只租 1 张 A100）

- **权威源在本机**（`triology/wf_one/` 与本机 `_pipeline/wf_one/` md5 一致）→ 只需「本机 → 新机」上传；旧机 `dl/*.sh` **不可复用** → 用 `deploy/bootstrap/`；`ui_to_api.py`、`s2_adapt.py` 在旧机**已不存在**（run_server.sh 是 dead code，别补）；SageAttention **未装**（SM80 无 FP8，别再试）。
- **媒体资产不在 git** → 换机必须手传 `deploy/server-assets/inputs/`；`tts_dry/trilogy`、`dy_full_a`、`dy_full_ref` 是**独一份备份**。跑全量用 `WF_DIR`/`GATE_DIR` 切产线，**gates 必须独立**（混用会互相跳过）。
- 新机要改三处：`~/.ssh/config` 别名与 IP、密钥路径、Clash 直连放行（`IP-CIDR,<新IP>/32,DIRECT,no-resolve`）。

## 当前进度（快照）

- **三部曲** 24 镜 prompt 过硬标准，只试拍过 f1s01/f1s02，**未全量出片**。
- **抖音三片**（佐味纪红烧酱，99/119/155 镜）走「台词句 = 生成单元」复刻路线：时间轴剧本 + `shots_all.json`（373 镜）+ 参考帧 v3（去字）已就绪；全量 373 镜曾启动后主动叫停。
  **当前停在「6 镜审查」**：3 部各出剧情镜 + 产品镜（`_remake/六镜审查.html`），确认后再铺量。

---

# 追加（2026-09-19 下午）· 参考帧零文字是硬门槛

## ★★ 参考帧有字 = 成片必抄（实测）

模型会把参考帧里的硬字幕**原样画进成片**（不是幻觉）。所以「参考帧零文字」是复刻的前置条件，不是优化项。
判别方法（`check_band.py`）：量字幕带 `edge = mean|Laplacian|` 与黄字像素占比，**参考帧带内偏高 = 泄漏**；
参考帧干净但成片有字 = 真幻觉。**先用这个分辨，别一律归给模型。**

## ★★ v3/v4 清洗漏检 9+ 帧（含 6 帧顽固）

`prep_refs_v3/v4` = `find_hits` 出框 → `stroke_mask` 框内取「亮字+深描边」→ `inpaint(NS)`。两个死穴：
1. **框漏/框歪** → 掩码没盖到字（报告里 `sub` 有命中，字还在）；
2. `stroke_mask` 掩码边界就是**字的黑描边** → `inpaint` 从边界取色 → **填成黑块**。

## ★★ 解法 `rescrub_sub.py`：靠「字幕位置固定」而非检测框

1. 实测硬字幕含描边落在 **y 866–982**，横跨整幅宽、居中；
2. **检测带与掩蔽带分开**：`STRIP=(866,986)` 只算列密度；`MASK_BAND=(850,1010)` 实际掩蔽；
3. **计数判据**：带内「列密度 > 0.60 的**列数**」→ 真字幕 **16~53**，其余帧 **≤13** → 阈值 **15**；
4. **整幅宽掩蔽** + **竖向线性渐变填充**（`vgrad_fill`，取带外上下各 6 px 邻带均值沿 y 插值）。

阈值踩坑：`0.04` 误判 **93.8%**（整带糊掉）；`0.40` 误判 9 帧；`0.60`+窄带 → 只剩 6 帧全为真。

| 坑 | 现象 | 原因 |
|---|---|---|
| 行带太窄（880-986） | 留**黄色横条** | 切掉字幕头部 14 px，残字被 inpaint 边界带成黄条 |
| 行带太宽（856-1005） | 掩码**碎成条状** | 字幕只占带高 2/3 → 列密度 0.9→0.4，与背景列混 |
| 按热列取 x 范围 | 末尾 1-2 字残留 | 边角字列密度掉到阈值下 |
| `stroke_mask`+inpaint | **黑块** | 描边本身就是黑的 |

产物：`full_ref2_v5/` `full_first5/` `full_last5/`（各 373 帧，命中 6/5/1 帧）；
`build_wf_v2.py --ref_suffix _v5 --first_dir dy_full_first5 --last_dir dy_full_last5`。
