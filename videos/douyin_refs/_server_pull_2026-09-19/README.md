# 服务器产出归档 · 2026-09-19

> `kehu`（124.81.178.140，2×A100-PCIE-40G，华为云泰国）**停机前**最后一次全量回传。
> 目录结构与服务器 `/workspace` **原样镜像**，便于逐文件比对。

| 项目 | 值 |
|---|---|
| 快照时间 | 2026-09-19 16:35（服务器 CST）；16:56 追加一轮增量 |
| 文件数 | **2794** |
| 总体积 | **1,772,259,938 B ≈ 1.65 GiB** |
| 回传方式 | `tar` over ssh 分块（本机无完整版 rsync，只有受限的 openrsync） |
| 实测速率 | ≈ 1.6 MB/s（BBR 已开启），首轮 928 s |
| 校验结果 | **2794 / 2794 通过 · 0 缺失 · 0 md5 不符** |
| 校验基准 | `MANIFEST.tsv`（服务器端生成，含每个文件的 md5） |
| 追加增量 | `pull_delta.sh` 抓到 20 个快照后新文件（`dy_six4` 六镜批次跑完的 6 个成片 + 新试点素材） |

---

## 一、目录结构

```
_server_pull_2026-09-19/
├── ComfyUI/
│   ├── output/            ← 115 个成片 · 1445 MB · 18 个实验批次
│   └── input/             ← 1656 个素材 · 237 MB（参考帧 / 首尾帧 / 干声 / 音轨切片）
├── dy_key/                ← 922 个 · 5.6 MB（worker 日志、门禁快照、全部工作流 JSON）
├── trilogy/               ← 67 个 · 0.3 MB（三部曲试拍）
├── dy4/                   ← 28 个 · 2.1 MB（dy4 试点）
├── logs/                  ← 5 个 · 0.3 MB（ComfyUI 服务端日志）
├── 节点源码参考/           ← `h3_t8/timing.py` + `core.py`（地板逻辑的出处）+ COMMITS.txt
├── MANIFEST.tsv           ← 服务器端 md5 清单（2794 条，校验基准）
├── README.md              ← 本文件
├── ANALYSIS.md            ← ★ 实测分析全文（成本模型 / 地板 / 优化清单）
├── timing.json / timing.md← 从日志抽出的逐镜耗时（145 条 / 19 批次）
├── analyze_logs.py        ← 抽计时（可重跑）
├── join_timing_frames.py  ← 实测耗时 ↔ 工作流帧数 关联
├── verify_pull.py         ← 逐文件 md5 校验
├── make_pull_manifest.py  ← 服务器端清单生成器
├── pull_h3_assets.sh      ← 首轮回传脚本（幂等，可续传）
└── pull_delta.sh          ← 增量补拉（比对清单，只传快照后的新文件）
```

### 成片批次一览（`ComfyUI/output/`）

| 批次 | 个 | 体积 | 是什么 |
|---|---:|---:|---|
| `dy_skel` | 33 | 754 MB | 骨架镜（354 帧请求 → 362 帧实渲，14.75 s） |
| `dy_key` | 17 | 336 MB | 关键技术镜（含 3 个产品镜） |
| `abtest` | 4 | 83 MB | 早期 A/B 对比 |
| `MiniMaxH3/trilogy_one` | 4 | 70 MB | 三部曲试拍 |
| `dy4_pilot` | 8 | 56 MB | dy4 试点（**8 步** Hybrid 三图） |
| `dy_full` | 12 | 36 MB | 373 镜全量线的短单元（1 图 / 4 步） |
| `dy_six4` `dy_six3` `dy_six2` `dy_six` | 6 / 6 / 6 / 4 | 115 MB | 六镜实验系列 |
| `dy_pv2` `dy_v2C` `dy_pv3` `dy_v2B` | 各 2 | 32.2 MB | 参考帧版本对比 |
| `dy_Dtest` `dy_v3full` | 各 2 | 9.8 MB | 参考帧版本对比 |
| `dy_S8` `dy_S6` `dy_S12` | 各 1 | 6.6 MB | **步数实验**（同镜 8 / 6 / 12 步） |
| **合计** | **115** | **1445.1 MB** | |

### 素材目录（`ComfyUI/input/`，>1 MB 的）

| 目录 | 张 | 体积 | 说明 |
|---|---:|---:|---|
| `dy_full_ref_v3` | 373 | 65.3 MB | 全量线参考帧（v3，去字后） |
| `dy_full_first_v3` | 373 | 65.3 MB | 全量线首帧（v3） |
| `dy_full_ref` | 373 | 29.8 MB | 全量线参考帧（v1） |
| `dy_full_last4/first4/last5/first5/ref_v5/last6/first6/ref_v6` | 各 6–8 | 7.9 MB | 各版首尾帧 |
| `dy_full_a` | 373 | — | **干声 / 音轨切片（wav）** |
| `dy_voice` / `tts_dry` / `dy4_voice` | 31 / 24 / 4 | — | TTS 干声素材 |

> `full_ref` 与 `dy_full_a_tmp` 在服务器上已是**空目录**（并行会话清理），故清单中为 0 条，不是漏拉。

---

## 二、完整性校验

`MANIFEST.tsv` 由**服务器端**在传输前生成（`md5 → 字节数 → 相对路径`）。
本机校验判据：**文件存在 且 字节数一致 且 md5 一致**，三者全中方为通过。

```bash
cd videos/douyin_refs/_server_pull_2026-09-19
python3 verify_pull.py .
```

**本次结果（2026-09-19 16:56）：**

```
清单条目: 2794
通过 2794   缺失 0   字节数不符 0   md5 不符 0   读错 0
```

首轮校验曾出现 2 处「字节数不符」，均为 `logs/comfy_b2.log` 与 `logs/comfy_pipeline.log` ——
这两个是 ComfyUI 服务端**正在写入**的活日志，传输期间持续增长。已重拉一版并把清单对齐到实际落盘值。

清单生成方式（如需在新服务器复现）：

```bash
# 服务器端
python3 - /workspace/_pull_2026-09-19/MANIFEST.tsv \
        ComfyUI/output ComfyUI/input logs dy_key dy4 trilogy
```

> ⚠ 传输期间服务器上有任务在跑（`dy_six4` 六镜批次）。`ComfyUI/input` 那棵树 tar 报了
> `file changed as we read it`（并行会话正往里写新素材），属正常现象，已用增量脚本补齐 20 个新文件。

---

## 三、这批数据能回答什么

详见 **`ANALYSIS.md`**（或 `docs/H3实测成本模型与优化清单.html`）。核心结论：

1. **工作流有 124 帧（5.167 s）渲染地板** —— `ensure_minimum_context=True` 把短镜补齐到
   `MIN_TRAINED_FRAMES` 再渲染，成片再裁回请求长度。
2. 373 镜里 **348 镜（93.3 %）落在地板以下**，付费帧数是需要的 **1.94 倍**。
3. 373 镜真实 GPU 机时 ≈ **14 h**（双卡 ≈7 h / 单卡 ≈14 h），不是部署手册写的 6.57 h —— **低估 ×2.1**。
4. **切短不省时间**：地板以下全是同一个价；短镜每镜秒 67.7 s，长镜 38.5 s，**长镜更划算**。
5. 参考图 1 / 2 / 3 张 = 110.1 / 130.2 / 145.0 s（**每多一张约 +20 s**）。
6. 步数**严格线性**：21.3 s/步（此前「非单调」的表象是排队污染）。

---

## 四、接手这台机器 / 从这台机器迁移时的注意点

| # | 事项 | 说明 |
|---|---|---|
| 1 | **清 `.lock` 残留** | `dy_key/gates_full/dy1_s009.lock`、`dy1_s010.lock` 仍在。带锁的镜会被 worker **永久静默跳过**。<br>`find gates* -maxdepth 1 -type d -name '*.lock' -exec rmdir {} \;` |
| 2 | **核对门禁账目** | 全量线 `gates_full/` 只有 **12 个 `.done`**（373 镜里），两部片子的关键镜 `gates/` **39/39 完成**。 |
| 3 | **日志「用时」含排队** | 不要拿它做加速对比。`S6.log` 里 410.5 s 中有 230 s 是排队。 |
| 4 | **失败镜** | 6 条失败记录全部卡在 `SamplerCustomAdvanced`；集中在 `dy1_s003/s004/s009/s010`，疑似确定性失败。 |
| 5 | **快照边界** | 16:35 之后服务器新增的 `dy4f_*` / `dy4g_*` 试点目录**不在此归档内**；服务器当时仍在被并行会话使用。 |

---

## 五、复现脚本

```bash
# 1) 从日志抽逐镜耗时 → timing.json / timing.md
python3 analyze_logs.py . --json timing.json --md timing.md

# 2) 实测耗时与工作流帧数按镜号关联（需本仓库的 wf_full 等目录）
python3 join_timing_frames.py

# 3) 逐文件 md5 校验
python3 verify_pull.py .

# 4) 重跑首轮回传（幂等，可续传）
bash pull_h3_assets.sh

# 5) 增量补拉：比对服务器当前状态，只传快照后的新文件
bash pull_delta.sh          # 只列差异
bash pull_delta.sh --pull   # 列出并拉取（会同步更新 MANIFEST.tsv）
```

用到的 Python 为任意 3.8+（仅标准库）。
