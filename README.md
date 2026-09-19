# videoHub

AI 短剧（MiniMax H3 + LTX-2.5 两阶段管线）工作区：本机 macOS 只做编排与后处理，重活跑远端 GPU。

> **本仓库只存「可读文本产物 + 编排代码」**：剧本/分镜/提示词、配置、脚本、报告、项目记忆。
> 视频/音频/图片等大体积媒体和 4 个外部代码仓库都**不在**本仓库内容里（见下文），
> 克隆后需要按下面步骤补齐 submodule。

## 快速开始

```bash
git clone --recurse-submodules ssh://git@ssh.github.com:443/realreadpaper/videoHub.git videoHub
cd videoHub

# 已克隆过、但没带 --recurse-submodules 时补齐
git submodule update --init
```

只想要文本产物、不需要外部仓库时，直接普通 clone 即可（父仓库本身约 7 MB）。

## 目录结构

| 路径 | 内容 |
| --- | --- |
| `h3-films/` | 主生产线：剧本/分镜/提示词、字幕（srt/vtt）、量化报告、后处理脚本（`*.py`/`*.sh`） |
| `待生成_现代婚姻三部曲/` | 三部曲（周星驰/姜文/奉俊昊 × 现代婚姻）剧本、分镜、`_pipeline/` 工作流与调度脚本 |
| `videos/` | 广告与 demo 工作区（`douyin-ad`、`douyin-ad-2`、`demo`、`selfhosted-check`）与抖音参考片拆解/复刻（`douyin_refs/`） |
| **`deploy/`** | **换 GPU 服务器时的重新部署包**：迁移总纲 `README.md` + `bootstrap/` 六个可执行脚本（单卡双卡通用）+ `single-gpu/` 单卡跑批脚本 + `server-assets/` 服务器侧脚本与输入资产快照 |
| `fastvideo-configs/` | FastVideo 推理/服务 YAML 配置（4090 / A100 / 多卡 FSDP 等） |
| `fastvideo-remote/`、`remote-render/` | 远端 GPU 环境搭建与远程渲染脚本 |
| `docs/`、`_meta/` | 成本测算、加速路线调研、**`新服务器部署手册.html`**、**`单卡A100部署手册.html`**、站点资料 |
| `.workbuddy/memory/` | 跨会话项目记忆（硬件门控判据、计时口径等，**跨会话必读**） |

## 外部代码仓库（submodule）

5 个仓库以 **git submodule** 引用（见 `.gitmodules`）：各自的 `.git`、分支、remote 完全独立，
父仓库只记录一个提交指针，**不复制任何文件**，因此可以随时独立拉取上游更新。

| 路径 | 上游（submodule url） | 本仓库记录的提交 |
| --- | --- | --- |
| `repos/hypit/` | https://github.com/hypit-ai/hypit | `98000342`（tag `v0.1.10`） |
| `repos/FastVideo/` | https://github.com/hao-ai-lab/FastVideo | `c4824c77`（`main`，版本 `0.2.1`） |
| `reelbench-skills/` | https://github.com/eternityspring/reelbench-skills | `18f2f639`（`main`） |
| `TaoMate-H3/` | https://github.com/TaoLiveAIGC/TaoMate-H3 | `b933d8e9`（`main`） |
| `repos/jianying-headless/` | https://github.com/mcncarl/jianying-headless | `bb1e72c`（`main`） |

> `repos/jianying-headless` 是剪映专业版的本地自动化工具（非商用许可，商用需作者书面授权）。
> 它**不是**独立剪辑软件：真正跑起来还需要本机安装剪映专业版 11.4.0/11.4.2，
> 并且重建原生 codec 需要与固定哈希匹配的工具链（Apple clang 21 / macOS SDK 26.5）。
> 详见该仓库的 `README.md`。

submodule 的 url 统一用 **HTTPS**（公开仓库免鉴权、不受本机 22 端口阻断影响）；
父仓库自身的 `origin` 用 SSH over 443（见「远端接入」）。

### 查看当前状态

```bash
git submodule status              # 前缀 ' '/'-'/'+' = 已初始化 / 未初始化 / 指针与工作区不一致
git -C repos/hypit log --oneline -3
git -C repos/hypit status --porcelain   # 子模块内的本地改动
```

### 更新到上游最新

```bash
git submodule update --remote --merge              # 全部：按 .gitmodules 里的 branch 更新
git submodule update --remote --merge repos/hypit  # 单个
git status && git add .gitmodules repos/hypit && git commit -m "chore: bump hypit submodule"
```

`--remote` 只移动工作区指针，**不会**替你提交；要在父仓库 commit 新的 gitlink 别人才拿得到。
更新前先 `git -C <path> status` 自查，避免把子模块里的本地改动一起带走。

### 已冻结的既有状态（不是故障）

1. `repos/hypit`：有 1 个本地未提交改动 `examples/semantic-composition/hypit.runtime.json`
   （本机运行时配置）。submodule 只记录 HEAD，**这份改动不在任何仓库里**，要保住得在 hypit 内 commit/push。
2. `repos/FastVideo`：上游 `main` 的**精简快照**——为省空间删掉了 84 个演示用图片/视频（约 155 MB），
   另有 69 个文件丢了可执行位（该子模块已设 `core.fileMode=false`）。因此它长期显示为 modified，
   属预期；`git -C repos/FastVideo checkout -- .` 可从本地已有对象恢复被删文件（不需要联网）。
3. `repos/FastVideo` 自身还有 3 个未初始化的子模块（ThunderKittens / cutlass / VBench，体积大），
   按需单独取：`git -C repos/FastVideo submodule update --init --depth 1 <path>`。

### 不要做的事

- 不要把子模块内部文件 `git add` 到父仓库（会退化成 vendored 复制，破坏上游可拉取性）。
  父仓库里只应存在 4 个 `160000` 类型的 gitlink。
- 不要 `rm -rf <submodule>/.git`、不要用 `git submodule deinit -f` 清工作区，否则子模块内的
  本地改动（如上面第 1 条）会丢。
- 不要在子模块里 `git push`（除 `reelbench-skills` / `TaoMate-H3` 是自有仓库外，hypit、FastVideo
  是他人仓库，没有权限）。

## 本仓库不包含的内容

1. **大体积媒体**（约 9 GB）：`h3-films/_deliver`、`_post`、`_review`、`_tts`、`_audio_orig`、
   `_a100verify` 等目录下的成片/切片/参考视频/音频/帧图，以及 `videos/**` 里的素材文件。
   原因：GitHub 单文件硬上限 100 MB，本地最大单文件 398 MB，14 个文件超过 50 MB，无法入库。
   媒体请放在本机/对象存储/远端 GPU 上，靠清单（`manifest*.json`、`*_p_list.txt`、`*.srt`）复现。
2. **敏感凭据**：`*.pem`、`*.key`、`.env` 等已在 `.gitignore` 中拦截。
   注意仓库根目录存在 `kehu-JiangLong.pem`（远端 GPU 私钥，与 `~/.ssh/` 同一把），**不要提交**，
   也建议不要留在仓库目录里。

## 远端 GPU 服务器与换机迁移

本机（macOS）只做**编排与后处理**，视频生成跑在远端 GPU 上。
截至 2026-09-19 的机器是 `ssh kehu`（2×A100-PCIE-40GB / 125 GB 内存 / 148 GB 盘 / 驱动 580.95.05 /
Ubuntu 22.04，华为云泰国机房），其上跑 ComfyUI v0.36.0 + MiniMax-H3 一步直出 768×1344。

> ★ **后续形态：只租 1 张 A100。** 部署步骤不变（`bootstrap/` 七脚本与卡数无关），
> 但启动方式、跑批脚本、内存门槛（单卡 ≥ 96 GB）、时间账都不同。
> **单卡请配套读 `docs/单卡A100部署手册.html` + `deploy/single-gpu/README.md`。**
> 一句话：单卡只影响排队长度（373 镜 3.4 h → 6.6 h），不影响单镜速度（都是 558 s）。

**要换服务器时，先读这几份，不要凭印象重建：**

| 文档 | 用途 |
| --- | --- |
| `docs/新服务器部署手册.html` | 详尽版：目标机硬要求、完整清单（软件 commit / 6 个权重 / 脚本 / 输入资产）、逐条部署命令、17 条血泪坑位、实测基准、验收清单 |
| **`docs/单卡A100部署手册.html`** | **单卡版**：卡数对照、内存门槛、单卡跑批、时间账推导、单卡坑位 10 条 |
| `deploy/README.md` | 可执行版（Agent 入口）：两条恢复路径 + 全部命令 + 路径速查 |
| `deploy/single-gpu/README.md` | 单卡可执行版（Agent 入口）：接手检查清单 + 单卡跑批命令 |

```bash
# 从零重建一台（目标机上依次执行）
bash deploy/bootstrap/00_check_target.sh    # 体检，只读（会自动判定单卡/双卡模式）
bash deploy/bootstrap/01_provision_os.sh    # apt / swap / BBR / 驱动核对
bash deploy/bootstrap/02_build_stack.sh     # venv + torch cu130 + ComfyUI + 3 节点
bash deploy/bootstrap/03_dl_weights.sh      # 75 GB 权重（最慢，挂 tmux）
bash deploy/bootstrap/04_launch_comfy.sh single   # 单卡用 single；双卡用 both
bash deploy/bootstrap/verify.sh --run       # 端到端验收，真出一镜

# 本机侧推资产
bash deploy/bootstrap/05_push_assets.sh <新机别名>
```

几个最容易出错的点（完整版见手册 §10）：

- **旧 `build_env.sh` 里的 ComfyUI commit 与 `comfy-kitchen` 版本都是过时的**，照抄会掉 28% 速度。
  现行标准是 ComfyUI `ee71d5c4`（v0.36.0）+ `comfy-kitchen==0.2.34`。
- **两阶段流程（`run_server.sh`）已废弃**——它依赖的 `ui_to_api.py` / `s2_adapt.py` 在机器上已不存在。
  现行是**一步直出**，不要试图"修复"它。
- **权重文件名是硬契约**（工作流 json 里写死），改名直接 400 `value_not_in_list`；
  Text Encoder 还必须在 `text_encoders/minimax_h3/` 子目录下。
- **`deploy/server-assets/inputs/` 里的干声与参考图不在 git 里**（被 `.gitignore` 拦），
  但生产必需，换机时必须手动传；其中三部曲干声的这份是唯一备份。

## 提交前的自检

```bash
# 1) 别把大文件带进来（直接看 HEAD 里最大的 blob，不依赖工作区）
git ls-tree -r -l HEAD | awk '$2=="blob"{print $4, $5}' | sort -rn | head

# 2) 确认没有凭据/嵌套仓库内容混入
git ls-files | grep -iE '\.(pem|key|env)$|node_modules/'

# 3) 父仓库里应当只有 4 个 gitlink
git ls-files -s | awk '$1=="160000"'
```

## 远端接入

GitHub 22 端口在本机网络被阻断（`ssh: connect to host github.com port 22: Operation timed out`），
父仓库 remote 已改用 443：

```bash
git remote -v
# origin ssh://git@ssh.github.com:443/realreadpaper/videoHub.git
```

想让 `git@github.com:...` 直接可用，在 `~/.ssh/config` 加入：

```
Host github.com
  HostName ssh.github.com
  Port 443
  User git
```
