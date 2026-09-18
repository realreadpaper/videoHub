# Hypit 本地视频工作流

用声明式的 **SVML** 语言描述视频，由本地 Chrome 渲染成片。渲染、媒体处理、图像处理、语音对齐全部在本机完成，**不调用任何生成模型，零 API 费用**。

---

## 一、装在哪

| 组件 | 位置 |
|---|---|
| 源码仓库 | `~/Desktop/videoHub/repos/hypit` |
| 可执行程序 | `~/Desktop/videoHub/repos/hypit/hypit` |
| Skill（AI 助手用） | `~/.workbuddy/skills/hypit` |
| 本项目 | `~/Desktop/videoHub/videos/demo` |
| 渲染缓存 | `~/.cache/puppeteer`（Chrome 153） |
| 引擎包 | `~/Library/Application Support/Hypit/packages` |

## 二、日常三板斧

所有命令在**项目目录**下执行。`hypit` 指仓库里的可执行文件：

```bash
alias hypit='/Users/hejianglong/Desktop/videoHub/repos/hypit/hypit'
```

```bash
hypit check  authors/main.svml   # 1. 校验源码，秒级，只读
hypit plan   runs/final.svrun    # 2. 看这次要跑什么、要花多少钱
hypit build  runs/final.svrun --follow   # 3. 真正渲染
```

渲染完导出成片：

```bash
hypit builds                             # 列出所有 Build，拿 build id
hypit inspect <build-id>                 # 看产物清单
hypit get <build-id> --output final.video --to output/final.mp4
```

中途想看时间线、调参数：

```bash
hypit studio --run runs/final.svrun      # 打开可视化编辑器
```

> `check` / `plan` / `doctor` 都是只读的，随时可跑。**只有 `build` 会真正执行工作。**

## 三、项目结构（推荐，非强制）

```
demo/
  authors/        main.svml        一份 Author 入口，描述视频本身
  recipes/        visual.svs       可复用的视觉配方
  runs/           final.svrun      一次执行意图：要哪个输出
  assets/                          你自己的素材
  packages/                        项目自定义组件（需要时）
  output/                          导出给人看的副本
  hypit.runtime.json               执行环境（已配好）
  .hypit/                          自动生成，别提交
```

小项目可以把 `.svml` / `.svs` / `.svrun` 平铺在根目录，Hypit 不强制这个结构。

## 四、SVML 长什么样

一份 6 秒纯代码渲染的视频，不依赖任何模型：

```xml
<?svml using="@hypit/markup@1"?>
<svml>
  <import as="time"   from="@hypit/timeline-author@1"/>
  <import as="spatial" from="@hypit/spatial@1"/>
  <import as="fonts"  from="@hypit/fonts-open@1"/>
  <import as="film"   from="@hypit/film@1"/>
  <import as="render" from="@hypit/render-hyperframes@1"/>

  <time:Clock id="clock" frame-rate="30"/>
  <time:Timeline id="timeline" clock={clock} end="6s"/>
  <spatial:Canvas id="canvas" width="1080" height="1920"/>
  <fonts:Stack id="font" family="inter" weight="700" style="normal"/>

  <film:Film id="main" canvas={canvas} timeline={timeline.timeline}>
    <!-- 这里放 track：字幕、文字、媒体、卡片… -->
  </film:Film>

  <render:Video id="final" composition={main.composition} timeline={timeline.timeline}/>
</svml>
```

配套的 `runs/final.svrun`：

```xml
<?svml using="@hypit/run-markup@1"?>
<svrun version="1">
  <author source="../authors/main.svml"/>
  <target output="final.video"/>
</svrun>
```

**核心心智模型**：动画锚定在**词**上，而不是秒。改一句台词，时间轴自动重排 —— 这是它能一份工程出 100 个变体的原因。

## 五、执行环境（`hypit.runtime.json`）

已配好 4 个**本地** Provider，零调用费用：

| Endpoint | 能力 | 依赖 |
|---|---|---|
| `media.local` | ffmpeg/ffprobe 媒体处理 | 系统 ffmpeg |
| `hyperframes.local` | Chrome 渲染画面 | Chrome 153 + ffmpeg |
| `image.opencv.local` | OpenCV 图像处理 | Python 环境 |
| `whisperx.local` | 语音转写 + 词级对齐 | Python 环境 + 模型 |

另保留 `hypihub.default`（官方托管生成服务）作为**备用**：只要不执行 `hypit auth login hypihub.default`，它就永远不会产生费用。想用云端的图像/视频/语音生成模型时再登录。

`bindings` 里把「词级对齐」显式绑定到了本地 WhisperX，避免和托管服务产生歧义。

### 还没装的（按需）

`image.opencv.local` 和 `whisperx.local` 需要 Python 环境，首次使用前跑：

```bash
hypit runtime up --endpoint image.opencv.local --endpoint whisperx.local
```

WhisperX 会下载 PyTorch 和语音模型（数 GB）。**只有做「有对白的视频」时才需要它**；纯代码渲染、字幕、动效都不需要。

## 六、已知限制

**渲染必须在你自己的终端里跑。**

AI 助手的沙箱环境禁用了 `ps` 命令，而渲染引擎在收尾阶段用 `ps` 枚举进程树来清理 Chrome 子进程，会报：

```
Render cleanup failed; Error: spawn EPERM
```

画面其实已经渲染完了（240 帧全部捕获、编码都开始了），只是最后清理失败导致结果没落盘。换成你自己的终端就正常。

验证脚本已备好：

```bash
bash ~/Desktop/videoHub/videos/demo/render-demo.sh
```

## 七、加生成模型（可选，要花钱）

需要 AI 生成画面 / 配音时，三条路：

1. **自有 API Key**（BYOK）—— 用 `packages/provider-*` 接你已有账户
2. **HypiHub 托管** —— `hypit auth login hypihub.default`，一个账户覆盖图像/视频/语音/转写
3. **本地部署** —— 自己的推理服务 + 写一个兼容 Provider

费用要先问清楚：

```bash
hypit pricing runs/final.svrun
```

## 八、更多文档

本地文档（中文）在仓库里：

```bash
open ~/Desktop/videoHub/repos/hypit/docs/zh/quickstart.md
open ~/Desktop/videoHub/repos/hypit/docs/zh/guide/runtime.md
open ~/Desktop/videoHub/repos/hypit/examples/README.md
```

官方文档站：<https://hypit.ai/zh/quickstart/>
