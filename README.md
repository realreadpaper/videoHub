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

## 本仓库不包含的内容

以下内容被 `.gitignore` 排除，请按需各自获取：

1. **外部代码仓库**（各自独立 remote，不在此仓库内提交）：
   - `repos/hypit/` → https://github.com/hypit-ai/hypit
   - `repos/FastVideo/` → FastVideo（上游发行包，非 git 克隆）
   - `reelbench-skills/` → https://github.com/eternityspring/reelbench-skills
   - `TaoMate-H3/` → https://github.com/TaoLiveAIGC/TaoMate-H3
2. **大体积媒体**：`h3-films/_deliver`、`_post`、`_review`、`_tts`、`_audio_orig` 等目录下的
   成片/切片/参考视频/音频/帧图（约 8 GB `*.mp4` 等），以及 `videos/**` 中的素材文件。
3. **敏感凭据**：`*.pem`、`*.key`、`.env` 等（远端 GPU 私钥等）。

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
