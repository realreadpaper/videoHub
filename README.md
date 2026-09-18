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
| `videos/` | 广告与 demo 工作区（`douyin-ad`、`douyin-ad-2`、`demo`、`selfhosted-check`）的编排代码与清单 |
| `fastvideo-configs/` | FastVideo 推理/服务 YAML 配置（4090 / A100 / 多卡 FSDP 等） |
| `fastvideo-remote/`、`remote-render/` | 远端 GPU 环境搭建与远程渲染脚本 |
| `docs/`、`_meta/` | 成本测算、站点资料 |
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
