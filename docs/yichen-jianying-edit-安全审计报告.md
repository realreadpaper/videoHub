# 🔍 安全审计报告

## 📊 执行摘要

- **审计对象**: `yichen-jianying-edit`
  - 公开源：`https://github.com/mcncarl/yichen-skills/tree/main/yichen-jianying-edit`
  - 本地副本：`/Users/jianglong/Desktop/videoHub/repos/jianying-headless/skills/yichen-jianying-edit/`
  - ★ 两者经 `diff -rq` 逐字节比对 **完全一致**（SKILL.md sha256 同为 `5d6b223ad14e81fbc24dfb1b4887b248d0b3266e60d55ff41d81808cb1266afc`），
    故本次审计结论对两个来源同时有效。
- **审计方式**: 纯静态文本分析（只读，未执行任何被审内容）
- **发现问题总数**: 0 个
  - 🔴 Malicious（恶意）: 0 个
  - ⚠️ Suspicious（可疑）: 0 个
  - 📝 信息性提醒: 2 个（非风险项，不计入风险总数）
- **安全评分**: **85 / 100**
  - 依据评分规则：无可执行风险行为、无投毒风险，但有代码 → 85 分（Benign 区间 76–100）

---

## 🔴 Malicious（恶意）风险发现

✅ 未发现 Malicious 风险

---

## ⚠️ Suspicious（可疑）风险发现

✅ 未发现 Suspicious 风险

**逐项排除说明**（对照定级标准主动核查）：

| 检查项 | 结果 |
| --- | --- |
| 下载 + 执行（`curl \| bash` 等） | ❌ 无。全仓库代码中零网络调用 |
| 读取敏感信息 + 外送 | ❌ 无。未触碰 `~/.ssh`、`~/.aws`、`.env` 等 |
| 自动执行破坏性命令 | ❌ 无。无 `rm`/`unlink`/`shutil.rmtree`/系统配置修改 |
| 隐蔽执行 + 危险操作 | ❌ 无。无 `nohup`/`disown`/日志清除 |
| 权限提升 | ❌ 无。无 `sudo`、无 `chmod 777` |
| 全局安装未固定版本依赖 | ❌ 无。整个 Skill 不含任何 `pip install` / `npm install -g` / `brew install` |
| 非官方源安装 | ❌ 无 |
| 从代码仓库安装且未固定 SHA | ❌ 无 |

---

## 📝 信息性提醒（非风险项）

### 1. `asr_once.py` 读取本机 ASR 凭据（作者设计如此，非投毒）

- **位置**: `scripts/asr_once.py:13,86-104`
- **代码片段**:
  ```python
  EXECUTOR = Path(os.environ.get('YICHEN_ASR_EXECUTOR', str(Path.home() / 'scripts/transcribe.py')))
  ...
  executor = runpy.run_path(str(EXECUTOR))
  token = executor.get('ACCESS_TOKEN', '')
  ...
  log = process.stdout.replace(token, '[credential redacted]')
  os.chmod(folder / 'executor.log', 0o600)
  ```
- **说明**: 该脚本是**可选**的 ASR 去重包装器。它从**用户自己安装的本机执行器**
  （`$YICHEN_ASR_EXECUTOR`，默认 `~/scripts/transcribe.py`）中读取 `ACCESS_TOKEN` / `APP_ID`，
  用于调用**该凭据对应的官方转写服务**。符合审计规则中"读取特定凭证调用其对应官方服务"的情形。
  凭据处理方式是**用心的**：日志中显式做 `[credential redacted]` 替换、落盘文件 `0600`、
  state 里记录 `credential_persisted: False`、异常时不重复提交。
  **本机当前未安装该执行器**（`~/scripts/transcribe.py` 不存在），且主链路不依赖它。
- **建议**: 无需处理。若使用，建议把 token 放 Keychain 或环境变量而非明文写入脚本。

### 2. `runpy.run_path` 会执行目标文件的模块级代码（设计选择，非漏洞）

- **位置**: `scripts/headless_draft.py:63`、`scripts/asr_once.py:85`
- **说明**: 两处 `runpy.run_path` 都会**执行**目标文件的模块级语句。
  但目标是**本地、用户可控且经 SHA-256 固定校验**的文件：
  `headless_draft.py` 在运行前先逐文件校验 `engine/` 下 13 个组件的 sha256（见 `PINS`），
  哈希不符直接 `SystemExit`。这属于**安全正面设计**，不是风险点。
- **建议**: 无需处理。

---

## 📋 详细检查结果

### 命令执行与权限检查

- **发现次数**: 0 次风险（7 处 `subprocess`，全部为固定参数列表，无 `shell=True`）
- **详细列表**:
  - `scripts/headless_draft.py:63` — `runpy.run_path(BACKEND/'jy14_headless.py', run_name='__main__')`，目标已哈希固定
  - `scripts/asr_once.py:85` — `runpy.run_path(EXECUTOR)`，目标为用户自备执行器
  - `scripts/asr_once.py:97` — `subprocess.run([sys.executable, EXECUTOR, source, '--transcribe-only'])`，列表参数
  - `scripts/edit_plan.py:47` — `subprocess.check_output(['ffprobe', ...])`，列表参数
  - `scripts/edit_plan.py:229` — `subprocess.run(['ffmpeg', ...])`，列表参数
  - `scripts/edit_plan.py:247` — `subprocess.run(['ffmpeg', ...])`，列表参数，输入经 stdin 管道
- **权限提升**: 无 `sudo`。`os.chmod` 仅两处，均为把**自己新写的文件**设为 `0o600`（收紧权限，非放开）。

### 文件操作与敏感路径检查

- **发现次数**: 0 次风险
- **详细列表**:
  - 未出现 `~/.ssh`、`~/.gnupg`、`~/.aws`、`~/.gcloud`、`~/.kube`、`.env`、`credentials`、`private_key` 等路径
  - 删除/移动操作：`unlink`、`shutil.rmtree`、`os.remove`、`rm -rf` **均未出现**
  - 写入操作全部限定在调用方显式传入的 `--out` / `--work` 路径，且大量使用
    `exist_ok=False` + `mode=0o700`，即"目录已存在就报错，不覆盖"
  - `edit_plan.py:224` 明确拒绝覆盖已存在的输出：`if output.suffix.lower() != '.wav' or output.exists(): raise`

### 网络请求检查

- **发现的 URL**: 仅 5 条，**全部是 Markdown 文档里的普通超链接**，无任何代码级请求
  - `README.md:6` — `https://github.com/mcncarl/yichen-skills/tree/main/yichen-jianying-edit`
  - `README.md:11` — `https://github.com/mcncarl/jianying-headless`
  - `references/dependencies-and-notices.md:3` — 同上核心项目
  - `references/dependencies-and-notices.md:8` — `https://github.com/wenshui330/jy-draftc`（MIT 来源声明）
  - `references/dependencies-and-notices.md:9` — `https://github.com/GuanYixuan/pyJianYingDraft`（Apache-2.0 来源声明）
- **代码中的导入检查**: 无 `requests` / `urllib` / `httpx` / `aiohttp` / `socket` / `fetch` 导入
- **Base64 编码检测**: 未发现可疑编码串（脚本中仅出现 sha256 十六进制摘要，属正常哈希固定）

### 远程脚本深度分析

本次未触发（不存在任何"自动下载并执行远程脚本"的行为），故无需深度分析。

### 依赖安装风险检查

- **全局安装检测**: ✅ 无。整个 Skill 不含任何依赖安装命令
- **虚拟环境检查**: 不适用（无依赖安装行为）
- **依赖来源检查**: ✅ 无。不涉及任何包管理器或索引源

### 行为与描述一致性

- SKILL.md 声明"默认交付可继续编辑的原生草稿，用户明确要求成片时才导出"，
  与实际脚本行为一致（`headless_draft.py` 仅按子命令分发 `edit`/`export` 入口）
- SKILL.md 声明"不下载、解锁、伪造授权"、"不自动永久删除文件"、"不强制结束进程"，
  在代码层面均有对应约束，**未发现描述与实际行为不符**
- SKILL.md 声明"不包含剪映引擎"——属实，`engine/` 位于私有核心仓库，Skill 内不含

---

## 💡 总体建议

1. **该 Skill 可以安装**。它本质上是一组"参数校验 + 哈希固定 + 本地子进程编排"的脚本，
   不含任何供应链投毒面：无网络、无远程执行、无依赖安装、无敏感路径访问、无破坏性操作。
2. 设计上有几处值得肯定的安全实践：运行前逐文件校验引擎 sha256、输出目录 `exist_ok=False`
   防覆盖、凭据出日志前做 redacted 替换、落盘文件 0600、失败保留现场不自动重试。
3. 安装后建议固定来源：该 Skill 无版本号，公开仓库 `main` 分支可随时更新。
   本次安装已记录全部文件 sha256（见下），日后可比对确认未被替换。
4. **注意**：审计通过 ≠ 本机可运行。安全性与可运行性是两个独立问题，本机存在硬性环境不满足
   （详见安装报告）。

### 本次审计基准哈希（安装后可比对）

```
078b938859a33048571dfed98283639e37593aed1b548648bb82a2a574a90981  LICENSE
bc54193a75619189cfd04947aaf13da6703f48c633af85d160266d0d48a6cff3  references/headless-macos.md
4a9533736b3fdcabca1d52edb6cb9df49cfe2b3d44cec7aaa4cdc0faf2fa7b0d  references/plan-format.md
7549a8d127d6fde9eb5533b7711ba0cc969dea2958a1d7b16bd2ac4413d9edb2  references/export-macos.md
5b33501a9838aeeec94cd7fb35569bc00e3b355645cdf972769dcd5a6f2d10d7  references/edit-existing-macos.md
2a2300059b076684dd4518d63730c1fb6dac7b95596cbe40db6f194009652162  references/dependencies-and-notices.md
a6544ea5d52750b724cd23ead6771604b56df17165f9a5d3518340b20753bbc4  references/editing-and-qc.md
4f09e413e5df8495cc96587ddde41d90693cd1ab52f3d1758e4466bbc3f5af07  agents/openai.yaml
4efda99047e22e2608c2527ca5daca02199df0d5e7a47f4493acce64462c4853  README.md
dd1462a4921336d40e0262200c8837a417d64c985957e37d5c44631a4fa09dee  scripts/asr_once.py
1483d2f5e545a9a24668ddaf26a9f99506fccfa5232414da000104ca4e5fcaf1  scripts/edit_plan.py
c36a60b74d310a79500e7e80956ea3d8da42facb03057b8faeddcb3c45a90223  scripts/headless_draft.py
5d6b223ad14e81fbc24dfb1b4887b248d0b3266e60d55ff41d81808cb1266afc  SKILL.md
```

---

## ✅ 审计结论

**风险等级**: ✅ **Benign（可信）**

**使用建议**: ✅ **可以安全使用**（85 分）——无投毒风险，无供应链风险，无环境破坏风险。
