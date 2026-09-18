/**
 * 自部署视频模型 → Hypit 项目 Provider
 * ====================================
 *
 * 把「跑在你自己服务器上的视频推理服务」接进 Hypit 的 Model–Provider–Endpoint 体系。
 *
 * 复用官方 Seedance 的 capability，所以 **SVML 源码一行都不用改**：
 *
 *     <seedance:TextVideo id="take" model="mini" prompt={p} duration="5"/>
 *
 * 作者写的是 seedance:TextVideo，实际请求打到你自己的服务上。切换发生在 Profile 层，
 * 靠 bindings 把 `@hypit/seedance@1#seedance-2-mini` 从这个 Endpoint 兑现。
 *
 * ─────────────────────────────────────────────────────────────────────
 * 本文件默认按 **FastVideo 的 OpenAI 兼容 server** 实现（`fastvideo serve`）。
 * 它暴露的接口形状（以仓库源码为准）：
 *
 *     GET  /v1/models/{model}              模型目录
 *     POST /v1/videos                      提交异步任务 → { id, status, ... }
 *     GET  /v1/videos/{video_id}           轮询 → { status: queued|in_progress|completed|failed }
 *     GET  /v1/videos/{video_id}/content   下载 mp4 字节
 *     POST /v1/videos/sync                 同步生成，直接返回 mp4
 *
 * 换成别的服务（ComfyUI、自写 FastAPI、任务队列）时，只需改三个地方 ——
 * 都在文件里用 `★ 服务适配点` 标出来了。
 * ─────────────────────────────────────────────────────────────────────
 *
 * 生命周期映射：
 *
 *     start   → POST {baseUrl}/v1/videos
 *     poll    → GET  {baseUrl}/v1/videos/{id}
 *     collect → GET  {baseUrl}/v1/videos/{id}/content
 */

import { canonicalize, defineEndpointPackage, wakeAfter } from "@hypit/hypit/endpoint-kit";
import type {
  AsyncEndpoint, CredentialRef, EndpointCredential, EndpointRequest, EndpointSupport,
} from "@hypit/hypit/endpoint-kit";
import {
  compileWireRequest, generationTypes, sealGeneratedVideoSet, selectWireModelForRequest,
} from "@hypit/hypit/generation";
import type { GenerationRequest, GenerationWireMapping } from "@hypit/hypit/generation";

/** ★ 改这里：包名，必须与 package.json 的 name 一致 */
export const providerModule = { name: "@local/provider-selfhosted-video", version: "1" } as const;

/**
 * ★ 改这里：你要顶替哪个 capability。Profile 的 bindings 里要用同一个全名。
 *
 *   SVML 写法                capability 全名
 *   model="standard"  →  @hypit/seedance@1#seedance-2        1080p / 4k，4–15s
 *   model="fast"      →  @hypit/seedance@1#seedance-2-fast   480p / 720p，4–15s
 *   model="mini"      →  @hypit/seedance@1#seedance-2-mini   480p / 720p，4–15s
 *   model="2.5"       →  @hypit/seedance@1#seedance-2.5      480p/720p/1080p，-1 或 4–30s
 */
export const capability = { module: { name: "@hypit/seedance", version: "1" }, name: "seedance-2-mini" } as const;

/**
 * ★ 改这里：端口 → 你服务 wire 字段 的翻译表。
 *
 * 关键规则：**只声明你的服务真正接受的端口**。
 * 没声明的端口，supports() 会在 `hypit plan` 阶段就明确报错，
 * 而不是静默丢弃 —— 这是这套体系最值得信任的一点。
 *
 *   as: "value"      标量原样发出
 *   as: "string"     标量转字符串
 *   as: "valueArray" 多个标量组成数组
 *   as: "url"        单个媒体解析成 URL
 *   as: "urlArray"   多个媒体解析成 URL 数组
 *   as: "itemObject" 媒体写成对象（urlKey 指定 URL 字段名）
 */
const mapping: GenerationWireMapping = {
  capability,
  result: "video",
  /** ★ 你服务上的模型标识，会作为请求体的 `model` 字段发出 */
  routes: [{ model: "FastVideo" }],
  fields: {
    prompt: { as: "value", field: "prompt" },
    duration: { as: "value", field: "seconds" },
    aspectRatio: { as: "value", field: "aspect_ratio" },
    // FastVideo 的 image_reference 是 [{ image_url }] 形状
    referenceImage: { as: "itemObject", field: "image_reference", urlKey: "image_url", fieldKeys: {} },

    // ── 按你的模型能力决定是否打开 ──────────────────────────────────
    // `generate_sound` 是 FastVideo 的音频开关。只有模型本身支持同步音频
    // （如 H3 系列）时才声明这一行；否则作者写了 generate-audio="true"
    // 会打到一个不认这个字段的服务上，不如让 supports() 提前拦下。
    //
    // generateAudio: { as: "value", field: "generate_sound" },
    //
    // firstFrame / lastFrame 需要服务能取到图片 URL；FastVideo 的引用走
    // image_reference 对象，首尾帧支持取决于所选模型。
    // firstFrame: { as: "url", field: "input_reference" },
  },
};

/** 本 Endpoint 声明支持的端口集合；supports() 与请求改写共用 */
const declaredPorts = new Set(Object.keys(mapping.fields));

/**
 * Seedance 说 `720p`，FastVideo 说 `1280x720`。
 * 这里做一次换算 —— 这是 Provider 的正当职责：「知道如何通过某个服务完成这个请求」。
 */
const SIZES: Readonly<Record<string, Readonly<Record<string, string>>>> = {
  "480p": { "16:9": "854x480", "9:16": "480x854", "1:1": "480x480", "4:3": "640x480", "3:4": "480x640" },
  "720p": { "16:9": "1280x720", "9:16": "720x1280", "1:1": "720x720", "4:3": "960x720", "3:4": "720x960" },
  "1080p": { "16:9": "1920x1080", "9:16": "1080x1920", "1:1": "1080x1080", "4:3": "1440x1080", "3:4": "1080x1440" },
};

/** 从凭据槽取 Bearer Token；服务不需要鉴权时返回空头，不报错。 */
function authHeaders(credentials: Readonly<Record<string, EndpointCredential>>): Record<string, string> {
  const secret = credentials.apiToken?.secret;
  return typeof secret === "string" && secret.length > 0 ? { authorization: `Bearer ${secret}` } : {};
}

function object(value: unknown, subject: string): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) throw new Error(`${subject} 必须是对象`);
  return value as Record<string, unknown>;
}

function text(value: unknown, subject: string): string {
  if (typeof value !== "string" || value.length === 0) throw new Error(`${subject} 必须是非空字符串`);
  return value;
}

/** 只接受 HTTPS 或本机回环 HTTP —— 与官方 Provider 保持同一策略。 */
function address(value: string): string {
  const url = new URL(value);
  const loopback = url.hostname === "localhost" || url.hostname === "127.0.0.1";
  if (url.protocol !== "https:" && !(url.protocol === "http:" && loopback)) {
    throw new Error("服务地址必须是 HTTPS，或 http://localhost / http://127.0.0.1");
  }
  return url.href;
}

/**
 * 支持性判定：请求里的每个端口都必须在本 Provider 的 mapping 里声明过。
 *
 * 这段是「诚实边界」的落点 —— 它保证不支持的请求在计划阶段就被拦下，
 * 而不是发到你服务上以后静默降级、或者烧了算力才发现端口被忽略。
 */
function support(request: EndpointRequest): EndpointSupport {
  const ports = (request.constraints as unknown as GenerationRequest | undefined)?.ports ?? {};
  const rejected = Object.keys(ports).find((port) => !declaredPorts.has(port));
  if (rejected !== undefined) {
    return {
      status: "unsupported",
      reason: `自部署视频服务没有 ${rejected} 端口；本 Endpoint 只实现 ${[...declaredPorts].sort().join(", ")}`,
    };
  }
  const pending = request.pendingInputs?.find((slot) => !declaredPorts.has(slot.input));
  if (pending !== undefined) {
    return {
      status: "unsupported",
      reason: `自部署视频服务没有 ${pending.input} 端口（上游图喂进来的输入无法映射）`,
    };
  }
  return { status: "supported" };
}

export function createSelfHostedVideoProvider(options: {
  readonly instance: string;
  readonly pool: string;
  readonly baseUrl: string;
  /** 可选：服务需要鉴权时才在 Profile 里配 apiToken */
  readonly apiToken?: CredentialRef;
  readonly concurrency?: number;
  readonly pollIntervalMs?: number;
  readonly requestTimeoutMs?: number;
  readonly fetch?: typeof globalThis.fetch;
}) {
  const base = address(options.baseUrl).replace(/\/$/u, "");
  const fetcher = options.fetch ?? globalThis.fetch;
  const interval = options.pollIntervalMs ?? 5_000;
  const timeout = options.requestTimeoutMs ?? 120_000;

  async function json(path: string, credentials: Readonly<Record<string, EndpointCredential>>, init: RequestInit = {}) {
    const response = await fetcher(`${base}${path}`, {
      ...init,
      headers: { ...init.headers, ...authHeaders(credentials) },
      signal: AbortSignal.timeout(timeout),
    });
    if (!response.ok) {
      let detail = "";
      try {
        const body = await response.json() as { detail?: unknown };
        if (typeof body.detail === "string") detail = `；${body.detail}`;
      } catch { /* 非 JSON 响应就保留 HTTP 证据 */ }
      throw new Error(`自部署视频服务 ${init.method ?? "GET"} ${path} 返回 HTTP ${response.status}${detail}`);
    }
    return object(await response.json(), "服务响应");
  }

  /** 把 Seedance 的 resolution + aspectRatio 折成 FastVideo 的 size */
  function applySize(input: Record<string, unknown>): void {
    const resolution = typeof input.resolution === "string" ? input.resolution : "720p";
    const ratio = typeof input.aspect_ratio === "string" ? input.aspect_ratio : "16:9";
    delete input.resolution;
    const size = SIZES[resolution]?.[ratio];
    if (size !== undefined) input.size = size;
  }

  const endpoint: AsyncEndpoint = {
    async start(context) {
      const supported = support(context.need);
      if (supported.status === "unsupported") throw new Error(supported.reason);

      const authored = context.need.constraints as unknown as GenerationRequest;
      const model = selectWireModelForRequest(mapping, authored);
      await context.reportProgress?.({ phase: `准备视频请求：${model}` });

      // 参考素材：先让它变成你服务能取到的 URL，再进请求体。
      const request = await compileWireRequest(mapping, authored, async (artifact) => {
        const bytes = await context.resources.get(artifact.resource);
        if (bytes === undefined) throw new Error("参考素材不可用");
        // ★ 服务适配点 1：素材托管。FastVideo 的 image_reference 只接受 URL，
        //   所以这里需要把字节放到你服务器能拉取的位置。三种常见做法：
        //     a) 同机部署：起一个静态文件服务，把字节写进去后返回其 URL
        //     b) 对象存储：上传到 OSS/S3/MinIO，返回带签名的 URL
        //     c) 服务支持 file_id：先 POST /v1/files 拿 id，返回 { image_url: "file://id" }
        //   纯文生视频（seedance:TextVideo）不会走到这里。
        throw new Error(
          "本 Provider 尚未配置参考素材托管：请实现 start() 里的 ★服务适配点 1，"
          + "或改用 text-to-video（不带参考图 / 首尾帧）。",
        );
      });

      const input = { ...(request.input as Record<string, unknown>) };
      applySize(input);

      await context.reportProgress?.({ phase: `提交视频请求：${model}` });
      // ★ 服务适配点 2：任务提交。FastVideo：POST /v1/videos → { id, status }
      const task = await json("/v1/videos", context.credentials, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ ...input, model }),
      });

      const id = text(task.id, "任务 id");
      const handle = { id };
      // 先登记回执，再返回 pending —— 远程真失败了也有据可查。
      await context.checkpoint?.({ handle, receipt: { id } });
      return { ...wakeAfter(handle, interval), receipt: { id } };
    },

    async poll(context) {
      const id = text(object(context.handle, "任务句柄").id, "任务 id");
      // ★ 服务适配点 3：状态查询。FastVideo：GET /v1/videos/{id} → { status }
      const task = await json(`/v1/videos/${encodeURIComponent(id)}`, context.credentials);
      const state = String(task.status ?? "");

      if (state === "queued" || state === "in_progress" || state === "running") {
        const phase = typeof task.progress === "number" ? `${state}（${task.progress}%）` : state;
        return wakeAfter({ id }, interval, Date.now(), { phase });
      }
      if (state === "failed") {
        const raw = task.error;
        const message = raw !== null && typeof raw === "object" && typeof (raw as Record<string, unknown>).message === "string"
          ? String((raw as Record<string, unknown>).message)
          : "服务未给出原因";
        return {
          status: "failed",
          receipt: { id },
          failure: { code: "SELFHOSTED_VIDEO_FAILED", message: `自部署视频任务 ${id} 失败：${message}` },
        };
      }
      if (state !== "completed" && state !== "succeeded") {
        throw new Error(`自部署视频服务返回了未知状态：${state || "(空)"}`);
      }
      return { status: "ready", handle: { id } };
    },

    async collect(context) {
      const id = text(object(context.handle, "任务句柄").id, "任务 id");
      await context.reportProgress?.({ phase: "接收生成视频" });

      // ★ 服务适配点 3（续）：产物下载。FastVideo：GET /v1/videos/{id}/content
      const response = await fetcher(`${base}/v1/videos/${encodeURIComponent(id)}/content`, {
        headers: authHeaders(context.credentials),
        signal: AbortSignal.timeout(timeout),
      });
      if (!response.ok) throw new Error(`产物下载返回 HTTP ${response.status}`);
      const mediaType = response.headers.get("content-type")?.split(";")[0]?.trim() ?? "video/mp4";
      if (!mediaType.startsWith("video/")) throw new Error("服务返回的不是视频产物");

      const artifact = await context.resources.put(new Uint8Array(await response.arrayBuffer()), mediaType);
      return {
        status: "completed",
        result: { value: { kind: "inline", value: canonicalize(sealGeneratedVideoSet({ videos: [artifact] })) } },
      };
    },
  };

  return defineEndpointPackage({
    module: providerModule,
    facet: "videos",
    instance: options.instance,
    pool: options.pool,
    // 服务不需要鉴权时就不声明凭据槽，Profile 里也不用配 apiToken。
    ...(options.apiToken === undefined ? {} : {
      credentials: { apiToken: options.apiToken },
      credentialInputs: { apiToken: { label: "自部署视频服务 Token（可选）" } },
    }),
    defaultConcurrency: options.concurrency ?? 1,
    actionLimits: { submit: { concurrency: 1 }, poll: { concurrency: 4 }, collect: { concurrency: 1 } },
    // 自有算力执行：Provider 侧零调用费用（算力成本属于你自己的机器）
    pricing: { kind: "local" },
    capabilities: [{
      capability,
      returns: generationTypes.videoSet,
      lifecycle: "asynchronous",
      supports: support,
      endpoint,
    }],
  });
}
