# videoHub 项目长期记忆

> ★ **完整判据在 `.workbuddy/memory/DETAIL.md`**（本文件是索引，超限会被截断，别往这里堆细节）。
> 生产规则 → `待生成_现代婚姻三部曲/AGENTS.md`（§零 硬标准 / §二 栅格 / §八 坑位 17 条）
> 出片流程 → 技能 `h3-key-shot-batch`（★ 旧记忆里的 `h3-film-production/` **不存在**）
> 拆解 / 下载 / 验收 → 技能 `video-breakdown` / `douyin-download` / `acceptance-doc`
> 换机 → `deploy/README.md` + `docs/{新服务器,单卡A100}部署手册.html`
> ⚠ 工程里残留 `/Users/hejianglong/...` 旧机路径（本机是 `jianglong`）→ 直接跑 file not found

## 当前状态（2026-09-19）

抖音三片复刻工程 = `videos/douyin_refs/2026-09-18/_remake/`（git 根 `.gitignore` 排除 mp4/wav/png/jpg）。
373 镜时间轴 + 参考帧已就绪。**停在「6 镜审查」**（`_remake/六镜审查.html`），用户确认后铺量。
三部曲 24 镜未全量出片。服务器 kehu 将关停，迁移包在 `deploy/`（含 `single-gpu/`）。

## ★★★ 剧本硬标准（用户：「以后的剧本都要这么要求」）

**S1 零字幕**（无 `<d>` 标签 + 有 `strict_output_constraints` + 文字道具 `illegible`）·
**S2 表情**（微表情 ≥3、情绪过渡 ≥1、完全静态词 =0）· **S3 位置逻辑**（多人镜方位锚点 ≥1、单人镜朝向锚点 ≥1）·
**S4 技术对齐**（prompt 末段时间戳 = scene_duration）。
三关：`_pipeline/review_v3.py` 扫 → 试拍目视 → 写回 AGENTS.md。★ 扫描只查「有没有写」，**好坏必须目视**。
机理：`<d>[Chinese]"…"</d>` 同时驱动口型**与**屏幕字幕，尾部 `no subtitles` 压不住 → **彻底剥离**比只去引号保险。
**干声定口型，面部神态全由 prompt 文字定**（写满 `unnervingly calm` = 木头人）。

## ★★ 四条实测铁律

1. **步数不是杠杆**（2026-09-19）：同镜 4/6/8/12 步 SSIM **非单调（混沌）** → **保持 4 步**，省下的时间换多 seed 备选。
2. **Hybrid 双端钉帧只保证首尾**，中段仍漂（模型在两端间用自身先验插值）→ 4 步下推镜倾向压过 prompt 措辞。
3. **关键镜提示词必须人工写**：`build_directing.py` 动作池与镜头**大量错配**（拥抱戏写成「夹肉放进嘴里」），
   EN 译文还会幻觉。**角色与关系必须显式写进 `<Characters and their relationship>` 段**（身份+彼此关系+该镜微表情）才影响表演，只写 `speaker` 名无效。
4. ★★ **参考帧必须零文字**：模型会把参考帧里的字幕**原样画进成片**（且自己还会幻觉中文烧字幕）。
   v3/v4 清洗靠 `find_hits` 出框，实测**漏掉 9/373 帧**（dy3_s059/s119/s138/s054/s100/s129/s013、dy2_s096/s098，字幕原样留着）。
   现行解法 `rescrub_sub.py`：**固定行带 y∈[856,1005]** + 计数判据 —— 带内「列密度 > 0.4 的**列数**」
   真字幕 **153~158**、其它帧 **≤8**，故取 **≥25** 才动手 → 按列段掩整带高 + `cv2.inpaint`。
   ⚠ 低阈值（0.04）会把 **93.8%** 的帧误判成有字、整条带糊掉。验收看 `_diag/REFSCAN.jpg` + `check_refs_all.py`。

## 复刻切分：单位 = 台词句，不是镜

**1 句台词 = 1 生成单元**（语音覆盖 96.6–99.7%、句间隙中位 0.00s）。工具 `h3-key-shot-batch/scripts/build_units.py`。
113→74 / 128→78 单元。★ **耗时是帧数平方级** → **短镜每秒更便宜**（22 帧 19 s/镜秒 vs 354 帧 38 s/镜秒）→ 切短**无取舍**。
1.6s 短单元**不可合并**（反应句/金句是命门）；安全下限 **39 帧**；常用 **107 帧**。⚠ ASR 会把相邻说话人并进一句 → **人工拆**。

## 服务器 kehu（124.81.178.140）

2×A100-PCIE-40G / 125 GB 内存 / 华为云泰国。★ **连不上先怀疑本机 Clash Verge TUN**，不是密钥 → 技能 `ssh-tun-hijack-diagnosis`。
双卡 = 双实例 `:8188`/`:8189`（b 实例需 `--database-url …instance_b.db` **防锁死**）；单卡 = 只起 `:8188`、**不需要 database-url**。
启动带 `--vram-headroom 1 --use-ck-attention`，用 `setsid nohup … < /dev/null &`。
★ **内存病根 = 空闲实例白吃 57 G** → 先查 `/queue`，**停空闲实例比加 swap 有效**。
★ **回传慢 = 跨境丢包**，开 BBR 即解（0.11→6 MB/s）。★ **服务器是共享的**，动队列前先看是不是自己的活。
★ **A100 冷启 = 热态 4–5 倍**（全项目最大记账陷阱）。单卡换算：双卡报告的「GPU 总机时」= 单卡挂钟（加速比 1.95×）。

## ★ 会静默毁结果的坑（完整 17 条见 AGENTS.md §八 / DETAIL.md）

- ★ **`http_proxy` 劫持 localhost**（最阴）：环境有 `HTTP_PROXY` 时 `curl 127.0.0.1:8188` 走代理拿 502
  → 检查脚本误报「ComfyUI 没响应」。解法 `export no_proxy="127.0.0.1,localhost,::1"`。★ **下载权重的脚本不能加**。
- ★ **`pkill -f <name>` 会匹配执行它的 ssh 命令行 → 自杀式断连**；用 `ps -eo pid,args | grep "[x]xx"` 取 PID。
- **zsh 不做单词切分**（`set -- $VAR` 不拆，用 `${=VAR}`）；`cd X && A & B &` 里 **B 跑在原 cwd** → 后台提交用绝对路径。
- `SaveVideo.format/codec` 是动态 combo → 参数静默消失；API 工作流顶层不能有 `_meta`；**`s2_adapt.py` 只吃 API 格式**。
- ★ **门禁脏状态**：`gates*/<k>.lock` 残留 → 该镜**永久跳过**；`<k>.fail` = 失败被跳过。接手前 `find gates* -name '*.lock' -exec rmdir {} \;`。

## 交付铁律 & 画面风格

不烧字幕，外挂 srt/vtt 同名同目录 · 禁字三层防线（NO_TEXT_CLAUSE + `build.py` 终检 + `scan_text_band.py` 目视）·
字幕绝对时间 = **Σ前序镜实际时长** · 产品镜用 `<Subject P>` 锚定、参考图 `<Picture N>`。
**禁「油腻」**：`matte finish` + `visible pores` + `neutral white balance` + `muted naturalistic colour`；
负向 `no oily sheen / no glossy specular highlights / no beauty-filter / no plastic or waxy skin / no HDR glow / no over-sharpening / no orange or teal cast`。
