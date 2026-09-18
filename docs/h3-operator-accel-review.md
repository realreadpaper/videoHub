# H3 算子级加速审查：v0.36.0 之后还能不能再来一次「升级式」提速

> 审查日期：2026-09-18 · 基线：MiniMax-H3 Ref2VA 一步直出 768×1344 / 311 帧 / 4 NFE · ComfyUI v0.36.0 + comfy-kitchen 0.2.34 · 2×A100-PCIE-40G（SM80，无 NVLink）
> 标注：**事实**（有原文/本机实测）／**推论**（本文算术）／**未知**

## 一、结论

1. **「融合」类红利基本吃完了。** v0.36.0 那 −28.1% 来自把**非注意力算子**接进 comfy-kitchen 的融合 CUDA 核（`group_norm_silu_pad3d`、`rms_rope_split_half`、INT8 GEMM epilogue 吞 SwiGLU/residual、`fp16_conv3d`）+ `tiled_decode`。comfy-kitchen 的内核清单里，H3 用得到的融合项已经都在（见第三节），**再融只能捡零碎，预计个位数百分比**。
2. **剩下的大头是注意力算子本身。** 本项目自证：像素 ×4 → 单步 ×11（384×672 = 12.4 s，768×1344 = 138.5 s，升级前），超线性部分只能是 attention。
3. **但 A100 上四条注意力快路已被堵死三条半**（逐条有据，见第四节）：VSA 只编 `sm_100a`、T8 节点包的 SLA 后端**源码里硬钉 sm89**、全局 `--use-sage-attention` 因 FP8 PV → NaN、FA4 需 sm90+。
4. **唯一「官方背书 + 未被你们试过」的注意力加速是 SageAttention 经 KJNodes 的 `PathchSageAttentionKJ`（MODEL 分支内 patch，fp16 PV 变体）**：ComfyUI 官方文档写"roughly double"，官方渐进配方实测 **106.70 → 74.71 s（−30%）**。你们只试过**全局开关**（必 NaN），没试过官方推荐的那条接法。
5. **两个现成可试的 comfy-kitchen 算子**：`int8_attention` 与 `sol_attn` —— 你们 09-17 的后端探测已确认 **SM80 预编译 wheel 含 `80-real` 且 capabilities 里有 `sol_attn`**，即两者在 A100 上都有原生路径。缺的只是 A/B 与画质验收。
6. **已验证、零风险的省时项还没接上**：官方 **INT8 ConvRot 视频 VAE**（H16 资格文档：热解码 12.58 → 4.90 s，峰值 5.38 → 3.08 GiB，两组四片已人审），而三部曲管线里仍是 `minimax_h3_video_vae_fp16`。
7. **别按 GEMINI.md §4 的账去优化**：`96.8（初始化）+ 377（采样）= 473.8 > 469.3（端到端）`，说明"模型初始化"不是可加的独立阶段（skill 已指出那是 `comfy/utils.py:model_trange()` 给第一步贴的 tqdm 标签）。**推论**：真实瓶颈账 = 4 步采样 ≈ 377 s（80%）+ 解码/封装/保存 ≈ 92 s（20%）。

## 二、v0.36.0 到底改了什么（事实）

| 改动 | 类型 | 作用对象 |
|---|---|---|
| `ck.group_norm_silu_pad3d` | 算子融合 | CausalConv3d 的 Norm/SiLU/Pad |
| `ck.rms_rope_split_half` | 算子融合 | RMSNorm + split-half RoPE |
| INT8 GEMM epilogue 融合 | 算子融合 | SwiGLU / residual 写回 |
| `ck.fp16_conv3d` | 专用卷积核 | VAE / DiT 卷积 |
| `tiled_decode` 动态批处理 | 调度 | VAE 解码（≤4 tiles 并发）+ temporal chunking 释放显存 |

实测：单步 131.1 → 94.3 s（**−28.1%**），单镜 590.7 → 469.3 s（**−20.5%**），24 镜双实例 ≈ 2.0 h → **1h34m**。
**关键推论**：非注意力算子原本占单步 ≥28%，所以单步里非注意力部分约 30 s 量级、注意力约 60 s 量级 —— 想再拿 20%+，只能动注意力。

## 三、还剩多少「同类」空间（comfy-kitchen 内核清单，事实）

库里的相关内核（`eager/cuda/triton/hip` 四后端矩阵）：

| 类别 | 内核 | cuda | 与 H3 关系 |
|---|---|---|---|
| 归一化+激活 | `na3d` / `na2d` / `adaln` / `rms_adaln` | ✓ | 已在用（v0.36.0 那批） |
| RoPE | `apply_rope*` / `rms_rope*`（含 in-place） | ✓ | 已在用 |
| INT8 | `quantize_int8_*` / `rotate` / `int8_linear` / `dequantize_*` | ✓ | **已在用**（convrot 主干） |
| AWQ | `gemv_awq_w4a16` | ✓ | 你们 TE 是 int8_convrot，不是 AWQ → 不适用 |
| 注意力 | **`int8_attention`** | ✓ | **未见启用证据** |
| 注意力 | **`sol_attn`** | ✓ | **未见启用证据**（stage2 模板里出现过 `auto_sol_attn`） |
| W4A4 | `convrot_w4a4_linear` / `svdquant` | ✓ | 更激进量化，未评估 |

**判断**：能融的都在库里，剩下的融合项是零碎（patchify/unpatchify、audio 分支、条件编码），单靠它拿不到两位数百分比。**要确认还漏了哪些，只能做算子级 profile（第五节）。**

## 四、注意力算子在 A100（SM80）上的可用矩阵

| 方案 | 硬件门槛 | A100 可用 | 证据 / 状态 |
|---|---|---|---|
| 现状（SDPA / CK 默认） | — | ✅ | 基线 |
| `comfy-kitchen` `int8_attention` | cuda | **✅** | 你们探测到的 capabilities 含 int8 系列；第三方在 SM75 上实测 CK INT8 比 KJ/Sage 快 29.4%，说明**注意力算子本身**是收益点 |
| `comfy-kitchen` `sol_attn` | cuda（`sm_100a` 原生核另有路径） | **✅ 探测含 `80-real`** | 未做画质 A/B；Sol 用「选中块精确 + 未选中块质心近似」，必须与 dense_reference 对照 |
| **SageAttention + `PathchSageAttentionKJ`** | SM80 支持（用 fp16 PV 变体） | **✅ 待试** | ComfyUI 官方文档："roughly double the generation speed… minimal quality loss"；官方渐进配方 106.70 → 74.71 s（−30%）。**必须绕开 FP8 PV 变体** |
| SageAttention 全局 `--use-sage-attention` | SM80 无原生 FP8 | ❌ | 本机实测 791 s 且**输出全 NaN**（根因：H3 内核对 `_sageattn_int8_fp8_nhd` 硬依赖） |
| VSA-H3（FastH3 稀疏注意力） | `sm_100a`/`sm_103a` | ❌ | 原生核只编 Blackwell；且只蒸馏了 T2VA |
| T8 节点包 SLA 后端 | **源码硬钉 `capability == (8,9)`** | ❌ | `h3_t8/sla_attention_advanced.py`：非 sm89 直接 raise；且你们有盲评硬失败记录 |
| chunk-star7 SLA（Triton / Sol 路径） | SM75 原生核 / SM80+ 用 Triton 或 Sol | ⚠️ | 你们环境探测：`triton: available=True 但 disabled=True` → Triton 路径当前不可用；SM80 实测数字缺失 |
| Progressive attention | — | ❌ | 官方 −37%，但明写**不支持多参考/尾帧**，正是 Ref2VA + first/last frame 的用法 |
| FA4 | sm90+ | ❌ | A100 落回 FA2 |

**小结**：注意力这块，**唯一低成本高赔率的是 Sage+KJ patch**；`int8_attention` / `sol_attn` 是「零安装成本的 A/B」；其余四条已排除。

## 五、动手前必须补的测量（现在所有拆分都是间接的）

1. **算子级 profile（最高优先，半天）**：对一镜 4 步跑 `nsys profile`（或 torch profiler），输出 **top-15 kernel 的耗时占比**。要回答的唯一问题：当前 94.3 s/步里，attention（softmax/QK/PV）、INT8 GEMM、conv3d、norm/rope 各占多少。
   - 若 attention ≥50% → 全力打 Sage/Sol；
   - 若 GEMM/conv 仍 ≥40% → 说明 kitchen 还有没接上的算子，先补路由。
2. **订正口径（半小时）**：
   - `GEMINI.md §4`：`模型初始化 96.8 s` 与 `4 步采样 377 s` 相加超过端到端 469.3 s → 该数不可加，别当成 20% 的独立阶段去优化。
   - `GEMINI.md §5.1`「**每镜前释放显存**」与 `run_one_step_dual.sh`（批次开始前一次）以及 skill 铁律「20 镜必须同进程连续跑，中途不调 `/free`」**相冲突**。照 GEMINI 字面执行，每镜多付一次冷加载，**约 +96.8 s/镜（+20%）**。
3. **确认当前注意力后端**：把实际工作流里 attention backend 的取值打出来（`ModelAttentionBackend` / 节点默认），确认是否已走 `comfy kitchen attention`；若走的是 SDPA，先切 CK INT8 做一次 A/B，成本为零。

## 六、按性价比排序的行动清单

| 序 | 动作 | 预期 | 成本/风险 |
|---|---|---|---|
| 1 | 算子级 profile + 口径订正 | 决定后面所有投入 | 半天，零风险 |
| 2 | 视频 VAE 换官方 `minimax_h3_video_vae_int8_convrot` | **−3~4% E2E**（按 H16 实测比例外推，需自测）＋峰值 −2.3 GiB | 半天，已有两组人审背书 |
| 3 | 装 KJNodes，`PathchSageAttentionKJ` 只 patch MODEL 分支 + fp16 PV 变体 | 若 attention 占比 60% → **理论 −18~30%** | 1 天；必须过三项量化质检 + 目视 |
| 4 | `sol_attn` / `int8_attention` A/B（各一镜，dense_reference 对照） | 未知，第三方在 SM75 上 attention op 快 1.24~2× | 1 天；Sol 有近似风险 |
| 5 | 条件缓存复用（`SaveConditioning`/`ConditioningLoader`），免每镜 CLIP 装载+编码 | 2–5 min/20 镜 + 显存余量（S2 98%→56%） | 半天 |
| 6 | 不要在提速目标里再考虑：VSA / T8-SLA / Progressive / TRT VAE / `--fast autotune` | 逐条已有否决证据 | — |

**能不能再来一次 −20%？** 能，但只有第 3 项有这个机会，而且要接受「画面可能变化、必须重新过质检」。第 2 项是稳的但小。**若要 1080p（2 MP），算子层的意义会从「提速」变成「能不能跑」**（激活分块 / 稀疏注意力 / 双卡分片），见 `h3-1080p-quality-research.md`。

## 七、来源

- ComfyUI H3 总览（Sage Attention 官方建议"roughly double"+ 安装 KJNodes 与 Patch Sage Attention 节点、768×1344 面积上限）：https://docs.comfy.org/tutorials/video/minimax/minimax-h3
- comfy-kitchen 内核矩阵与后端能力（`int8_attention` / `sol_attn` / `na3d` / `rms_rope*` / `int8_linear`）：https://github.com/Comfy-Org/comfy-kitchen
- 本项目 09-17 后端探测（SM80 预编译含 `80-real`，capabilities 含 `sol_attn`；`triton` disabled=True）：`~/.workbuddy/skills/h3-film-production/scripts/setup/README.md`
- 本项目单镜加速对照套件（冷/热 826/631 s、单步 12.4/138.5 s、SageAttention NaN 根因、官方渐进配方 −30%、各加速包否决清单）：`~/.workbuddy/skills/h3-film-production/scripts/speed/README.md`
- 官方 INT8 ConvRot 视频 VAE 资格（热解码 12.58 → 4.90 s，峰值 5.38 → 3.08 GiB，用户验收）：T8 节点包 `docs/H16_OFFICIAL_INT8_VAE_QUALIFICATION.md`
- TRT VAE 实测（解码内核 22.96 → 10.64 s，但端到端 30.54 → 31.33 s，无净收益）：T8 节点包 `docs/TRT_VAE_EXP.md`
- T8 节点包 SLA 后端硬钉 sm89：`h3_t8/sla_attention_advanced.py`（`capability != (8, 9)` → raise）
- 补丁组合策略（允许 KJ Sage／Sol／LoRA 组合，但组合未经效果验证）：T8 节点包 `docs/PATCH_STACK_POLICY.md`
- chunk-star7（SLA/Sol 的 SM80+ 路径、激活分块只在 OOM/换页时改善吞吐）：https://github.com/star7code/minimax-h3-chunk-star7
- v0.36.0 升级实测：`GEMINI.md` §4 与本仓库 `docs/h3-acceleration-2xa100.md`
