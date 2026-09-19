# ComfyUI v0.36.0 升级与加速记录 (2026-09-18)

## 1. 升级概况
- **ComfyUI 核心**：从 commit `f42b24e` 升级至标签 **`v0.36.0`** (`ee71d5c4`)
- **高性能算子库**：`comfy-kitchen` 从 `0.2.33` 升级至 **`0.2.34`**
  - 新增并在 MiniMax-H3 中生效的融合算子：`group_norm_silu_pad3d`, `rms_rope_split_half`, `int8_attention`, `fp16_conv3d`
  - `tiled_decode` 升级为动态批处理并发（最多 4 tiles 并行）
  - `temporal chunking` 优化中间显存释放
- **依赖补全**：安装了缺失的 `comfyui-workflow-templates==0.11.62`

## 2. 实测数据对比 (wf_f1s02: 768x1344, 311 帧, 13秒)
| 指标 | 升级前 (f42b24e / 0.2.33) | 升级后 (v0.36.0 / 0.2.34) | 改善幅度 |
| :--- | :--- | :--- | :--- |
| **模型初始化** | 128.2 秒 | **96.8 秒** | 提速 24.5% |
| **单步采样** | 131.1 秒/步 | **94.3 秒/步** | **提速 28.1%** |
| **4步采样用时** | 527.0 秒 | **377.0 秒** | 节省 150 秒 |
| **单镜端到端** | 590.7 秒 (9m50s) | **469.3 秒 (7m49s)** | **净省 121.4 秒 (20.5%)** |
| **24 镜双实例总用时** | 约 2.0 小时 | **约 1.56 小时 (1h34m)** | **净省 26 分钟** |

## 3. 双实例规范启动命令
```bash
# GPU 0 / 端口 8188
CUDA_VISIBLE_DEVICES=0 nohup /workspace/venv/bin/python /workspace/ComfyUI/main.py   --listen 127.0.0.1 --port 8188 --vram-headroom 1 > /workspace/logs/comfy_a.log 2>&1 &

# GPU 1 / 端口 8189 (必须加 --database-url 防止锁死)
CUDA_VISIBLE_DEVICES=1 nohup /workspace/venv/bin/python /workspace/ComfyUI/main.py   --listen 127.0.0.1 --port 8189 --vram-headroom 1   --database-url sqlite:////workspace/instance_b.db > /workspace/logs/comfy_b.log 2>&1 &
```
