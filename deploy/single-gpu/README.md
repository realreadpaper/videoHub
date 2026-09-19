# single-gpu/ — 单卡（1×A100-40GB）部署与跑批

> 面向 **只租一张 A100-PCIE-40GB** 的场景。这是现行形态，也是成本最低的可用形态。
>
> **部署步骤和 `deploy/bootstrap/` 完全一样**（00→05 那 6 个脚本一个字都不用改，
> 它们本来就与卡数无关）。本文只讲**单卡与双卡不同的那几处**，别重复看手册。

---

## 0. 一句话：单卡差在哪

| 维度 | 双卡（旧机形态） | **单卡（本形态）** |
|---|---|---|
| ComfyUI 实例 | 8188 + 8189，各占一张卡 | **只起 8188** |
| `instance_b.db` | 必须要（否则 `Database is locked`） | **完全不需要，别建** |
| `--database-url` | 8189 必须带 | **不需要**（单进程独占 sqlite，天然不锁） |
| 内存占用 | 2×57 GB ≈ 115 GB（125 GB 机器只剩 1.1 GB free） | **1×57 GB，内存压力大降** |
| 吞吐 | 加速比 1.950×（实测） | 1× |
| 一镜耗时 | 热态 558 s | **完全一样**（一镜本来也拆不到两卡） |
| 启动命令 | `04_launch_comfy.sh both` | **`04_launch_comfy.sh single`** |

**单卡唯一变慢的是"排队长度"，不是"单镜速度"。** 你丢 373 镜进去，
双卡 3.4 小时出完，单卡 6.6 小时出完——每一镜本身的 9 分 18 秒是一样的。

---

## 1. 目标机门槛（单卡分档，和双卡不同）

| 项 | 要求 | 说明 |
|---|---|---|
| GPU | 1× A100-PCIE-40GB（或 SXM4-40GB） | 都是 SM80，兼容性一致；SXM4 略快 |
| 显存 | 40 GB | 基准就是 40 GB，别选更小的 |
| **内存** | **≥ 96 GB**（推荐 128 GB） | ★ **最容易踩的坑**，见下 |
| 磁盘 | ≥ 150 GB | 权重 71 GB + ComfyUI/venv 8 GB + 长跑的成片输出 |
| 驱动 | ≥ 580 | torch cu130 自带 CUDA 13 运行时 |
| OS | Ubuntu 22.04 | 脚本按 apt 写 |

### ★ 为什么单卡也要 96 GB 内存

单张 40 GB 的卡**装不下 50.2 GB 权重**，必然要把一部分放内存里换进换出。
旧机实测：**单个空闲的 ComfyUI 进程就常驻 57 GB 内存**（双卡就是 2×57 GB）。

所以租卡时顺手选个 64 GB 内存的机型，跑到一半就会 OOM——这是本项目
**最贵的一类失误**（跑到第 200 镜崩了，前面的 gates 白费一半）。

`00_check_target.sh` 已内置这条判定：内存 < 96 GB 会直接报 `[FAIL]`。

> swap（`01_provision_os.sh` 会建 8 GB）只是**安全气囊**，不是内存扩展。
> 真开始用 swap 时因云盘 IO 抖动会表现为「整机卡死」，别指望它兜住 32 GB 的缺口。

---

## 2. 部署：照旧走 bootstrap，只有 4 处不同

```bash
# 新机上，与双卡完全相同的流程
bash deploy/bootstrap/00_check_target.sh     # 体检（会判定为【单卡模式】）
bash deploy/bootstrap/01_provision_os.sh
bash deploy/bootstrap/02_build_stack.sh
bash deploy/bootstrap/03_dl_weights.sh
bash deploy/bootstrap/04_launch_comfy.sh single    # ★ 差异 1：single 而不是 both

# 本机：推资产（唯一一份干声/参考帧，必推）
bash deploy/bootstrap/05_push_assets.sh <新机别名>
# 目标机
bash deploy/bootstrap/verify.sh --run
```

**差异 2 · 别建 `instance_b.db`。** 单卡不需要它，建了纯属占盘。

**差异 3 · 如果是整盘 rsync 搬过来的，清掉双卡的残留：**

```bash
# 旧机双卡时代留下的锁文件，会让单实例起不来或行为异常
rm -f /workspace/instance_b.db /workspace/instance_b.db.lock
rm -f /workspace/ComfyUI/user/comfyui.db.lock
# venv 里写死了旧机绝对路径，跨机搬过来基本是坏的 —— 别偷懒，重建
mv /workspace/venv /workspace/venv.broken && bash deploy/bootstrap/02_build_stack.sh
```

**差异 4 · 跑批前先做一次「接手检查」**（双卡时代的门禁文件还在，见 §4）。

---

## 3. 跑批：单 worker，不切分 keys

双卡要按 keys 对半分给两个 worker；**单卡就一个 worker，直接用目录扫描式**——
`pipeline_worker.sh` 的原子锁 + gates 断点续跑在单卡下就是最优解，不需要手工分片。

### 三条产线

| 产线 | 命令（目标机） | 单卡挂钟 |
|---|---|---|
| **抖音全量复刻 373 镜** | `cd /workspace/dy_key && setsid nohup bash run_dy_single.sh full > run_full.log 2>&1 < /dev/null &` | **≈6h34m** |
| 抖音关键镜 / 骨架 39 镜 | `cd /workspace/dy_key && setsid nohup bash run_dy_single.sh key > run_key.log 2>&1 < /dev/null &` | **≈5h15m** |
| 现代婚姻三部曲 24 镜 | `cd /workspace/trilogy && setsid nohup bash run_trilogy_single.sh > run_single.log 2>&1 < /dev/null &` | **≈3h45m** |
| 单镜试拍 | `/workspace/venv/bin/python /root/s2/submit_api.py /workspace/trilogy/wf_one/wf_f1s01.json --host http://127.0.0.1:8188 --timeout 2400` | 冷启 ≈820 s |

> 前两个脚本在本目录，**需要先推到目标机的对应位置**：
> ```bash
> # 本机执行
> scp deploy/single-gpu/run_dy_single.sh      <新机>:/workspace/dy_key/
> scp deploy/single-gpu/run_trilogy_single.sh <新机>:/workspace/trilogy/
> ssh <新机> 'chmod +x /workspace/dy_key/*.sh /workspace/trilogy/*.sh'
> ```
> 它们不依赖任何双卡脚本，单卡可独立使用。

### 为什么是这些时间（口径，别拍脑袋）

**核心公式**：双卡报告里的「**GPU 总机时**」= 单卡下的「**挂钟**」。

| 产线 | 实测 GPU 总机时 | 双卡挂钟 | **单卡挂钟** |
|---|---|---|---|
| 抖音关键镜 33 镜（实际跑完的） | 18908 s = 5h15m | 2h35m | **5h15m** |
| 抖音全量 373 镜 | 6.57 h | 3.37 h | **6h34m** |
| 三部曲 24 镜 | 未整批实测，按 558 s/镜外推 | ≈1.9 h | **≈3h45m** |

- 单镜热态 **558 s**（n=31，实测区间 541–578 s，很稳）
- 首镜冷启 **820 s**（比热态多付 ~262 s，**一个批次只付一次**）
- 所以：`单卡挂钟 ≈ 镜数 × 558 s + 262 s`
- **373 镜 6h34m 里，冷启只占 0.7%** —— 单卡跑长批次不需要为冷启做任何优化；
  但**试拍 1 镜时冷启就是 100% 的成本**，别拿它去估批量。

### 别在双卡机器上用这些脚本

`04_launch_comfy.sh single` 只启 GPU0 的 8188。在双卡机器上这么跑，
**GPU1 全程闲置、白付一半租金**。双卡机器请用 `both` + 双 worker。

---

## 4. ★ 接手检查清单（单卡专属，跑批前必做）

从双卡环境接手（或中断后重启）时，门禁目录里可能有三类脏状态。
**它们全都不会报错，只会静默跳过或死循环**——最阴的一类故障。

```bash
cd /workspace/dy_key

# ① 残留 .lock —— 双卡 worker 被 kill / 机器关机留下的空目录
#    后果：该镜被【永久跳过】，既不跑也不报错
find gates gates_full -maxdepth 1 -type d -name '*.lock'
find gates gates_full -maxdepth 1 -type d -name '*.lock' -exec rmdir {} \;

# ② 残留 .fail —— 此前失败的镜（新版 pipeline_worker.sh 会写）
#    后果：被跳过。确认修好了再删，删掉即重跑
ls gates*/*.fail
# rm gates/*.fail gates_full/*.fail

# ③ 旧实例的数据库锁 —— 整盘 rsync 搬过来的机器
rm -f /workspace/ComfyUI/user/comfyui.db.lock /workspace/instance_b.db.lock
```

`run_dy_single.sh` 已内置 ① 和 ③ 的自动清理（且会在有别的 worker 在跑时拒绝执行）。

### 另外一个真 bug 已修（2026-09-19）

原版 `pipeline_worker.sh` **对失败的镜会无限重试**：FAIL 后只写 `failed_*.txt`
并释放 lock，下一轮扫描又领到同一个镜 → 死循环烧机时。
双卡时另一张卡还在出别的片，不容易察觉；**单卡跑 373 镜时会直接卡死在那**。

归档版已加 `.fail` 标记：失败即跳过、不再自动重试，删 `.fail` 才重跑。
★ 旧服务器上跑的还是老版本，单卡部署时**请用 `deploy/server-assets/dy_key/pipeline_worker.sh`
覆盖过去**（`05_push_assets.sh` 已经传的就是修好的版本）。

---

## 5. 单卡独有的三个好处（别浪费）

1. **内存不再打架**：双卡时 125 GB 被两个实例各吃 57 GB，只剩 1.1 GB free，
   任何额外进程都可能 OOM；单卡时余量充足，可以放心开日志、跑后处理、拉片子。
2. **冷启只付一次**：双卡时两张卡各付一次 ~253 s 的冷启溢价，短批次亏得更明显。
3. **不存在 `Database is locked`**：这条双卡最常见的翻车点，单卡天然免疫 —— 不必再纠结 `--database-url`。

**不用做的优化（省点力气）**：
- 不要试「单卡把 batch 调大」：H3 的一镜是整体去噪，没有 batch 维度可堆。
- 不要试 SageAttention / FP8 / `--fast`：A100 是 SM80，全部已实测否决，见主手册 §11。
- 不要为了提速拆分辨率：768×1344 是已定稿的交付口径。

---

## 6. 相关文件

| 文件 | 作用 |
|---|---|
| `../README.md` | 通用迁移总纲（软件/权重/资产清单、血泪坑位） |
| `../bootstrap/` | 6 个部署脚本，单卡双卡通用 |
| `deploy/single-gpu/run_dy_single.sh` | 抖音单卡跑批（full / key 两条线） |
| `deploy/single-gpu/run_trilogy_single.sh` | 三部曲单卡跑批 |
| `../../docs/单卡A100部署手册.html` | 单卡完整手册（含背景、实测、验收） |
