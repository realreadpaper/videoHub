/**
 * 项目 Provider 的激活入口。
 *
 * 这个文件负责把 Profile 里的 `config` 读出来、校验、然后交给 provider.ts 建实例。
 * Hypit 通过 package.json 的 `hypit.activation` 字段找到它 —— 所以这个包被安装后
 * 并不会自动生效，只有选中的 Profile 里配了对应 endpoint 才会激活。
 *
 * 字段名必须与 runtimeConfigExact 的清单严格一致，多一个少一个都会启动失败。
 */
declare const _default: {
    format: "hypit.node-package@1";
    hostFacets: import("@hypit/hypit/runtime-kit").RuntimeAdapterHostFacet[];
};
export default _default;
