# PROGRESS · 复刻抖音「短剧 + 家常菜」带货片

## 状态

**工程就绪，等待渲染。** `check` / `plan` 两级已通过；`build` 需在用户终端或远端主机执行。

## 已完成

| 步骤 | 产物 | 结果 |
| --- | --- | --- |
| 取片 | `references/homecook/source.mp4` | 27MB · 296.93s · 720×1282@30 · H.265 |
| 转写 | `transcript.{srt,txt}` + `transcript_lines.txt` | whisper.cpp large-v3-turbo，35s 转完，106 句 |
| 抽帧 | `frames8/` 37 帧 · `frames2/` 148 帧 | 等间隔（场景检测对 H.265 无效，未用） |
| 接触表 | `evidence/sheet_*.jpg` | 全片 2 张 + 卖货段 3 张 + 尾段 3 张 |
| 证据帧 | `product_frame` / `demo_frame` / `drama_frame` / `topzone_frame` | 产品特写、演示、短剧、顶部安全区实测 |
| 拆解 | `ANALYSIS.md` / `TIMELINE.md` | 三段结构 + 6 动作 + 2 个不对称 + 价格拆解 |
| 切片 | `assets/ad-segment.mp4` | 106.0–211.0s → 105.000s · H.264+AAC |
| 工程 | `authors/main.svml` / `recipes.svs` / `runs/final.svrun` | 5 层图形共 28 条 |
| 报告 | `docs/homecook-teardown.html` | 浅色单文件，含可复用语术骨架 |
| 脚本 | `render-clone.sh` | 一键渲染（含环境自检） |

## 验证记录

```
hypit check  → ✓ Source is valid · Outputs 21
hypit plan   → Preflight ready · Requests 5 · Local requests 5 · no Provider charge
```

## 未完成 / 遗留

- [ ] **`hypit build` 成片** —— 本会话环境有删除护栏 + `ps` 限制，Worker 起不来。需在用户终端跑 `render-clone.sh`，或走远端主机 `render-remote.sh`
- [ ] 短剧 A / B 段未复刻（按 BRIEF 的范围决定，只做结构标注）
- [ ] 图形层顶部条在特写镜头会压额头（已知取舍，见报告 07 节）
- [ ] 商用前需替换全部原片素材与 28 条文案

## 关键结论（可迁移）

1. **切换铰链**：用一句剧情台词（"我想吃 XX"）把观众带进产品场景，零违和
2. **举证配比**：省事 : 好吃 = 4 : 1 —— 卖"降低使用成本"的产品都适用
3. **价格四段式**：锚点 → 让利 → 加码（人格化折扣）→ 折算 + 稀缺指令
4. **模板可复制**：与上一支参考片（卤味 / 电饭锅）逐段同构，真正的资产是模板不是片子
