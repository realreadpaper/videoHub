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
import type { CredentialRef } from "@hypit/hypit/endpoint-kit";
/** ★ 改这里：包名，必须与 package.json 的 name 一致 */
export declare const providerModule: {
    readonly name: "@local/provider-selfhosted-video";
    readonly version: "1";
};
/**
 * ★ 改这里：你要顶替哪个 capability。Profile 的 bindings 里要用同一个全名。
 *
 *   SVML 写法                capability 全名
 *   model="standard"  →  @hypit/seedance@1#seedance-2        1080p / 4k，4–15s
 *   model="fast"      →  @hypit/seedance@1#seedance-2-fast   480p / 720p，4–15s
 *   model="mini"      →  @hypit/seedance@1#seedance-2-mini   480p / 720p，4–15s
 *   model="2.5"       →  @hypit/seedance@1#seedance-2.5      480p/720p/1080p，-1 或 4–30s
 */
export declare const capability: {
    readonly module: {
        readonly name: "@hypit/seedance";
        readonly version: "1";
    };
    readonly name: "seedance-2-mini";
};
export declare function createSelfHostedVideoProvider(options: {
    readonly instance: string;
    readonly pool: string;
    readonly baseUrl: string;
    /** 可选：服务需要鉴权时才在 Profile 里配 apiToken */
    readonly apiToken?: CredentialRef;
    readonly concurrency?: number;
    readonly pollIntervalMs?: number;
    readonly requestTimeoutMs?: number;
    readonly fetch?: typeof globalThis.fetch;
}): import("@hypit/hypit/endpoint-kit").EndpointPackage;
