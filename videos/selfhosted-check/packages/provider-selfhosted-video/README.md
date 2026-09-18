# `@local/provider-selfhosted-video`

把跑在你自己服务器上的视频推理服务接进 Hypit。复用官方 Seedance 的 capability，
所以 **SVML 源码一行不用改** —— 切换发生在 Profile 的 `bindings` 层。

**状态：已实测可用。** `tsc` 零报错；装进项目后 `hypit doctor` 返回 0 diagnostics；
两个反例（内网明文 HTTP、binding 指向不存在的 Endpoint）都被准确拦下，
错误消息即来自本包的 `activation.ts` —— 证明 Runtime 真的加载并执行了它。

```
[你的 Mac: Hypit Runtime + 本 Provider]  --HTTP-->  [你的服务器: 推理服务 / ComfyUI / GPU]
```

## 它假设的服务形状

最常见的「任务式 HTTP API」。协议不匹配时改这三个方法即可：

| Hypit 生命周期 | 本骨架假设的接口 |
| --- | --- |
| `start` | `POST /upload` → `{ url }`（上传参考素材）<br>`POST /tasks` → `{ id }` |
| `poll` | `GET /tasks/{id}` → `{ state }`，取值 `queued` / `running` / `in_progress` / `succeeded` / `completed` / `failed` |
| `collect` | `GET /tasks/{id}/files` → `{ items: [{ url }] }`，再下载视频字节 |

## 四处要改

**1 · 顶替哪个 capability** — `src/provider.ts` 顶部

```ts
export const capability = { module: { name: "@hypit/seedance", version: "1" }, name: "seedance-2-mini" } as const;
```

| SVML 写法 | capability 全名 | 分辨率 | 时长 |
| --- | --- | --- | --- |
| `model="standard"` | `@hypit/seedance@1#seedance-2` | 1080p / 4k | 4–15s |
| `model="fast"` | `@hypit/seedance@1#seedance-2-fast` | 480p / 720p | 4–15s |
| `model="mini"` | `@hypit/seedance@1#seedance-2-mini` | 480p / 720p | 4–15s |
| `model="2.5"` | `@hypit/seedance@1#seedance-2.5` | 480p / 720p / 1080p | -1 或 4–30s |

Profile 的 `bindings` 里必须用同一个全名。

**2 · 端口映射表** — `mapping.fields`，以及 `routes[0].model`（你服务上的模型标识）

**只声明你的服务真正接受的端口。** 没声明的端口，请求一旦用到就在 `hypit plan` 阶段报错，
不会静默丢掉。无声模型（Wan 2.2 / HunyuanVideo）就不要声明
`referenceAudio` / `generateAudio` / `webSearch`。

**3 · 三个生命周期方法** — `start` / `poll` / `collect` 里标了 `★ 改这里` 的三处

**4 · Profile 配置**

```json
{
  "endpoints": {
    "selfhosted.video": {
      "use": "@local/provider-selfhosted-video",
      "config": {
        "baseUrl": "http://127.0.0.1:8188",
        "pollIntervalMs": 5000,
        "requestTimeoutMs": 120000,
        "concurrency": 1
      }
    }
  },
  "bindings": {
    "@hypit/seedance@1#seedance-2-mini": "selfhosted.video"
  }
}
```

`apiToken` 可选 —— 服务不需要鉴权就别配。配了的话走 os 凭据库：

```json
"config": {
  "baseUrl": "https://video.myserver.com",
  "apiToken": { "store": "os", "key": "selfhosted.video" }
}
```

## 构建与安装

```bash
cd packages/provider-selfhosted-video
npm install
npm run build
cd ../..
npm install ./packages/provider-selfhosted-video
hypit doctor --color never
```

## 为什么 `node dist/provider.js` 会报错 —— 这是正常的

`@hypit/hypit` 的 subpath exports 长这样：

```json
"./endpoint-kit": {
  "types":  "./dist/public/endpoint-kit.d.ts",
  "import": "./packages/endpoint-kit/src/index.ts"
}
```

`import` 指向的是 **TypeScript 源文件**。所以：

- `tsc` **类型检查完全正常** —— `types` 指向 `.d.ts`，这是编译能过的原因
- 用普通 `node` 直接 import 编译产物会报 `Stripping types is currently unsupported for files under node_modules`

**这不是包有问题。** Provider 从来不由普通 node 直接运行 —— 它由 Hypit Runtime 加载，
Runtime 有自己的模块解析器，能处理这个 TS 入口。判断包是否可用，看 `hypit doctor` 的输出，
不要看裸 node import 的结果。

## 硬约束

- **地址必须 HTTPS 或回环。** `http://192.168.1.x:8000` 会被拒绝。内网服务用 SSH 隧道：
  ```bash
  ssh -N -L 8188:127.0.0.1:8188 user@your-server
  ```
  然后 `baseUrl` 写 `http://127.0.0.1:8188`。

- **并发默认 1。** 单卡串行就别调高。`actionLimits` 把 submit / poll / collect 分开限流。

- **超时是分钟级的。** 视频生成慢，别用默认值硬扛。

## ComfyUI 适配提示

ComfyUI 的接口形状天然就是 start / poll / collect，且默认监听 `127.0.0.1:8188`（满足回环约束）：

| 本骨架 | ComfyUI |
| --- | --- |
| `POST /tasks` | `POST /prompt`，body `{ prompt: <API格式工作流>, client_id }` → `{ prompt_id }` |
| `GET /tasks/{id}` | `GET /history/{prompt_id}` — 空对象 `{}` 表示还在跑，非空且 `status.completed` 表示完成 |
| `GET /tasks/{id}/files` | `GET /view?filename=&subfolder=&type=output` |
| `POST /upload` | `POST /upload/image`（multipart）→ `{ name, subfolder, type }` |

**工作流必须导出为 API 格式**（Settings → Enable Dev Mode options → Save (API Format)）。
UI 里保存的普通 JSON 不能直接提交 —— 这是最常见的失败原因。

视频产物所在的字段取决于节点：VHS 系节点通常输出在 `outputs` 的 `gifs`，
其他节点可能是 `images`。以你实际工作流为准。

## 官方参考

- 完整项目 Provider 示例：`repos/hypit/examples/provider-package/`
- 文档：`repos/hypit/docs/zh/guide/providers.md`、`service-partners.md`
- SDK：`@hypit/hypit/endpoint-kit`、`@hypit/hypit/generation`、`@hypit/hypit/runtime-kit`
