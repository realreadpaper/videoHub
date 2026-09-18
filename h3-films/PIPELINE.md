# 双片流水线排产 · 全 H3 生成

> 两部抖音复刻片全部由 H3 生成画面，本地只做编排。远程出完片 1 立刻转片 2，
> 本地同时处理片 1 —— 远程机时不空转。

## 一、两片参数

| 项 | 片 1 | 片 2 |
| --- | --- | --- |
| 工程 slug | `douyin-office` | `douyin-blinddate` |
| 片名 | 良心面试 · 食堂红烧 | 相亲这场 · 一包搞定 |
| 时长 | 286 s（原片） | 296.9 s（原片） |
| **镜数** | **20 镜 × 15 s = 300 s 素材** | **20 镜 × 15 s = 300 s 素材** |
| 卖货段 | 镜 13–18（84 s 口播） | 镜 8–14（105.5 s 口播） |
| seed | 20260916 | 20260917 |
| 分辨率 | stage1 `384×672` → stage2 `768×1344` | 同左 |
| 生成帧率 | 24 fps（`h3_length 362` / `refined 361`） | 同左 |
| 成片帧率 | 30 fps（本地转换） | 同左 |

两片都是 **9:16 竖版**。分辨率已从模板的横版（672×384 / 1344×768）改为竖版，
像素量不变，**耗时与横版持平，不会更快**。

## 二、耗时基线

单镜固定 15 秒。实测冷热对照：

| 阶段 | 冷启动（首镜） | 热跑（第二镜起） |
| --- | --- | --- |
| 草稿 Stage1 · 384×672 | 120.6 s | 72.5 s |
| 精修 Stage2 · 768×1344 | 167.7 s | 90.6 s |

**单片的两个批次：**

```
草稿批次 20 镜 = 120.6 + 19 × 72.5 = 1498.1 s = 24.97 分
精修批次 20 镜 = 167.7 + 19 × 90.6 = 1889.1 s = 31.49 分
                                    单片合计 = 56.45 分
```

若用默认交替跑：`20 × 288.3 = 5766 s = 96.1 分` —— **多付 39.6 分**，纯浪费。

## 三、重叠排产

```
T+00:00  远端  起 ComfyUI + 片1 草稿批次（20 镜）开始
T+00:25  远端  片1 草稿完成
T+00:25  远端  片1 精修批次（20 镜）开始
T+00:56  远端  片1 精修完成 → final/shot01..shot20.mp4
T+00:57  回传  片1 的 20 个成镜拉回本地（约 600 MB）
T+00:58  远端  ▶ 立即提交片2 草稿批次          ← 远程不停
T+00:58  本地  ▶ 片1 处理：拼接 → 转竖版/30fps → 换 A-roll → hypit 出片
T+01:05  本地  ✓ 片1 成片交付
T+01:23  远端  片2 草稿完成
T+01:23  远端  片2 精修批次开始
T+01:54  远端  片2 精修完成
T+01:55  回传  片2 成镜拉回本地
T+01:55  本地  片2 处理
T+02:02  本地  ✓ 片2 成片交付
```

**端到端约 122 分钟（2 小时 2 分）。**

## 四、重叠到底省多少 —— 说清楚，别高估

| 方案 | 总时间 | 对比 |
| --- | --- | --- |
| 完全串行（不重叠） | 127.9 分 | — |
| **重叠（本方案）** | **121.9 分** | **省 6 分** |

**只省 6 分钟，原因很直白**：本地处理只有约 6 分钟，而生成占 56.5 分钟。
重叠的上限就是「本地处理时长」——`min(6, 56.5) = 6`。

所以这个并行的价值**不在省时间**，而在于：

1. **片 1 到手后你能立刻判断质量、决定是否重跑某几镜**，而片 2 已经在跑，机时不浪费
2. **全程可无人值守**：睡前提交，早上收两片
3. 流程解耦：本地脚本报错重跑，不占用远端窗口

### 真正能压缩总时间的手段

| 手段 | 效果 | 代价 |
| --- | --- | --- |
| **拆两批跑**（已采用） | 96.1 分 → 56.5 分，**省 39.6 分** | 无，纯赚 |
| 降 stage2 分辨率到 `640×1152` | 约省 20–25% | 画质下降，且要重验帧数栅格 |
| 只跑单阶段（跳过草稿） | 约省 25 分 | LTX 需要草稿做结构引导，**可能崩**，须先单镜对照 |
| 减少镜数 | 线性减少 | H3 单镜固定 15 秒，只能靠删内容 |

**唯一无代价的优化就是拆两批。** 其他的都要拿质量换。

## 五、远端执行

工程已投送完毕（`bash deploy.sh` 已跑过）：

```
/workspace/films/douyin-office/      10_run_film.py + manifest.json + workflows/
/workspace/films/douyin-blinddate/   同上
```

**第 0 步 · 先跑一镜验竖版（必做，约 5 分钟）**

```bash
cd /workspace/films/douyin-office
/workspace/venv/bin/python 10_run_film.py --shots 1 --stage both --force
```

H3 主训在 16:9，竖屏构图是否成立、人物是否变形，必须先看这一镜。
**这一镜不过关，就不要提交后面 39 镜。**

**第 1 步 · 片 1 两批**

```bash
cd /workspace/films/douyin-office
/workspace/venv/bin/python 10_run_film.py --stage draft  --shots 1-20
/workspace/venv/bin/python 10_run_film.py --stage refine --shots 1-20
```

**第 2 步 · 片 2 两批**（片 1 回传后立即执行）

```bash
cd /workspace/films/douyin-blinddate
/workspace/venv/bin/python 10_run_film.py --stage draft  --shots 1-20
/workspace/venv/bin/python 10_run_film.py --stage refine --shots 1-20
```

**可选 · 远端直接合成全片**

```bash
/workspace/venv/bin/python 10_run_film.py --concat
# 输出：/workspace/films/douyin-office/良心面试_食堂红烧_全片.mp4
```

## 六、本地处理

### 1. 回传成镜

```bash
mkdir -p ~/Desktop/videoHub/h3-films/film1-office/shots
sshpass -e scp -P 23 -r root@117.50.188.156:/workspace/films/douyin-office/final/shot*.mp4 \
  ~/Desktop/videoHub/h3-films/film1-office/shots/
```

### 2. 拼接 + 转竖版 720×1280 + 转 30 fps

768×1344 与抖音标准的 720×1280 不是严格等比（4:7 vs 9:16），
用「缩到高 1280 → 居中裁到宽 720」，每边只裁 6 px，几乎无损：

```bash
cd ~/Desktop/videoHub/h3-films/film1-office/shots
printf "file '%s'\n" "$PWD"/shot*.mp4 > list.txt
ffmpeg -y -f concat -safe 0 -i list.txt \
  -vf "scale=-2:1280,crop=720:1280,fps=30,setsar=1" \
  -c:v libx264 -crf 16 -preset medium -pix_fmt yuv420p \
  -c:a aac -b:a 192k -ar 48000 -ac 2 \
  ../a-roll-720x1280-30fps.mp4
```

### 3. 接回现有 hypit 工程

现有工程不用大改，**只换 A-roll 素材路径**：

| 片 | hypit 工程 | 要替换的素材 |
| --- | --- | --- |
| 片 1 | `videos/douyin-ad/productions/ad-clone/assets/` | `ad-segment.mp4` → 新 A-roll |
| 片 2 | `videos/douyin-ad-2/productions/ad-clone/assets/` | 同左 |

图形层（痛点条 / 五步条 / 价格卡 / CTA）沿用现有 `main.svml`。

> **顺带一个变化**：原片烧死的字幕、免责声明、红箭头**都没有了**。
> 图形层不必再挤在顶部 2%–12%，可以重新落位。但第一版建议先保持工程不动跑通，
> 拿到成片后再优化位置。

### 4. 口播音轨

全片生成后原片音轨不可用，需重新配音：

- **剧情段（片 1 镜 1–12、19–20；片 2 镜 1–7、15–20）**：H3 已按 prompt 里的
  `<d>[Chinese] "..."</d>` 生成台词与口型，直接用其原生音轨。
- **卖货段（片 1 镜 13–18；片 2 镜 8–14）**：prompt 里已全部写死
  `No speech`，画面只做讲解姿态，口播由 Edge TTS 或真人录，后期由 hypit 混轨。

台词稿见各片的 `SCRIPT.md`。

### 5. 出片

```bash
cd ~/Desktop/videoHub/videos/douyin-ad
bash render-clone.sh      # 或 render-local.sh，见该工程说明
```

字幕按用户长期约定**外挂 `.srt`，不烧入画面**。

## 七、风险与回退

| 风险 | 表现 | 回退 |
| --- | --- | --- |
| **竖版构图崩** | 第 0 步单镜里人物畸形、构图失衡 | 回退横版生成（改回 672×384 / 1344×768），本地裁切取中间 9:16 |
| **帧数栅格** | 未改动（保持 362 / 361），风险已规避 | — |
| **产品包装失真** | 卖货段的产品特写假 | 该镜改实拍，或后期用 hypit 贴自有产品图覆盖 |
| **口型对不上** | 卖货段 TTS 配音与人物口型不同步 | 卖货段改用画外音 + B-roll 特写覆盖人物嘴部 |
| **显存不足** | 报 OOM | 已在模板内沿用既有配置，未加码；降 stage2 分辨率 |
| **镜数超预算** | 20 镜素材 300 s，成片只需 286/296.9 s | 每片多出 3–14 s，后期剪掉即可 |

## 八、待你确认

1. **第 0 步单镜什么时候跑？** 现在跑，5 分钟出结果，验完再决定是否提交 39 镜。
2. ~~**产品怎么定？**~~ **已定（2026-09-16）**：产品不另找素材，直接用两条参考视频里
   提取出来的真实产品画面 —— 两片其实是**同一品牌同款**：「醉锅里 · 鲍汁红烧酱」。
   素材与规格见 [`_product/PRODUCT.md`](_product/PRODUCT.md)。
3. **口播用 TTS 还是真人？** 影响后期处理方式（TTS 我可以直接接 Edge TTS 生成音轨）。

## 九、产品素材（2026-09-16 更新）

产品取自参考视频抽帧，两片共用一套描述：

| 项 | 内容 |
| --- | --- |
| 产品 | 醉锅里 · 鲍汁红烧酱（半固态复合调味料，自立袋） |
| 素材目录 | `h3-films/_product/`（正面 4× 特写 / 手持 / 桌面 / 原始抽帧） |
| 规格卡 | [`_product/PRODUCT.md`](_product/PRODUCT.md) |
| 替换的产品镜 | 片 1：镜 **12 / 13 / 15 / 16 / 18**　片 2：镜 **8 / 10 / 11 / 14 / 19** |

**两层策略**（关键）：

- **生成层**：prompt 常量 `SP` 已从「深红铝箔袋 + 空白标签」的通用占位，换成对标真实包装的
  **壳描述** —— 鲜亮番茄红镀铝面、米白挂孔顶条、白色弧形色块、下半部红烧肉实拍图、
  袋身折痕与镜面高光；品牌名区域写成 `clean unprinted red field`，
  `no legible lettering / no barcode / no readable characters`。
  目的是让模型画出「像它」，**同时不生成中文乱码**。
- **合成层**：包装上的品牌与品名由后期（hypit）用 `_product/product_front_4x.jpg` 贴图叠加，
  文字 100% 准确、随时可换成自有产品。

> 为什么不让模型直接写中文：生成模型画汉字必出鬼画符，且不可控。这层文字必须靠贴图。

## 十、对白写法（**已废弃** —— 由 §11 的 audio-lock 方案取代，留档备查）

**`<d>[Chinese] 台词</d>` —— 台词两侧绝对不要加英文双引号。**

- 加了引号：`<d>[Chinese] "我赶时间，别挡道。"</d>` → H3 把这行**烧进画面**当字幕，
  而且是模型自造的错字（实测出现「現 / 顧 / 屣 / 嘗」这种混杂异体字），违反「成片不烧字幕」约定。
- 去掉引号：`<d>[Chinese] 我赶时间，别挡道。</d>` → 字幕**完全消失**，语音与口型照常生成。
- 这是节点自带示例库（`examples/`）的写法，用 `grep -rho "<d>[^<]*" examples/` 可自行核对。

`<d>` 标签的官方语义是「逐字台词」，用于驱动语音与口型，**不承担字幕职责** ——
烧字幕纯属引号引入的误触发。两片 25 处已全部修正。

若某镜后续仍发现画面杂字，优先检查该镜 prompt 里有没有其它成对的引号包住中文。

## 十一、抄写重建 + 中文语音（2026-09-16 晚 · 当前口径）

前面的「自己写分镜 + 让模型说中文」已被推翻。现在按**复刻 skill 的原意：100% 抄参考视频**。

### 11.1 四条抄写口径

| 层 | 抄什么 | 产物 |
| --- | --- | --- |
| **台词** | 原片 whisper 逐词转写原文，**逐字照抄** | `_lines/film{1,2}_shot_lines.{txt,json}` |
| **画面** | 按原片接触表**逐拍重建**（白天后门 / 轮椅 / 真人 / 真实后厨） | `p1_data.py` / `p2_data.py` 的 `beats` |
| **时间窗** | 原片 286.13 / 296.93 s 均分 20 镜（每镜 14.31 / 14.85 s） | `align_lines.py` |
| **语音** | 原文逐字喂 TTS（中文），**不靠模型自己说** | `make_tts.py` |

**为什么要逐镜对齐**：原片是连续口播，20 镜是均分窗口。对齐脚本按**词中心点**归属窗口，
保证不切词、不丢字；拼接后与原转写**逐字一致**（见 `_lines/抄写核对报告.md`）。

### 11.2 语音：audio-lock（中文 100% 可控）

**不要再用 `<d>[Chinese] 台词</d>` 让模型说话** —— 实测它不稳（官方只验证过 1 句中文），
且说了什么不可控。正确做法是**把外部中文 TTS 当音轨锁定输入**：

```
Edge TTS（原文逐字）→ shotNN_dry.wav（15s，32kHz 立体声）
   → stage1_audio_lock 工作流（lock_source）→ 草稿音轨 = 该干声
   → stage2 LTX 精修（保留音轨）→ 成片音轨 100% 中文、100% 原文
```

实测证据（镜 5）：喂进去的是 TTS「大爷，您没事吧？」，产物转写回来**就是这一句**，
且人物嘴型跟着音频动 —— `lock_source` 生效，音轨完全可控。

**执行命令**

```bash
# 本地：生成逐镜干声（需 edge-tts 解释器）
/Users/hejianglong/.workbuddy/binaries/python/envs/default/bin/python make_tts.py
# 本地：生成该镜的锁定工作流
python3 build_voice_workflow.py --shot 5 --film film1
# 上传干声 + 工作流，然后远端提交
scp -P 23 _tts/film1/*.wav  root@…:/workspace/ComfyUI/input/tts_dry/film1/
scp -P 23 _remote/stage1_voice_film1_s05.json root@…:/workspace/films/douyin-office/workflows/
ssh -p 23 root@… '/workspace/venv/bin/python /workspace/h3scripts/80_run_workflow_remote.py \
   /workspace/films/douyin-office/workflows/stage1_voice_film1_s05.json --tag VOICE'
```

### 11.3 音频锁定的坑（实测）

| 坑 | 现象 | 修法 |
| --- | --- | --- |
| **clip_name 缺目录前缀** | `/prompt` 返回 400 `value_not_in_list`；`value 'qwen3vl_…' not in ['minimax_h3/qwen3vl_…']` | 设 `minimax_h3/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors`。**UNET 在根目录，不能加前缀**（官方示例模板与磁盘目录布局不一致） |
| **干声必须分片目录** | 两片同名 `shot05_dry.wav` 互相覆盖 | 上传到 `tts_dry/film1/`、`tts_dry/film2/` |
| **load_source 需要窗口** | 不设窗口会取整段音频 | `MiniMaxH3AudioWindowT8` 的第 2 个值设成镜长（15.0833） |

### 11.4 权威产物索引

| 文件 | 作用 |
| --- | --- |
| `align_lines.py` | 逐词 srt → 20 镜时间窗原文（逐字，带完整性校验） |
| `_lines/*_shot_lines.{txt,json}` | 对齐表（人读版 / 机读版） |
| `_lines/抄写核对报告.md` | 全片级核对：相似度 + 逐条订正清单 |
| `patch_lines.py` | 把原文台词写回 `pN_data.py`（只动 dialogue 块，自动校验） |
| `review_diff.py` | difflib 逐处打印「原文 vs 抄写」上下文，用于人工判定增删字是否越界 |
| `make_tts.py` | 原文逐字 → 中文干声（v3：裁首尾静音 + atempo 兜底 + 实测排布） |
| `verify_tts.py` | 用本地 whisper.cpp 把干声转写回来，逐字比对原文（质量门） |
| `check_tts_len.py` | 读 `shotNN_lines.json` 的实测 `dur`，校验 40 镜全部落在 15.0833s 窗内 |
| `build_voice_workflow.py` | 生成 audio-lock 工作流（含 seed / 分辨率 / 窗口） |
| `deploy_voice.sh` | 一键投送：先清远端旧货，再送 40 工作流 + 两片干声 + runner |
| `batch_all.sh` | 两片全量：`draft 20 → refine 20 → concat`，串行用 GPU |
| `11_run_voice_film.py` | **远端**锁音轨驱动：stage1 audio-lock 草稿 → stage2 LTX 精修 → concat |

> 台词订正原则：**只订正 ASR 明显错字**（如「主管港」→「主管岗」、「电饭波」→「电饭锅」、
> 「灵测糖」→「0 蔗糖」），不改写、不删减、不并句。所有订正逐条列在核对报告里可复查。

### 11.4.1 怎么跑（本地 → 远端，单镜验 → 批量）

```bash
# 1) 本地：合成干声（v3）+ 校验时长 + 抽验内容
/Users/.../envs/default/bin/python make_tts.py --rate 40   # 两片 40 镜干声
/Users/.../envs/default/bin/python check_tts_len.py        # 必须「全部落在 15.0833s 窗内」
/Users/.../envs/default/bin/python verify_tts.py           # whisper 反写逐字比对（可选）

# 2) 本地：清远端旧货 + 投送（干声 + 40 工作流 + runner）
SSHPASS=... bash deploy_voice.sh

# 3) 远端：单镜全链路验证（锁音轨草稿 ~110s + LTX 精修 ~140s）
ssh -p 23 root@117.50.188.156
cd /workspace/films/douyin-office
/workspace/venv/bin/python 11_run_voice_film.py --film film1 --shots 5

# 4) 批量（两片；GPU 串行）
SSHPASS=... bash batch_all.sh          # draft 20 → refine 20 → concat，两片
```

> ⚠ **prompt 或干声一变，远端旧草稿/成片必须全部作废** —— `deploy_voice.sh`
> 已内置清空 `output/MiniMaxH3/<slug>/`、`final/*.mp4`、`logs/*.log`、`input/tts_dry/<film>/*.wav`。
> 否则 `find_draft()` 会把上一版 prompt 的产物当成本镜草稿复用。

产物命名：草稿 `output/MiniMaxH3/<slug>/voice_sNN_00001_.mp4`；精修 `final/shotNN.mp4`。

### 11.5 抄写完整度实测

| 片 | 原片转写 | 抄写稿 | 相似度 | 差异 |
| --- | --- | --- | --- | --- |
| 片 1 | 1696 字 | 1698 字 | **0.9823** | 25 处 |
| 片 2 | 1679 字 | 1678 字 | **0.9836** | 25 处 |

**逐处复核（`review_diff.py`，逐条打印上下文）** —— 差异全部定性为 **ASR 错听订正，无一处臆造**：

- 绝大多数是**等长同音替换**：港→岗 / 波→锅 / 灵测→0 蔗糖 / 故事→顾氏 / 极具→集剧 / 扇→善 …
- 少数「增删字」均为 ASR 边界问题，方向都是**向原片真实台词靠**：
  - 补漏字：「公司不是救助**站**」、颜色也红亮「**你**」自己做的、点击左「**下**角」、
    「电**饭**锅内胆」、「红烧鱼、炖**牛肉**、炖羊肉」
  - 删幻觉重复：「不用了**了**」→「不用了」、「补偿我了**了**」→「补偿我了」、删多余的「电点」
- 唯一主动优化：镜 06 补回原文的「**垫垫**」（ASR 误识为「电点」）


### 11.6 角色锚定（2026-09-16 晚 · 关键修复）

**症状**：跨镜人脸漂移、主角年龄/身份错 —— 实测镜 05 里 65 岁的顾董被画成了年轻西装男。

**根因**：H3 是**单镜生成**，而 40 镜里最初只有 2 镜（片1 镜01、片2 镜16）的 prompt 带了角色外貌描述；
其余镜里角色只以裸标签 `S1/S2/S3` 出现，**模型每镜都在自由发挥**。这正是「角色没保持一致」的根因。

**处置**：在 `pN_data.py` 的 `_prompt()` 里自动注入「角色锚定块」：

- 从 `beats + sound` 文本按词边界识别出场标签（`S2K` / `S2_STAND` 优先于 `S2`，避免前缀误配）
- 在 `integrated_multimodal_description:` 之后插入一整行：
  `<Character reference — every subject below keeps exactly the same face, hair, age, build and
  clothing in every shot of this film: <Subject 1> (S1), …; <Subject 2> (S2), …>`
- 画面里出现 `pouch / packet / sachet` 时自动补锚定产品 `SP` → 跨镜产品外观一致
- `_shot(..., cast=[...])` 可显式指定（片2 镜16 男孩站起来那镜用 `S2_STAND`）

**验证**：两片 40 镜中 38 镜带完整锚定；余 2 镜（片1 镜16、片2 镜10）是纯手部/锅内特写，
无人脸、无产品袋入画，按设计不需要锚定。

### 11.7 TTS 时长布局（make_tts v3 · 当前口径）

**症状**：40 镜里 **38 镜语音超出 15.0833s 窗**（最长 16.67s），干声尾巴会盖到下一镜 → 台词听不全。

**v2 的错误假设**：以为溢出是「TTS 语速太慢」，于是写了一套「迭代加速到 +90%/+150%」。
v3 实测推翻了它 —— 溢出跟语速基本无关，真正的两个根因是：

1. **edge-tts 的 `rate` 在 `+50%` 处封顶**（实测同句 `+50% / +100% / +200%` 时长完全一致，
   都是 1.872s）。所以 `MAX_RATE=150` 是假的，v2 那几轮「加速」全是无效空转。
2. **每句 TTS 产物的首尾都垫着 0.4–0.9s 静音** —— 实测「束一半了。」总长 1.872s，
   真实语音只占 `0.184s → 0.995s`（**0.81s**），尾部 0.88s 全是静音。
   8 句一镜就白扔 5–7s。**这才是 38 镜超窗的真凶。**

**v3 处置**（`make_tts.py` 重写）：

| 步骤 | 做法 |
| --- | --- |
| A. 合成 | 默认 `rate=+40%`（edge-tts 有效区间内，听感比 atempo 更干净） |
| B. **裁静音** | `silencedetect`（-45dB/0.05s）定位语音区间 → `atrim` 裁掉首尾静音，保留 0.03/0.06s 呼吸 |
| C. 排布 | 按裁剪后**实测时长**首尾相接，句间留白均分，落在 `[0.06, 0.75]s` |
| D. **atempo 兜底** | 若裁剪后仍塞不下，用 ffmpeg `atempo` 变速（不受 edge-tts 限制、不改音高），数学上保证 `end ≤ 窗长` |

**效果**：镜 05（8 句、台词密度最高）由 **15.96s → 14.82s**，且 `+40%` 时**无需任何变速**；
全片语速从 v2 的「顶到 +90%」回落到统一 `+40%`，听感自然得多。

**两个配套工具**：

- `check_tts_len.py`：⚠ 旧版量的是**原始 mp3** 时长（含静音）会误判超窗，已改为读
  `shotNN_lines.json` 里落盘的实测 `dur`。
- `verify_tts.py`：把干声用 whisper.cpp 转写回来逐字比对原文 —— 实测镜 05 转写
  「数一半了大爷您怎么摔地上了…」与原文**逐字一致**（「束」被判为同音字属 ASR 正常现象）。

## 十二、当前状态与待你确认（2026-09-16 深夜）

**已完成**：
1. ✅ 100% 抄写（台词逐字、画面照原片接触表、时间窗均分 20 镜），相似度 0.98+，逐处复核无臆造；
2. ✅ 角色锚定 + 场景锚定注入（40 镜全覆盖），实测镜 05 顾董/轮椅/年轻女主/后门场景全部修正；
3. ✅ 单镜全链路验证通过：镜 05 草稿 76.5s + 精修 137.3s → `final/shot05.mp4`（768×1344，音轨 100% 中文）；
4. ✅ TTS 时长口径修正（v3 裁静音 + atempo），超窗从 38 镜降到 0。

**待你定**：
1. **口播音色**：`make_tts.py` 按角色分配了音色（顾董沉稳老年男声 / 林晚晴年轻女声 /
   阿姨温柔女声 / 小孩童声…），试听后要换随时改 `VOICES` 表。
2. **画面自造文字**：prompt 已写死 `no subtitles / no printed words`，但实测**压不住**
   （镜 5 文件上仍出现伪字）。原片本身也带免责声明水印，本就要重做图形层 → 后期统一扫残字。
3. **是否立刻起批量**：`batch_all.sh` 已就绪，两片 40 镜 × (草稿+精修)，GPU 串行。


## 十三、日间实测基线（2026-09-16）

| 口径 | 原估 | 实测 |
| --- | --- | --- |
| 单镜连跑（草稿 + 精修） | 288.3 s | **248 s**（镜 2 / 镜 13）、268 s（冷启动首镜） |
| 草稿 Stage1 | 120.6 s | 107.0 – 120.0 s |
| 精修 Stage2 | 167.7 s | 139.4 – 148.2 s |
| 显存峰值 | — | 23.2 GiB / 24 GiB（安全，无 OOM） |

竖版构图已验证成立（768×1344 / 24fps / 361 帧 / 15.04 s / 双声道），
**不启用「回退横版裁切」的备选方案**。
产品壳只能到「形似」，品牌字与袋身印刷图必须后期贴图或改走 I2VA —— 详见
[`单镜验证报告.html`](单镜验证报告.html)。


