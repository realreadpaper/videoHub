# Progress

## 当前状态

卖货段复刻工程**已通过源码校验与渲染预检**，成片渲染待用户在终端执行。

| 项 | 状态 |
| --- | --- |
| SVML 校验 `hypit check` | ✓ Source is valid · Outputs 18 |
| 渲染预检 `hypit plan` | ✓ Preflight **ready** · Requests 5 · Local requests 5 |
| 模型费用 | **0 元**（全部本地 Provider） |
| 成片渲染 `hypit build` | ✗ 被环境护栏拦截，需在用户终端执行 |

## 阻塞原因（环境，非配置）

`hypit build` 在本会话内无法完成，两个独立的环境限制：

1. **Runtime Worker 无法启动** —— 本会话的批量删除计数已达环境护栏阈值（`SAFE_DELETE_BULK_CONFIRM_REQUIRED` count 50 / threshold 50）。
2. **渲染收尾会 EPERM** —— Hypit 在渲染完成后用 `ps -A -o pid=,ppid=` 枚举进程树回收 Chrome 子进程；当前环境禁用 `ps`。此前对 240 帧级渲染的验证表明画面能渲完，只是清理失败导致结果不落盘。

两者均与配置无关，`Preflight ready` 已经证明工程本身可用。

## 下一步（用户终端）

```bash
cd ~/Desktop/videoHub/videos/douyin-ad
hypit build productions/ad-clone/runs/final.svrun --workspace . --follow
```

需要 `PATH` 里有 `~/.npm-global/bin`（`hypit` 与 `hyperframes` 都在那里）。

## 已装的环境依赖（本次新增）

| 包 | 位置 | 用途 |
| --- | --- | --- |
| `@hypit/hypit@0.1.10` | `~/.npm-global` | 全局 CLI |
| `hyperframes@0.7.101` | `~/.npm-global` | 渲染引擎 CLI（`resolveNodePackageExecutable("hyperframes", ...)` 从 Distribution 解析，必须装在全局） |
| `@hyperframes/producer@0.7.101` | Hypit machine packages | 渲染 Producer |
| `@fontsource-variable/noto-sans-sc@5.3.0` | 全局 + machine packages | 中文正文（可变字重 100–900） |
| `@fontsource/zcool-qingke-huangyou@5.3.0` | 全局 | 站酷庆科黄油体，价格/CTA 展示字 |

## 复刻范围边界

**在范围内**：卖货段（原片 176s–270s，94.2s）的六结构功能、价格三段式、四层图形（痛点条 / 五步条 / 价格卡 / CTA）。

**不在范围内**：短剧剧情段、人物换脸、语音重配、原片烧死字幕的去除。

## 待用户决策

- 是否把 A-roll 替换为自有素材（原片素材仅限研究用）。
- 是否需要把同一套图形层套到自持产品上（改 18 条文本 + 3 个时点即可）。
- 是否需要短剧外壳（本工程只复刻了卖货段，不含剧情引流部分）。
