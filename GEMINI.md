# VideoHub / MiniMax-H3 项目长期记忆与技术规范

> 本文件记录远端服务器（`kehu`）拓扑、ComfyUI 双实例部署规范、核心模型与算子加速基准，供所有会话与自动化 Agent 继承遵循。

---

## 1. 远端服务器与硬件拓扑

* **SSH 别名**：`ssh kehu`
* **硬件规格**：
  * GPU：2 × NVIDIA A100-PCIE-40GB（SM80 架构，无物理 NVLink，卡间通信走 PCIe）
  * 驱动与 CUDA：Driver Version 580.95.05，CUDA 13.0
  * 系统内存：128 GB RAM
* **工作目录**：
  * ComfyUI 根路径：`/workspace/ComfyUI`
  * Python 虚拟环境：`/workspace/venv`（Python 3.10.12）
  * 批处理主脚本与数据目录：`/workspace/trilogy`
  * 运行日志目录：`/workspace/logs`

---

## 2. ComfyUI 部署与运行规范

### 2.1 当前版本与核心依赖（2026-09-18 升级验证）
* **ComfyUI 版本**：官方发布标签 **`v0.36.0`**（commit `ee71d5c4`）
* **关键依赖要求**：
  * `comfy-kitchen>=0.2.34`（必须≥0.2.34，内建 `group_norm_silu_pad3d`、`rms_rope_split_half`、`fp16_conv3d` 等专为 MiniMax-H3 适配的 CUDA 算子）
  * `comfyui-workflow-templates>=0.11.62`
  * `comfyui-frontend-package==1.52.7`
  * `torch==2.14.0+cu130`

### 2.2 双实例并行启动命令（铁律：必须隔离数据库）
双卡独立跑批处理时，**必须为实例 B 指定独立 SQLite 数据库路径**，否则会触发 `Database is locked` 严重报错：

```bash
# GPU 0 实例 A（监听 8188 端口）
CUDA_VISIBLE_DEVICES=0 nohup /workspace/venv/bin/python /workspace/ComfyUI/main.py \
  --listen 127.0.0.1 --port 8188 --vram-headroom 1 > /workspace/logs/comfy_a.log 2>&1 &

# GPU 1 实例 B（监听 8189 端口，必须指定独立的 database-url）
CUDA_VISIBLE_DEVICES=1 nohup /workspace/venv/bin/python /workspace/ComfyUI/main.py \
  --listen 127.0.0.1 --port 8189 --vram-headroom 1 \
  --database-url sqlite:////workspace/instance_b.db > /workspace/logs/comfy_b.log 2>&1 &
```

---

## 3. MiniMax-H3 模型栈与工作流资产

* **DiT 主干模型**：`models/diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors`（19.53 GB，INT8 量化）
* **加速 LoRA**：`models/loras/minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors`（4-step Turbo）
* **Text Encoder**：`models/text_encoders/minimax_h3/qwen3vl_32b_minimax_h3_int8_convrot.safetensors`
* **Video VAE**：`models/vae/minimax_h3_video_vae_fp16.safetensors`（FP16）
* **Audio VAE**：`models/vae/minimax_h3_audio_vae_fp32.safetensors`
* **自定义节点**：`custom_nodes/comfyui-minimax-h3-audio-T8`
* **系统环境依赖**：必须确保宿主机安装了 `/usr/bin/ffmpeg`，否则视频封装节点 `MiniMaxH3SafeAVSaveT8Advanced` 会报错中断。

---

## 4. 实测基准数据（Benchmark Records）

> 测试规格：MiniMax-H3 768×1344 分辨率，13秒长片（311帧视频 + AAC音频），4 NFE 采样

| 阶段 / 指标 | 升级前（commit f42b24e / kitchen 0.2.33） | 升级后（v0.36.0 / kitchen 0.2.34） | 提升收益 |
| :--- | :--- | :--- | :--- |
| **模型初始化与冷加载** | 128.2 秒 | **96.8 秒** | 提速 24.5% |
| **单步扩散采样平均耗时** | 131.1 秒 / step | **94.3 秒 / step** | **提速 28.1%** |
| **4步采样总耗时** | 527.0 秒 | **377.0 秒** | 节省 150 秒 |
| **单镜端到端总用时** | 590.7 秒（9分50秒） | **469.3 秒（7分49秒）** | **整体提速 20.5%（净省 121.4 秒）** |
| **全量 24 镜批处理总耗时** | 约 2.0 小时 | **约 1.56 小时（1h34m）** | **整批净省 26 分钟** |

---

## 5. 批处理与日常运维准则

1. **每镜前释放显存**：通过 POST `http://127.0.0.1:<port>/free` 带 `{"unload_models":true,"free_memory":true}` 释放显存，防止长视频残余激活压卡。
2. **多卡策略铁律**：在 A100-PCIE 拓扑下，保持 **双实例独立并行** 吞吐最高（1.56 小时）。单任务双卡序列并行（SP=2）总耗时预估 >2.4 小时，无整体收益。
3. **批量任务监控**：
   * 批处理状态：`cat /workspace/trilogy/run_*.log`
   * 门禁完成情况：`ls -la /workspace/trilogy/gates_one/*.done`
