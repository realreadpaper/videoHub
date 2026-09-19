# videoHub 项目长期记忆

> ★ **完整判据在 `DETAIL.md`**（本文件是索引，超限会被截断，别往这里堆细节）。
> 生产规则 → `待生成_现代婚姻三部曲/AGENTS.md`（§零 硬标准 / §二 栅格 / §八 坑位 17 条）
> 出片 → 技能 `h3-key-shot-batch`；拆解/下载/验收 → `video-breakdown` / `douyin-download` / `acceptance-doc`
> 换机 → `deploy/README.md` + `docs/{新服务器,单卡A100}部署手册.html`；流程+加速 → `docs/H3生成流程与加速白皮书.html`
> ⚠ 工程里残留 `/Users/hejianglong/...` 旧机路径（本机 `jianglong`）→ file not found

## 当前状态（2026-09-19）

373 镜复刻 = `videos/douyin_refs/2026-09-18/_remake/`。★ **全量进度仅 12/373**，其余 361 镜未开始。三部曲跑了 f1s01/f2。
kehu 将关停；迁移包 `deploy/`（单卡版 `single-gpu/`）**已逐文件 md5 核对：1413 文件 0 漏拉 0 损坏**。

## ★★★ 剧本硬标准（用户：「以后的剧本都要这么要求」）

**S1 零字幕**（无 `<d>` + `strict_output_constraints` + 文字道具 `illegible`）·
**S2 表情**（微表情 ≥3、情绪过渡 ≥1、静态词 =0）· **S3 位置逻辑**（多人镜方位锚点 ≥1、单人镜朝向锚点 ≥1）·
**S4 技术对齐**（末段时间戳 = scene_duration）。
三关：`_pipeline/review_v3.py` 扫 → 试拍目视 → 写回 AGENTS.md。★ 扫描只查「有没有写」，**好坏必须目视**。
`<d>[Chinese]"…"</d>` 同时驱动口型**与**屏幕字幕 → **彻底剥离**比只去引号保险。**干声定口型，神态全由 prompt 定**。

## ★★ 四条实测铁律

1. **步数不是杠杆**：4/6/8/12 步 SSIM 非单调 → **保持 4 步**，省下的时间换多 seed。
   ★ **全量线 `wf_full/` = 单图(16 节点)+4 步；Hybrid 三图(18 节点)+8 步只用于试点/关键镜**，别搞混。
2. **Hybrid 双端钉帧只保证首尾**，中段仍漂 → 推镜倾向压过 prompt 措辞。
3. **关键镜提示词必须人工写**：`build_directing.py` 动作池与镜头**大量错配**、EN 译文会幻觉；
   **角色与关系要显式写进 `<Characters and their relationship>` 段**，只写 `speaker` 名无效。
4. ★★ **参考帧必须零文字**：模型会把帧内字幕**原样画进成片**。
   解法 `rescrub_sub.py`＝固定行带 y∈[856,1005] + 「列密度>0.4 的列数」判据（取 ≥25）；
   ⚠ 阈值 0.04 会误判 93.8% 的帧。验收 `_diag/REFSCAN.jpg`＋`check_refs_all.py`。

## 复刻切分：单位 = 台词句，不是镜

**1 句台词 = 1 生成单元**（语音覆盖 96.6–99.7%）。工具 `h3-key-shot-batch/scripts/build_units.py`。
★ **耗时是帧数平方级** → **短镜每秒更便宜**（22 帧 19 s/镜秒 vs 354 帧 38 s/镜秒）→ 切短**无取舍**。
1.6s 短单元**不可合并**（金句是命门）；安全下限 **39 帧**、常用 **107 帧**。⚠ ASR 会并句 → **人工拆**。

## 服务器 kehu（124.81.178.140）

2×A100-PCIE-40G / 125 GB 内存 / 华为云泰国。★ **连不上先怀疑本机 Clash Verge TUN** → 技能 `ssh-tun-hijack-diagnosis`。
双卡 = 双实例 `:8188`/`:8189`（b 需 `--database-url …instance_b.db` 防锁死）；单卡只起 `:8188`、**不要 database-url**。
启动带 `--vram-headroom 1 --use-ck-attention` + `setsid nohup … < /dev/null &`。
★ **内存病根 = 空闲实例白吃 57 G** → 先查 `/queue`，停空闲实例比加 swap 有效。
★ **回传慢 = 跨境丢包**，开 BBR 即解。★ 服务器共享，动队列前先看是不是自己的活。
★ **A100 冷启 = 热态 4–5 倍**（最大记账陷阱）。单卡挂钟 = 双卡报告的「GPU 总机时」（1.95×）。

## ★ 会静默毁结果的坑（完整 17 条见 AGENTS.md §八 / DETAIL.md）

- ★ **`http_proxy` 劫持 localhost**：`curl 127.0.0.1:8188` 走代理拿 502 → 误报「ComfyUI 没响应」。
  解法 `export no_proxy="127.0.0.1,localhost,::1"`。★ **下载权重的脚本不能加**。
- ★ **`pkill -f <name>` 会匹配执行它的 ssh 命令行 → 自杀式断连**；用 `ps -eo pid,args | grep "[x]xx"`。
- **zsh 不做单词切分**（用 `${=VAR}`）；`cd X && A & B &` 里 **B 跑在原 cwd** → 后台用绝对路径。
- ★ **门禁脏状态**：`gates*/<k>.lock` 残留 → 该镜**永久跳过**；`<k>.fail` = 失败被跳过。
  接手前 `find gates* -maxdepth 1 -type d -name '*.lock' -exec rmdir {} \;`。
## 交付铁律 & 画面风格

不烧字幕，外挂 srt/vtt 同名同目录 · 禁字三层防线（NO_TEXT_CLAUSE + `build.py` 终检 + `scan_text_band.py` 目视）·
字幕绝对时间 = **Σ前序镜实际时长** · 产品镜用 `<Subject P>` 锚定、参考图 `<Picture N>`。
**禁「油腻」**：正向 `matte finish` + `visible pores` + `neutral white balance` + `muted naturalistic colour`；
负向 7 条见 DETAIL.md §「不油腻」。
