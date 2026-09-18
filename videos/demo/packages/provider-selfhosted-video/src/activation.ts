/**
 * 项目 Provider 的激活入口。
 *
 * 这个文件负责把 Profile 里的 `config` 读出来、校验、然后交给 provider.ts 建实例。
 * Hypit 通过 package.json 的 `hypit.activation` 字段找到它 —— 所以这个包被安装后
 * 并不会自动生效，只有选中的 Profile 里配了对应 endpoint 才会激活。
 *
 * 字段名必须与 runtimeConfigExact 的清单严格一致，多一个少一个都会启动失败。
 */

import {
  createRuntimeEndpointAdapterFacet,
  runtimeConfigCredentialRef,
  runtimeConfigExact,
  runtimeConfigObject,
  runtimeConfigPositiveInteger,
  runtimeConfigString,
} from "@hypit/hypit/runtime-kit";

import { createSelfHostedVideoProvider, providerModule } from "./provider.js";

export default {
  format: "hypit.node-package@1" as const,
  hostFacets: [createRuntimeEndpointAdapterFacet({
    use: providerModule.name,
    activate(context) {
      const config = runtimeConfigObject(context.config, "自部署视频服务");
      runtimeConfigExact(config, ["baseUrl", "apiToken", "concurrency", "pollIntervalMs", "requestTimeoutMs"], "自部署视频服务");

      const baseUrl = runtimeConfigString(config.baseUrl, "自部署视频服务 baseUrl");
      if (baseUrl === undefined) throw new Error("自部署视频服务必须配 baseUrl");

      // 与官方 Provider 同一策略：HTTPS 或本机回环，避免明文走公网或内网裸 HTTP。
      const url = new URL(baseUrl);
      const loopback = url.hostname === "localhost" || url.hostname === "127.0.0.1";
      if (url.protocol !== "https:" && !(url.protocol === "http:" && loopback)) {
        throw new Error("自部署视频服务 baseUrl 必须是 HTTPS，或 http://localhost / http://127.0.0.1");
      }

      const apiToken = runtimeConfigCredentialRef(config.apiToken, "自部署视频服务 apiToken");
      if (!context.pool) throw new Error("自部署视频服务需要 Provider Pool 身份");

      return {
        endpoint: createSelfHostedVideoProvider({
          instance: context.instance,
          pool: context.pool,
          baseUrl,
          ...(apiToken === undefined ? {} : { apiToken }),
          concurrency: runtimeConfigPositiveInteger(config.concurrency, "concurrency") ?? 1,
          pollIntervalMs: runtimeConfigPositiveInteger(config.pollIntervalMs, "pollIntervalMs") ?? 5_000,
          requestTimeoutMs: runtimeConfigPositiveInteger(config.requestTimeoutMs, "requestTimeoutMs") ?? 120_000,
        }),
      };
    },
  })],
};
