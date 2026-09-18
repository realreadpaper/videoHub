# MiniMax-H3 画质提升：从 768p 到 1080p 的可行路径

> 调研日期：2026-09-18 · 面向本项目现状：**Ref2VA（产品参考图）+ int8_convrot pruned + Ref2V turbo 4-step v0.1（544p 训练）+ 一步直出 768×1344 + A100-PCIE-40G**
> 标注：**事实**（有原文）／**推论**（本文算术）／**未知**。来源链接见文末。

## 一、四条结论

1. **本地开源权重（H3-Base）的硬上限就是 768p。** 官方 ComfyUI 文档原话：1344×768 是原生画布，"1.0 Megapixels（1376×768）**已超过模型的 768×1344 像素面积上限**"。官方模型卡也写明 H3-Base「producing results at **768p** resolution」。
2. **官方唯一的 1080p/2K 路径是 H3-Regenerate-2K，且没有开源。** 它不是超分模块，而是「把 768p 结果连同原始多模态 context 再喂回 H3 重新生成」，官方称这样才能"恢复小字和细节"（常规超分只能猜）。**只提供 API**；HF 上只有 `t2va`、`i2va` 两个本地 `full-2k-*-h3-regenerate-2k.sh`，**Ref2VA 没有**——Ref2VA 的 2K 官方样例是直接调 Open Platform API（`resolution: "2K"`）。
3. **本地想生成式地到 1080p，只有一条路：低分辨率草稿 → 潜在空间放大 → 高分辨率重采样。** 社区已有 H3 专用 latent upscaler + 现成 R2V 工作流，且其 megapixels 表最高标到 **2.0 MP = 1920×1088**。但它有代价：H3 要在超出训练面积 2× 的尺度上跑（无官方质量背书），且撞 40 GB 显存墙。
4. **对"产品字/小字"这类细节，升分辨率不是解。** 要么走 API 2K，要么把真实产品像素**合成**进去（官方 ComfyUI 的 Fun ControlNet Union 支持 mask 视频修补，可在高分辨率下做）——这是你们四杠杆里唯一 100% 保真的一条。

## 二、官方口径（事实）

| 项 | 官方说法 |
|---|---|
| H3-Base（开源） | 768p；短边默认 768；分辨率对齐 32 的倍数；24fps；≤15 s（`17n+5` 帧栅格） |
| H3-Regenerate-2K | 768p 结果 + 原始 context → 重新生成到 2K；**未开源**，给 API |
| H3-Context-IR | 多阶段工作流，**未开源**，给 API |
| 稀疏注意力 | "natively supports sparse-attention training and inference"，但**首个开源版本只有 full attention**，稀疏实现后续单独发布 |
| ComfyUI 面积上限 | 768×1344 像素面积；`Resolution Selector` 的 Megapixels 不要填 1.0 |
| R2V 参考图尺寸 | 官方/lightx2v 都推荐 `match`（与训练同口径）——你们已在用 |
| H3 2K API | `POST /v2/video_generation` + `"resolution": "2K"` + `"ratio": "adaptive"`，内容用 `content[]`（text / video_url role=reference_video / audio_url role=reference_audio） |

`H3-Regenerate-2K` 的 API：`/video-generation-v2-regeneration`（EN/CN 平台文档均有）；价格与 Ref2VA 支持范围**未知**，需查平台。

## 三、本地三条路线（按推荐度）

### A. 潜在放大 + 高分辨率重采样（唯一本地生成式 1080p 路线）

- 模型：[LBH-123-AI/Minimax_h3_latent_Upscaler](https://huggingface.co/LBH-123-AI/Minimax_h3_latent_Upscaler)（Apache-2.0，bf16 691 MB，30 天 22 万下载）
  - 直接作用在 **H3 的 24 通道 VAE latent** 上做空间放大，时间维不动；3D 卷积 + 时序卷积 + 三线性插值，3.45 亿参数
  - 避开 `decode → 像素放大 → encode` 的往返（H3 视频 VAE 约 5B 参数，往返很贵），也避开朴素插值的**重影/双影**
  - 放大倍数 **1.0×–4.0× 连续**（0.1 步进，默认 2.0×）
  - ComfyUI 节点：[LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler](https://github.com/LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler)，放 `models/latent_upscale_models/`
- **现成 R2V 工作流**（`workflow_templates/minimax_h3_r2v_Latent Upscaler example workflow3.json`）实测拆解：
  - 草稿：`MiniMaxH3ReferenceToVideo` 1344×768 / 124 帧 / `match`，但经 `ResolutionSelector` 压到 **0.2 MP（608×352）**
  - 采样 1：`SamplerCustomAdvanced` + `MiniMaxH3SigmaShift[12,3]`，sigmas 取 8 步调度的前半段
  - 放大：`MinimaxH3LatentUpscaler3D`，模式 `megapixels`，目标 **1（MP）**，multiple=32
  - 采样 2（重采样）：`ManualSigmas = [0.9035, 0.6316, 0.3158, 0.0000]`（4 步），从放大后的 latent 重新去噪
  - 即：**低噪草稿省时 → latent 放大 → 在目标分辨率上重新生成细节**（与官方 Regenerate-2K 同思路，只是用社区放大网络替代）
- 节点自带 megapixels→分辨率表（16:9）：0.2→608×352、0.5→960×544、0.98→1344×768、**2.0→1920×1088**
- **推论**：把采样 2 的目标从 1.0 MP 提到 2.0 MP，就得到 1920×1088。风险三条：① H3 在 2× 训练面积上跑，质量无背书；② 显存（见第五节）；③ 放大网络的泛化只在 1–4× 连续范围内、按 80k 对样本训练（含 8k 2K 图像对），视频 2× 是主训练档位（40% 占比）。

### B. 激活分块 / 稀疏注意力：让 2 MP 塞进 40 GB

- [star7code/minimax-h3-chunk-star7](https://github.com/star7code/minimax-h3-chunk-star7)：QKV / RoPE / MLP **三处激活独立分块** + 注意力后端可选
  - 关键：**SM75 用自带原生 CUDA 核，SM80+ 用 Triton 或 NVIDIA 官方 Sol-Attn** —— 这对 A100(SM80) 不是 SageAttention 那条 NaN 路
  - 作者明说："分块降低的是推理临时激活峰值，不减少模型权重、帧数或 token，也不改变采样器、latent、VAE、时长和输出分辨率"；"如果任务原本可以完整驻留显存，分块不一定更快；**当原任务会 OOM、进入共享显存或频繁换页时，分块才更可能改善实际吞吐**" —— 正是 1080p 场景
  - 附带 NaN/Inf 分段诊断（QKV / attention / out_proj / MLP），便于定位
- 稀疏注意力补丁：SLA（动态 Top-K 块路由，视频查询保留约 15% K 块）、Sol（选中块精确 + 未选中块质心近似）
  - 配套 LoRA：[lightx2v/Minimax-h3-Turbo-SLA](https://huggingface.co/lightx2v/Minimax-h3-Turbo-SLA)（4 步蒸馏 + 85% 注意力稀疏，作者实测 RTX 5090 上 ~2.5×）——**目前只有 FL2V 版本，没有 Ref2V**，你们的产品镜用不上，但值得盯
- 未验证的社区件：`Slacking-engineer/ComfyUI-VDN-H3`（Video Delta Net 混合注意力，★ 少）

### C. 非生成式超分（交付最稳，但不创造细节）

- [numz/ComfyUI-SeedVR2_VideoUpscaler](https://github.com/numz/ComfyUI-SeedVR2_VideoUpscaler)（★2856，ByteDance SeedVR2 官方 ComfyUI 移植，支持多卡 standalone CLI）+ 分块拼接节点（`moonwhaler/comfyui-seedvr2-tilingupscaler`、`BacoHubo/ComfyUI_SeedVR2_Tiler`）解决显存
- 官方也承认：常规超分只能"猜"细节，小字/产品字无效
- 你们已有的 **LTX-2.5 精修到 1920×1088**（NVIDIA Sol-Engine 包）属于这条路，实测"糊/涂抹"已否掉

## 四、分辨率之外更值钱的画质杠杆（ComfyUI 官方原生节点）

| 手段 | 能解决什么 | 与本项目的关系 |
|---|---|---|
| **Multiframe Reference / Add Guide** | 在时间轴指定帧号钉住静帧（可带音频），做多镜延续、身份锚定 | 直接对口 24 镜一致性与跨镜空间坐标（你们的 S3 硬标准） |
| **Fun ControlNet Union**（alibaba-pai，Comfy-Org 打包） | canny/depth/hed/mlsd/pose 控制视频 + **mask 视频修补**；`fl2va`/`ref2va` 均可挂 | 就是"产品区域合成贴图"的官方做法，可在高分辨率下修补产品区 → 唯一 100% 保真 |
| R2V `match` 参考图尺寸策略 | 与训练同口径，避免参考图被裁/缩放失配 | 已在用 |
| 官方 prompt guide | 提示词结构（含音频/镜头） | 你们早有更严的自建四条硬标准 |
| 未来：官方稀疏注意力开源 | 长序列成本 | 发布后再评估 |

## 五、显存账：为什么 1080p 在 40 GB 上难（**推论**）

官方模型卡：H3-VisualVAE 为 `f16t4d24`（空间 16×）+ patchify `1×2×2` → **有效空间下采样 32×**。

| 画布 | 每帧 token | 124 帧（temporal 4× → 31 帧）总 token | 相对 768×1344 |
|---|---|---|---|
| 768×1344（1.03 MP） | 24 × 42 = 1008 | ≈ 31k | 1× |
| 1664×928（1.5 MP） | 52 × 29 = 1508 | ≈ 47k | 1.5× |
| **1920×1088（2.09 MP）** | **60 × 34 = 2040** | **≈ 63k** | **2×（attention 约 4×）** |

你们 09-17 实测：768×1344 时 S1 峰值 **40353/40960 MiB（98.5%）**。所以：

- 直接一步直出 1920×1088 在 40 GB 上**基本不可能**（除非权重与文本编码器不同时驻留 + 激活分块）
- 走「0.2 MP 草稿 + latent 放大 + 2 MP 重采样」时，2 MP 采样那一步仍要面对 2× token
- 三条减负路径：① chunk-star7 激活分块；② 降到 1.5 MP（1664×928，+44% 像素，3×2 对齐）；③ 双卡 SP/FSDP（见 `h3-acceleration-2xa100.md`——在 1080p 场景下多卡的价值从"提速"变成"能不能跑"）

## 六、建议的 A/B 实验序列（只改一个变量，全部可回滚）

| # | 变量 | 目的 | 判据 |
|---|---|---|---|
| T1 | 0.2 MP 草稿 → latent 放大到 **1.0 MP** → 4 步重采样 | 社区配方是否在你们管线里**又省时又提画质** | 总耗时 vs 631 s；三项量化质检 + 目视 |
| T2 | 同上，目标改 **1.5 MP（1664×928）** | 超面积生成是否开始崩 | 显存峰值、结构崩坏（手/脸/道具）、目视 |
| T3 | 同上，目标 **2.0 MP（1920×1088）** | 1080p 本地可行性 | 若 OOM → 装 chunk-star7 的激活分块再试 |
| T4 | 产品镜：Fun ControlNet Union 的 **mask 修补**，把真实产品像素合成进 1080p 画布 | 交付级产品保真 | 像素级对照（产品区 SSIM），不靠生成 |
| T5 | 对照：官方 API `resolution:"2K"`（Ref2VA 直出） | 官方质量上限的参照系 | 拿 1–2 个镜头做基准，别整批 |

## 七、一个需要复核的口径（重要）

官方模型卡给的是 **32× 有效空间下采样**（16× VAE + 1×2×2 patchify），768×1344 → **24×42 = 1008 token/帧**。
你们 09-17《产品高清方案》里用的是「VAE 空间压缩 **8 倍** → 96×168 latent 格子」。

- 如果那个 8× 指的是 **LTX-2.5 阶段**（LTX VAE 确为 8×），没问题；
- 但如果用它推 **H3 阶段**"产品字能不能画出来"的格子账，就要按 32× 重算：产品占 226 px 宽 → 226/32 ≈ **7 个 token 宽**，一列竖排文字连 2 个 token 都不到。
建议直接打印一次 H3 节点实际 latent shape 核对，这会影响"文字道具是否写进 prompt"的判据。

## 八、未解决 / 会改变结论的事

- **没有任何公开的 H3 本地 2 MP 出片案例与对照**（含 LBH 工作流作者自己，megapixels 表到 2.0 但公开示例是 1 MP）
- **Regenerate-2K API 的价格、并发、是否接受 Ref2VA 输入**：未见公开说明，需在平台文档/控制台确认
- **chunk-star7 没有 A100 实测数字**（只有机制说明）
- 「超训练面积生成」的画质上限未知：可能 1.5 MP 就是本地拐点
- 官方稀疏注意力开源时间未知

## 九、来源

- MiniMax-H3 官方模型卡（H3-Base 768p / H3-Regenerate-2K 未开源 / in-context 恢复小字 / 稀疏注意力未开源 / VAE f16t4d24 + patchify 32× / Full 2K Workflow 与 API 端点）：https://huggingface.co/MiniMaxAI/MiniMax-H3
- 2K API 请求样例（Ref2VA 直出 2K）：https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/scripts/readme/full-2k-ref2va-h3-api-2k-in-open-platform-for-reference.sh
- ComfyUI 官方 H3 总览（**768×1344 面积上限**、分辨率选择、Sage Attention）：https://docs.comfy.org/tutorials/video/minimax/minimax-h3
- ComfyUI 官方 H3 原生工作流与高级技巧（guide 锚定、latent noise mask、模型清单）：https://docs.comfy.org/tutorials/video/minimax/minimax-h3-native
- ComfyUI 官方 Multiframe Reference（时间轴锚定帧）：https://docs.comfy.org/tutorials/video/minimax/minimax-h3-multiframe
- ComfyUI 官方 Fun ControlNet Union（控制视频 + mask 视频修补）：https://docs.comfy.org/tutorials/video/minimax/minimax-h3-fun-controlnet
- LBH 潜在放大器（24 通道、1–4×、R2V 工作流、megapixels 表到 1920×1088）：https://huggingface.co/LBH-123-AI/Minimax_h3_latent_Upscaler
- chunk-star7（QKV/RoPE/MLP 激活分块；SM75 原生 / SM80+ Triton 或 Sol-Attn；SLA/Sol）：https://github.com/star7code/minimax-h3-chunk-star7
- Turbo-SLA LoRA（85% 稀疏、4 步、仅 FL2V）：https://huggingface.co/lightx2v/Minimax-h3-Turbo-SLA
- SeedVR2 ComfyUI（通用视频超分 + 分块拼接）：https://github.com/numz/ComfyUI-SeedVR2_VideoUpscaler
- MiniMax-H3 Turbo 规格表（Ref2VA 4-step v0.1 = 544p 训练）：https://github.com/ModelTC/Minimax-H3-Turbo
- 本项目既有实测：《产品高清方案》（像素门槛、四杠杆）、《768×1344 加速实测》（631 s 分解）、《h3-acceleration-2xa100.md》（双卡）
