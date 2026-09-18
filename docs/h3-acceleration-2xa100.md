# MiniMax-H3 加速路线盘点 + 双 A100 是否更快

> 调研日期：2026-09-18 · 结论面向本项目现状：**Ref2VA（产品参考图）+ int8_convrot + 4-step Turbo LoRA + A100-PCIE-40G（SM80，无 NVLink）+ ComfyUI 双实例**
> 一手来源链接见文末。区分标注：**事实**（有原文）／**推论**（本文算术）／**未知**。

## 一、结论先行

1. **per-clip**：两张 A100 跑**单个**镜头会更快，但只有 **1.2–1.5×**，不是 2×。
2. **整批**：24 镜总时长**更慢**。保持现在的「双实例各 12 镜」。
   - **升级前（commit f42b24e / kitchen 0.2.33）实测**：590.7 s/镜/卡 × 24 镜 ÷ 2 卡 ≈ **2.0 h**
   - **升级后（v0.36.0 / kitchen 0.2.34）实测**：**469.3 s/镜/卡** × 24 镜 ÷ 2 卡 ≈ **1.56 h（1h34m）**，整批**净省 26 分钟（提速 20.5%）**！
   - 改成单任务双卡：469 ÷ 1.3 ≈ 361 s/镜 × 24 镜 ≈ **2.4 h**
   - 结论不变：仍然是双实例吞吐最高。
3. **真正白拿的单卡核心加速已落地（ComfyUI v0.36.0 + comfy-kitchen 0.2.34）**：
   - 算子级融合：CausalConv3d Norm/SiLU/Pad 合并至 `ck.group_norm_silu_pad3d`，RMSNorm+RoPE 融合至 `ck.rms_rope_split_half`，INT8 GEMM epilogue 融合 SwiGLU / residual。
   - 动态瓦片解码：`tiled_decode` 提升至多 4 tiles 动态批处理并发，temporal chunking 即时释放显存。
   - **实测收益**：单步采样从 131.1s 降至 94.3s（**提速 28.1%**），模型初始化从 128.2s 降至 96.8s，端到端单镜从 590.7s 降至 469.3s。
4. **下一阶段单卡加速预留**：SageAttention patch 路线（−30%，单卡、不影响双实例吞吐）＞ 多卡单任务。
5. **最大的加速包（FastH3 4-step DMD2 + VSA 90% 稀疏）对你的用例不可用**：官方模型卡原话 —— FL2VA / Ref2VA **没有被蒸馏**，且原生 VSA 内核只到 `sm_100a/sm_103a`（Blackwell）。

## 二、加速手段 × 本机可用性

| 手段 | 来源 | 覆盖 Ref2VA | A100-SM80 可用 | 备注 / 实测 |
|---|---|---|---|---|
| ComfyUI v0.36.0 算子融合 | ComfyUI 官方 PR #16187 / #16329 / #16332 | ✅ | ✅ SM80 完美支持 | **已落地实测**：CausalConv3d/RMSNorm/RoPE 内核级融合 + tiled 批处理，采样步均 131s→94s（**-28%**），单镜 590s→469s（**-20.5%**） |
| Turbo 4-step LoRA（本项目在用） | [lightx2v/Minimax-h3-Turbo](https://huggingface.co/lightx2v/Minimax-h3-Turbo) | ✅ `ref2v_turbo_4step_v0.1` | ✅ 纯 LoRA | **训练分辨率 544p**（video/audio shift 12/3，NFE 4） |
| PDD Acc 8-step LoRA | [alibaba-pai/MiniMax-H3-Acc-LoRAs](https://huggingface.co/alibaba-pai/MiniMax-H3-Acc-LoRAs) · [VideoX-Fun](https://github.com/aigc-apps/VideoX-Fun) | ✅ `Ref2VA-Acc-8Step` | ✅ | 阿里 PAI 的 Parallel Decoding Distillation，rank=64 BF16 |
| 8-step 768p Turbo LoRA | lightx2v | ✅ `ref2v_turbo_8step_v1.0_768p`（文件存在，**未列入官方规格表**） | ✅ | 比 4-step 慢一倍；训练分辨率/质量边界需自行核实 |
| int8_convrot 量化权重 | ComfyUI/Kijai 生态 | ✅ | ✅ SM75+ | 已在用（主干 19.53 GB） |
| NVFP4 / FP8 权重 | FastVideo、LightX2V | ✅ | ❌ | FP8 matmul 需 **sm89+**，低于此自动回退 bf16 反量化 → **无收益**（FastVideo 文档原文） |
| VSA-H3 稀疏注意力（0.9） | [FastH3 Preview](https://huggingface.co/FastVideo/FastVideo-FastH3-4-step-Preview-v1-VSA-DataFree) | ❌ **仅 T2VA** | ❌ | 原生核 `sm_100a/sm_103a`；有 Triton 回退但**未在 A100 验证过**。官方口径：单卡 Blackwell 最高 14× |
| SageAttention 2.x | [thu-ml/SageAttention](https://github.com/thu-ml/SageAttention) | ✅ | ⚠️ | 本项目实测：H3 内核硬依赖 INT8 QK + **FP8 PV**，SM80 无原生 FP8 → 全 NaN；`PathchSageAttentionKJ` 只在 MODEL 分支内 patch 可拿 **−30%**（需装 KJNodes） |
| FlashAttention 4 | FastVideo | ✅ | ❌ | sm90+（A100 自动落回 FA2） |
| 区域 torch.compile | [FastVideo optimizations](https://github.com/hao-ai-lab/FastVideo/blob/main/docs/inference/optimizations.md) | ✅ | 理论可用 | **会改数值**：官方 GB200 实测 185.08 → 157.01 s E2E（−15%），但 PSNR 16.67 dB / SSIM 0.7108、逐像素与 eager 不同 → 只能当实验项 |
| TAE 快速解码 | [Kijai/MiniMax-H3-TAE](https://huggingface.co/Kijai/MiniMax-H3-TAE) · [madebyollin/taehv](https://github.com/madebyollin/taehv) | ✅ | ✅ | 只解决解码段（GB10 上解码占 E2E 约 40%）；预览级质量，正式交付需另测 |
| 特征缓存（TeaCache 类） | LightX2V H3 集成 | ✅ | ✅ | 未见 H3 公开数字，需自测 |
| 序列/张量并行多卡 | FastVideo `sp_size`、LightX2V `seq_p_size/tp`、FSDP2 | ✅ | ✅ | 见第三节 |

## 三、双 A100 到底快多少

### 3.1 唯一可引用的 H3 多卡一手数据（FastVideo，两台 DGX Spark 配对，21 GB/s RoCE）

| 场景 | 1 卡 | 2 卡 SP=2 | 加速 |
|---|---|---|---|
| 768×1344×124，冷进程 E2E | 374–393 s | **292 s** | 1.28–1.35× |
| └ denoise | 180–188 s | 122 s | **1.5×** |
| └ VAE decode | 151–156 s | 102 s | 1.5× |
| 512×896×124，热态中位 E2E | 251.4 s | **215.2 s** | 1.17× |
| └ denoise | 94.2 s | 72.4 s | 1.3× |
| 768×1344×345（15 s 片） | — | 587 s | （无单卡对照） |

FastVideo 自己的限定（**原文**）：
- 「**Throughput of many clips.** Two independent 1-GPU jobs still win if you want two videos, not one faster video.」
- 「**FSDP or tensor parallel as a speedup** on this 21 GB/s link」不予承诺（每层 all-gather 走 21 GB/s）
- 「Do not install xDiT for this path」—— FastH3 只有 4 步且无 CFG，PipeFusion / CFG-parallel 没有作用对象
- `num_attention_heads`(56) 必须能被 `sp_size` 整除；SP=4 的 latent consistency 已验，SP=2 未在 A100 上验过

### 3.2 本项目算术（**实测与推论**）

* 升级前基线（commit `f42b24e`）：一步直出 768×1344，单镜 590.7 s/卡，双实例 24 镜 ≈ 2.0 h。
* **升级后实测（ComfyUI `v0.36.0` + `comfy-kitchen 0.2.34`）**：一步直出 768×1344，单镜 **469.3 s/卡**，双实例 24 镜 ≈ **1.56 h（1h34m）**。

| 方案 | per-clip | 24 镜总时长（2 卡） | 备注 |
|---|---|---|---|
| 双实例（升级前基线） | 590.7 s | ≈ 2.0 h | commit `f42b24e` 实测 |
| **双实例（v0.36.0 升级后实测）** | **469.3 s** | **≈ 1.56 h（1h34m）** | **当前最新现状，净省 26 分钟** |
| 单任务双卡 SP=2（按 1.3× 推算） | ≈ 361 s | ≈ 2.4 h ❌ | 仍显著慢于双实例并行 |
| 单任务双卡 SP=2（乐观按 1.5× 推算）| ≈ 313 s | ≈ 2.1 h ❌ | 仍慢于双实例并行 |
| 单任务双卡 SP=2，要打平双实例 | — | 需 >2× 加速 | SM80 PCIe 拓扑下不可能达到 |

为什么达不到 2×：H3 4 NFE 是短任务，通信/同步开销摊不开；SP 只切 DiT 与 VAE，切不动文本编码、资源/LoRA 装配、封装等串行段。A100-PCIE 无 NVLink（P2P 走 PCIe），与上面 21 GB/s 的互联同级，甚至 NCCL 表现可能更差。

### 3.3 什么时候「双卡单任务」才值得

- 单卡**装不下**时 —— 你们不是这种情况（Stage1 峰值 ≈34.7 GB / 40 GB）
- **人在等**的试拍、单镜交付、需要 15 s 满长片（345 帧，显存/时长压力更大）
- 换运行时做对照实验：LightX2V 的 H3 集成（2026-08-07）明确覆盖 **Ref2AV**，含 tensor/sequence parallelism、块级 offload、量化 DiT、feature caching，官方给了单卡与多卡脚本（`torchrun --nproc-per-node=N`）；Minimax-H3-Turbo 仓库另有 **FSDP2 多卡**路径（分片 TE + 当前 transformer，因此**关掉 CPU offload**）

## 四、比多卡更值得先做的三件事

1. **SageAttention 走 KJNodes patch 路线**（−30%，单卡、与双实例并行不冲突）。本项目已定位 NaN 根因是 SM80 无原生 FP8 导致 INT8 QK + FP8 PV 内核输出异常，全局开关必挂，必须在 MODEL 分支内 patch。
2. **Ref2VA 的训练域问题**：`ref2v_turbo_4step_v0.1` 官方规格表写明是 **544p 混合宽高比**训练（shift 12/3，NFE 4），你们按 768×1344 一步直出属分布外。目前只有 **FL2VA** 正式发布了 768p v1.0/v1.1/v1.2（shift 6/3）；HF 仓库里虽然躺着 `minimax_h3_ref2v_turbo_8step_v1.0_768p_bf16.safetensors`，但它**没有出现在官方规格表里**，lightx2v 的 roadmap 仍写着「Improve the visual quality and consistency of Ref2VA and FL2VA Turbo」。可对照该 8-step 768p 权重与 alibaba-pai PDD `Ref2VA-Acc-8Step` 做 A/B（两者都要自行验质量与显存）。
3. **别在冷启上丢时间**：冷启 = 热态 4–5×，批量提交保持热态与主动 free（本项目已有铁律）。

## 五、尚未解决、会改变结论的事

- **没有任何公开的 H3 多卡数据跑在 A100-PCIE（无 NVLink）上**。本文引用的 1.2–1.5× 来自 GB10 配对（21 GB/s RoCE），量级相近但拓扑不同 —— A100 上可能更差。要定论只能在 `kehu` 上跑 A/B（同一 prompt、同 seed、同帧数，`--warmup --repeats 3` 取中位）。
- **LightX2V / FSDP2 在 H3 上的 2 卡延迟数字同样没有公开值**。
- **迁移成本未知**：把本项目的 ComfyUI 栈（int8_convrot 权重 + turbo LoRA + T8 节点）搬到 FastVideo 或 LightX2V 才能用上它们的多卡/缓存能力，这是一次真实的工程改造，不是配置开关。
- **VSA 的 Triton 回退能否跑 SM80**：无任何验证记录；即便能跑，也没有 VSA 训练过的 Ref2VA 权重（gate 矩阵只存在于 VSA 蒸馏的 T2VA 检查点里）。

## 六、来源

- FastVideo，两设备 H3 SP=2 实测与「多片吞吐 vs 单片时延」结论：https://github.com/hao-ai-lab/FastVideo/blob/main/docs/getting_started/installation/spark_pair.md
- FastVideo 优化总览（FP8 sm89+、FA4 sm90、区域编译数值代价、VSA 支持边界）：https://github.com/hao-ai-lab/FastVideo/blob/main/docs/inference/optimizations.md
- FastVideo 内核架构门（H3 VSA 原生核仅 sm_100a/sm_103a；Triton 回退）：https://github.com/hao-ai-lab/FastVideo/blob/main/fastvideo-kernel/README.md
- FastH3 Preview 模型卡（「FL2VA and Ref2VA were not distilled」）：https://huggingface.co/FastVideo/FastVideo-FastH3-4-step-Preview-v1-VSA-DataFree
- FastH3 发布博客（Blackwell 14×、8×B200 亚实时、Ref2VA 待训）：https://haoailab.com/blogs/fasth3-preview/
- FastVideo H3 cookbook（CUDA 默认 4 卡、性能档位实测于 4×GB200）：https://hao-ai-lab.github.io/FastVideo/cookbook/minimax-h3/
- FastVideo MiniMax-H3 端口状态（T2VA/FL2VA/Ref2VA 全支持，分布式 SP=1/SP=4 latent 一致）：https://github.com/hao-ai-lab/FastVideo/blob/main/tests/local_tests/minimax_h3/PORT_STATUS.md
- MiniMax-H3 Turbo 规格表与多卡章节（FSDP2、`torchrun --nproc-per-node`）：https://github.com/ModelTC/Minimax-H3-Turbo · https://huggingface.co/lightx2v/Minimax-h3-Turbo
- LightX2V H3 集成（Ref2AV + tensor/sequence parallel + 量化 + feature caching）：https://github.com/ModelTC/LightX2V/tree/main/scripts/minimax_h3
- LightX2V 并行推理（Ulysses / Ring / CFG parallel）：https://lightx2v-en.readthedocs.io/en/latest/method_tutorials/parallel.html
- alibaba-pai PDD Acc LoRAs（含 Ref2VA-Acc-8Step）：https://huggingface.co/alibaba-pai/MiniMax-H3-Acc-LoRAs
- H3 TAE 快速解码：https://huggingface.co/Kijai/MiniMax-H3-TAE · https://github.com/madebyollin/taehv
- VSA 论文：https://arxiv.org/abs/2505.13389
- 基线模型：https://huggingface.co/MiniMaxAI/MiniMax-H3
- ComfyUI H3 R2V 参考图尺寸口径：https://docs.comfy.org/tutorials/video/minimax/minimax-h3
- NVIDIA Sol-Engine H3 Super Acceleration（本项目已在用：LTX-2.5 三步细化）：https://nvlabs.github.io/Sana/Sol-Engine/H3-Super-Acceleration/
