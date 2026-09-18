# jianying-headless 配置报告 + yichen-jianying-edit 安装报告

日期：2026-09-19
本机：MacBook Pro 15,1（2018）· Intel Core i7-8750H · x86_64 · macOS 15.7.9

---

## 一、结论先说

| 项目 | 状态 |
| --- | --- |
| ① 核心仓库拉到本地 | ✅ 完成（`repos/jianying-headless`，commit `bb1e72c`） |
| ② Skill 安装 | ✅ 完成（`~/.workbuddy/skills/yichen-jianying-edit/`，安全审计 85 分 Benign） |
| ③ 环境变量配置 | ✅ 完成（`JIANYING_HEADLESS_ROOT` 已写入 `~/.zshrc`） |
| ④ 本机跑通完整链路 | ❌ **不可能** —— 三个硬性条件不满足，见下 |
| ⑤ 部分能力本机可用 | ✅ **`edit_plan.py` 口播剪辑支线已实测跑通** |

**一句话**：仓库和 Skill 都装好了、接线也通了，但"生成/导出剪映原生草稿"这条主链路
在本机**物理上无法运行**——因为它要链接你本机安装的剪映程序库，且强制要求 Apple Silicon。

---

## 二、硬性阻塞（三个，均无法通过改配置绕过）

这些是工具**自己在代码里写死的前置检查**，不是我们的猜测：

| # | 要求 | 本机实际 | 证据 |
| --- | --- | --- | --- |
| 1 | **Apple Silicon (arm64)** | Intel x86_64 | `tools/build_native_codec.py:47` 源码 `require(platform.machine() == 'arm64', ...)`；实测输出 `This native bridge profile requires Apple Silicon macOS` |
| 2 | **macOS 26.0+** | macOS 15.7.9 | 仓库 README「固定 codec 的最低系统版本为 26.0」 |
| 3 | **本机安装剪映专业版 11.4.0 / 11.4.2** | 未安装 | 要链接 `/Applications/VideoFusion-macOS.app/Contents/Frameworks/libvideoeditor.dylib`；实测该 App 不存在 |

**为什么绕不过去**：这个工具不是"独立剪辑软件"，它需要**编译一个桥接动态库**，
去链接**用户本机已安装的剪映**提供的 `libvideoeditor.dylib`。
构建脚本还会核对：

- 剪映的 `CFBundleShortVersionString` 必须 ∈ {11.4.0, 11.4.2}
- `CFBundleIdentifier` 必须是 `com.lemon.lvpro`
- 该 dylib 的 sha256 必须精确等于 `632c8ddd…`（11.4.2）或 `a1693070…`（11.4.0）
- 应用签名 `TeamIdentifier` 必须是 `X2JNK7LY8J`
- 编译产物 sha256 必须精确等于 `b6533eb5…`，否则**构建失败并保留记录**

也就是说，**没有本机剪映 = 没有可链接的库 = 构建无法进行**。
而 `-arch arm64` 与 `platform.machine()=='arm64'` 两道检查，Intel 机器直接出局。

### 当前的报错链（已修复到最后一环）

```
# 修复前（Skill 装在技能目录，找不到核心仓库）
Jianying Headless checkout unavailable. ... set JIANYING_HEADLESS_ROOT ...

# 修复后（已越过路径检查与 13 个引擎文件的 sha256 校验）
ValueError: IO/codec component unavailable: jy14_codec_hardened_11_4;
            build with tools/build_native_codec.py
```

**这是预期的终点**——说明 Skill ↔ 核心仓库的接线完全正常，
只差"构建本地桥接"这一步，而这一步在本机永远无法完成。

---

## 三、本机现在就能用的部分（已实测）

`scripts/edit_plan.py` 是**唯一不依赖剪映、不依赖 Apple Silicon** 的组件——
它只吃 Python 3.9+ 和 ffmpeg/ffprobe，做的是**口播语义剪辑 + 帧对齐字幕轴编译**。

**实测记录**（合成素材 10s / 30fps / 含音轨）：

```bash
# 1. compile
$ python3 ~/.workbuddy/skills/yichen-jianying-edit/scripts/edit_plan.py \
    compile --plan edit-plan.json --out compiled-v1
{"duration": 3.6, "segments": 2, "subtitles": 2, "sfx": 1}

# 2. render-audio
$ python3 .../edit_plan.py render-audio \
    --plan compiled-v1/compiled.json --out voice-v1.wav --work audio-render-v1
{"status": "completed", "samples": 172800, "duration": 3.6, "video_rendered": false}
```

产出（`compiled-v1/`）：

| 文件 | 内容 |
| --- | --- |
| `compiled.json` | 完整时间映射（源→目标微秒、帧号、保留区间、字幕、音效） |
| `subtitles.srt` | **帧对齐的剪后字幕轴** |
| `transcript.md` | 剪后转写稿 |

编译出的字幕轴（源 0.08–2.32 / 3.08–5.92，速度 1.5×）：

```srt
1
00:00:00,033 --> 00:00:01,587
这里是第一句

2
00:00:01,633 --> 00:00:03,587
这里是后一句
```

**为什么这段对你现在的活儿有用**：它解决的正是你在 `AGENTS.md` 交付铁律第 3 条里
反复踩的那个问题——**字幕绝对时间必须按实际保留区间累加，不能按"镜号 × 单镜时长"算**。
`edit_plan.py` 的 `project()` 函数就是干这个的：
删掉的源区间会被正确跳过，保留区间的目标时间按速度重算，再转成帧对齐的 SRT。
而且它是**先算后校验**：`validate_compiled()` 会反向核对
源时长/目标时长/速度三者是否自洽、时间线有无空隙重叠、字幕有无越界。

**能白拿的能力**（本机可用）：

- `jianying-edit-plan/v1` 计划 → 帧对齐 SRT + 剪后转写稿 + 复核 WAV
- 保护词区间校验（`protect`）：删除操作若碰到受保护发音会**报错拒绝**，不会静默删掉重说
- 速度链补偿（`tempo_filters`）：>2× 或 <0.5× 自动拆成多级 `atempo`，避免失真

---

## 四、尚不可用的能力（需要 Apple Silicon + 剪映）

| 能力 | 命令 | 阻塞原因 |
| --- | --- | --- |
| 生成可编辑的原生草稿 | `headless_draft.py build` | 需本地桥接 `jy14_codec_hardened_11_4` |
| 登记到剪映首页 | `headless_draft.py publish` | 同上 |
| 修改已有草稿的独立副本 | `headless_draft.py edit` | 同上 |
| 导出原生 MP4 | `headless_draft.py export` | 同上，且只接受剪映 **11.4.2** |
| 可选 ASR 去重 | `asr_once.py run` | 需另装执行器（`~/scripts/transcribe.py`，本机不存在） |

---

## 五、已落地的改动清单

| 位置 | 改动 |
| --- | --- |
| `repos/jianying-headless/` | 已存在的 submodule 检出，确认完整（engine 23 个文件）；**未做任何修改** |
| `~/.workbuddy/skills/yichen-jianying-edit/` | **新建**：从审计基准逐字节复制安装 |
| `~/.zshrc` | **追加** `export JIANYING_HEADLESS_ROOT="/Users/jianglong/Desktop/videoHub/repos/jianying-headless"`（带 `>>> yichen-jianying-edit >>>` 标记块，可整块删除） |
| `docs/yichen-jianying-edit-安全审计报告.md` | **新建**：完整安全审计（0 Malicious / 0 Suspicious / 85 分） |
| `docs/jianying-headless-配置报告.md` | **新建**：本文件 |

⚠️ 注意：`JIANYING_HEADLESS_ROOT` 指向 submodule 目录。
若日后执行 `git submodule deinit repos/jianying-headless`，该路径会失效，需同步更新 `~/.zshrc`。

---

## 六、要继续推进的话，三条路

### 路线 A：换到 Apple Silicon Mac（唯一能跑通完整链路的路）

条件：Apple Silicon + macOS 26.0+ + 自行安装剪映专业版 **11.4.2**。
步骤：

```bash
gh repo clone mcncarl/jianying-headless
cd jianying-headless
python3 tools/build_native_codec.py        # 链接本机剪映，校验哈希
python3 skills/yichen-jianying-edit/scripts/headless_draft.py doctor
```

再用本机已有的 `repos/jianying-headless` 亦可（可整目录拷过去）。
**注意**：需要已授权的 GitHub 账号，且核心仓库 README 注明该预览"尚未完成另一台干净机器的安装验收"。

### 路线 B：本机只吃 `edit_plan.py` 这支线（零额外成本，现在就能用）

适合你当前在做的事——把抖音参考片/自己拍的素材做口播语义剪辑，
拿到**帧对齐的字幕轴**和复核 WAV，然后**手工**在剪映 UI 里落成草稿。
这正好能接上 AI 短剧流水线里"字幕轴按实际时长累加"那个坑。

### 路线 C：先用现有工具链

工程里已有的 `video-breakdown`（阿里云百炼转写 + 分镜拆解）和 `hypit`
覆盖了拆解与编排；剪映环节继续手工。等条件具备再启用本 Skill。

---

## 七、复现命令（验证本报告结论）

```bash
# 1. 确认三个硬阻塞
sw_vers                                              # macOS 15.7.9
sysctl -n hw.optional.arm64                          # 空/0 = Intel
ls -d /Applications/VideoFusion-macOS.app            # 不存在

# 2. 确认桥接无法构建
python3 ~/Desktop/videoHub/repos/jianying-headless/tools/build_native_codec.py
# → This native bridge profile requires Apple Silicon macOS

# 3. 确认 Skill 接线正常（应只卡在 codec 一步）
python3 ~/.workbuddy/skills/yichen-jianying-edit/scripts/headless_draft.py doctor
# → ValueError: IO/codec component unavailable: jy14_codec_hardened_11_4

# 4. 确认本机可用的支线
bash /tmp/test_editplan.sh          # 若脚本已清理，见第三节命令
```
