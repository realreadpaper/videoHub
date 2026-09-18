# videoHub

AI 短剧（H3 + LTX-2.5 两阶段管线）工作区：本机 macOS 只做编排与后处理，重活跑远端 GPU。

## 目录结构

| 路径 | 内容 |
| --- | --- |
| `h3-films/` | 主生产线：剧本/分镜/提示词、字幕、量化报告、后处理脚本 |
| `videos/` | 广告与 demo 工作区（`douyin-ad`、`douyin-ad-2`、`demo`、`selfhosted-check`） |
| `fastvideo-configs/` | FastVideo 推理/服务 YAML 配置 |
| `fastvideo-remote/`、`remote-render/` | 远端 GPU 环境搭建与远程渲染脚本 |
| `docs/`、`_meta/` | 成本测算与站点资料 |
| `.workbuddy/memory/` | 跨会话项目记忆（硬件门控、计时口径等判据） |

## 外部代码仓库（submodule）

以下 4 个仓库以 **git submodule** 引用（见 `.gitmodules`），各自保留独立的 `.git` 与上游 remote，
本仓库只记录提交指针，不复制任何文件内容：

| 路径 | 上游（submodule url） | 记录版本 |
| --- | --- | --- |
| `repos/hypit/` | https://github.com/hypit-ai/hypit | `98000342` (v0.1.10) |
| `repos/FastVideo/` | https://github.com/hao-ai-lab/FastVideo | `c4824c77` (main, 0.2.1) |
| `reelbench-skills/` | https://github.com/eternityspring/reelbench-skills | `18f2f639` (main) |
| `TaoMate-H3/` | https://github.com/TaoLiveAIGC/TaoMate-H3 | `b933d8e9` (main) |

拉到新机器时：`git clone --recurse-submodules <本仓库>`。

更新到上游最新（会移动工作区指针，改动前 `git -C <path> status` 自查）：

```bash
# 全部更新到 .gitmodules 里 branch 指定的最新提交
git submodule update --remote --merge
# 只更新一个
git submodule update --remote --merge repos/hypit
# 然后在父仓库提交新的指针
```

注意：`repos/FastVideo` 是上游 `main` 的精简快照（本地删除了 84 个演示用图片/视频，约 155 MB），
因此 `git submodule status` 会显示该子模块为 modified；需要还原时：

```bash
git -C repos/FastVideo checkout -- .   # 从已下载的对象中恢复
```

`repos/FastVideo` 自身还有 3 个未初始化的子模块（ThunderKittens / cutlass / VBench），按需
`git -C repos/FastVideo submodule update --init --depth 1 <path>`。

## 本仓库不包含的内容

1. **大体积媒体**：`h3-films/_deliver`、`_post`、`_review`、`_tts`、`_audio_orig` 等目录下的
   成片/切片/参考视频/音频/帧图（约 8 GB `*.mp4` 等），以及 `videos/**` 中的素材文件。
   GitHub 单文件硬上限 100 MB，这些文件本地最大 398 MB，无法入库。
2. **敏感凭据**：`*.pem`、`*.key`、`.env` 等（根目录 `kehu-JiangLong.pem` 是远端 GPU 私钥，
   已在 `.gitignore` 中拦截）。

## 远端接入

GitHub 22 端口在本机网络被阻断，已使用 443 端口：

```bash
git remote -v
# origin ssh://git@ssh.github.com:443/realreadpaper/videoHub.git
```

如需让 `git@github.com:...` 直接可用，可在 `~/.ssh/config` 加入：

```
Host github.com
  HostName ssh.github.com
  Port 443
  User git
```
