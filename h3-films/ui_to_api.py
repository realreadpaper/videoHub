#!/usr/bin/env python3
"""ui_to_api.py — 把 ComfyUI UI 格式工作流转成 API 格式并提交，轮询到结束。

为什么需要它：本机的 runner（80_run_workflow_remote.py）没随资产上传，
而 ComfyUI 前端那套 UI→API 转换只存在于浏览器端。这里用 /object_info 的
schema 重建同一套映射逻辑。

用法：
  python ui_to_api.py <ui.json> --out api.json            # 只转换，打印映射表
  python ui_to_api.py <ui.json> --submit --timeout 1800   # 转换 + 提交 + 轮询
  python ui_to_api.py <ui.json> --submit --prefix MiniMaxH3/a100-verify/verify
选项：
  --host http://127.0.0.1:8188
  --drop MarkdownNote                    # 纯 UI 节点，直接丢弃（可多次）
  --replace-missing VHS_VideoCombine     # 缺失节点的替代：转成 MiniMaxH3SafeAVSaveT8Advanced
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request

PRIMITIVES = {"INT", "FLOAT", "STRING", "BOOLEAN"}
CONNECTION_TYPES = {
    "MODEL", "CLIP", "VAE", "CONDITIONING", "LATENT", "IMAGE", "MASK", "AUDIO",
    "SAMPLER", "SIGMAS", "NOISE", "GUIDER", "VIDEO", "UPSCALE_MODEL", "CONTROL_NET",
    "STYLE_MODEL", "CLIP_VISION", "CLIP_VISION_OUTPUT", "GLIGEN", "HOOKS", "WEBCAM",
    "VHS_BatchManager", "VHS_FILENAMES",
}
SEED_CONTROLS = {"fixed", "increment", "decrement", "randomize"}
# 前端会为这些 widget 额外插一个“生成控制”下拉，占 widgets_values 一格
SEED_NAMES = {"seed", "noise_seed", "rand_seed"}


def http_json(url, payload=None, timeout=120):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def schema_of(oi, node_type):
    ent = oi.get(node_type)
    if not ent:
        return None, None
    inp = ent.get("input", {})
    out = ent.get("output")
    return inp, out


def is_widget_type(ty):
    """判断一个 schema 输入类型是否会渲染成 widget。

    ★ 坑：本节点包里大量 COMBO 型输入的 type 是**字符串 "COMBO"** 而不是候选列表
    （task_type / audio_mode / ref_image_size / reference_video_policy / LoadAudio.audio …）。
    只按 `isinstance(ty, list)` 判断会把这些漏掉，导致提交时全部回落默认值 ——
    audio_mode 掉成默认就不是 lock_source 了，锁音轨直接失效。
    """
    if isinstance(ty, list):
        return True
    if not isinstance(ty, str):
        return False
    u = ty.upper()
    if u.startswith("COMFY_AUTOGROW"):
        return False
    if u in CONNECTION_TYPES:
        return False
    if u == "COMBO":
        return True
    return u in PRIMITIVES


def widget_names(schema):
    """按 required -> optional 顺序，列出会渲染成 widget 的输入名"""
    names = []
    if not schema:
        return names
    for sec in ("required", "optional"):
        for name, spec in (schema.get(sec) or {}).items():
            ty = spec[0] if isinstance(spec, list) and spec else spec
            opts = spec[1] if isinstance(spec, list) and len(spec) > 1 and isinstance(spec[1], dict) else {}
            if opts.get("forceInput"):
                continue
            if is_widget_type(ty):
                names.append(name)
    return names


def link_type_names(schema):
    names = []
    if not schema:
        return names
    for sec in ("required", "optional"):
        for name, spec in (schema.get(sec) or {}).items():
            ty = spec[0] if isinstance(spec, list) and spec else spec
            opts = spec[1] if isinstance(spec, list) and len(spec) > 1 and isinstance(spec[1], dict) else {}
            if opts.get("forceInput"):
                names.append(name)
                continue
            if isinstance(ty, str) and ty.upper() in CONNECTION_TYPES:
                names.append(name)
    return names


def autogrow_names(schema):
    """列出 COMFY_AUTOGROW_* 型输入。

    ★ 坑：这类槽（ref_images / ref_videos / ref_audios / ref_video_audios）在 API 格式里
    **不是单键**，必须展开成 `父名.子名_N`，例如：
        "ref_images.ref_image_0": ["17", 0]
    依据是节点包官方 fixture `hybrid_model_mixed_reference_api.json`（实测）。
    写成 `"ref_images": ["17", 0]` 时，节点内部 `sorted_autogrow_items()` 收到的是张量
    而非 Mapping，会抛：
        RuntimeError: Boolean value of Tensor with more than one value is ambiguous
    （它的 `sort_key` 要从键名尾部 `rsplit("_", 1)[-1]` 解析序号，故子名必须带 `_N`。）
    """
    names = []
    if not schema:
        return names
    for sec in ("required", "optional"):
        for name, spec in (schema.get(sec) or {}).items():
            ty = spec[0] if isinstance(spec, list) and spec else spec
            if isinstance(ty, str) and ty.upper().startswith("COMFY_AUTOGROW"):
                names.append(name)
    return names


def convert(ui, oi, drops, replace_missing, prefix=None, verbose=True):
    links = {l[0]: l for l in ui.get("links", [])}
    api = {}
    report = []

    def resolve(lid):
        l = links.get(lid)
        if not l:
            return None
        return [str(l[1]), l[2]]

    for node in ui["nodes"]:
        nid = str(node["id"])
        ntype = node.get("type")

        if node.get("mode") in (2, 4):        # muted / bypass
            report.append((nid, ntype, "跳过（muted/bypass）"))
            continue
        if ntype in drops:
            report.append((nid, ntype, "丢弃（UI 专用节点）"))
            continue

        schema, _ = schema_of(oi, ntype)
        src_type = ntype
        if schema is None:
            if ntype in replace_missing:
                src_type = "MiniMaxH3SafeAVSaveT8Advanced"
                schema, _ = schema_of(oi, src_type)
                report.append((nid, ntype, "缺失 → 替换为 %s" % src_type))
            else:
                report.append((nid, ntype, "!! 节点不存在，无法转换"))
                raise SystemExit("节点类型不存在: %s（用 --replace-missing 或 --drop 处理）" % ntype)

        ui_inputs = {i["name"]: i for i in (node.get("inputs") or [])}

        # 先只按连线建立输入（与 widget 无关）
        link_inputs = {}
        for name, i in ui_inputs.items():
            if i.get("link") is not None:
                r = resolve(i["link"])
                if r:
                    link_inputs[name] = r

        if src_type != ntype:
            # 替换节点：旧节点的 widgets_values 结构完全不同，绝不能继承；
            # 只保留同名连线输入，其余交给替代节点的默认值 + 显式覆盖
            inputs = dict(link_inputs)
            inputs["filename_prefix"] = prefix or "MiniMaxH3/a100-verify/verify"
            inputs["crf"] = 19
            api[nid] = {"class_type": src_type, "inputs": inputs}
            report.append((nid, src_type, "替换节点：连线 %d 项 + 覆盖 2 项"
                           % len(link_inputs)))
            continue

        wvals = node.get("widgets_values")
        if isinstance(wvals, dict):
            wvals = list(wvals.values())
        wvals = wvals or []
        wnames = widget_names(schema)

        inputs = {}
        wi = 0
        for name in wnames:
            has_slot = wi < len(wvals)
            val = wvals[wi] if has_slot else None
            if has_slot:
                wi += 1
            if name in link_inputs:
                inputs[name] = link_inputs[name]   # widget 被转成输入槽：用连线值覆盖
            elif has_slot:
                inputs[name] = val
            if name in SEED_NAMES and wi < len(wvals) and wvals[wi] in SEED_CONTROLS:
                wi += 1                            # 吞掉前端"生成控制"那一格

        for name, r in link_inputs.items():
            if name not in wnames:
                inputs[name] = r

        for name in list(inputs):
            if inputs[name] is None:
                del inputs[name]

        if prefix and "filename_prefix" in widget_names(schema):
            inputs["filename_prefix"] = prefix

        # ★ COMFY_AUTOGROW_* 槽必须展开成 `父名.子名_N`（详见 autogrow_names 文档串）
        ag = autogrow_names(schema)
        for name in [k for k in list(inputs) if k in ag]:
            val = inputs.pop(name)
            singular = name[:-1] if name.endswith("s") else name
            refs = val if (isinstance(val, list) and val and isinstance(val[0], list)) else [val]
            for idx, r in enumerate(refs):
                inputs["%s.%s_%d" % (name, singular, idx)] = r

        api[nid] = {"class_type": src_type, "inputs": inputs}
        report.append((nid, src_type, "widgets %d/%d → 输入 %d 项"
                       % (wi, len(wvals), len(inputs))))

    if verbose:
        print("--- 转换映射 ---")
        for nid, ntype, note in report:
            print("  [%s] %-38s %s" % (nid, ntype, note))
        print()
    return api


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workflow")
    ap.add_argument("--host", default="http://127.0.0.1:8188")
    ap.add_argument("--out")
    ap.add_argument("--submit", action="store_true")
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--prefix")
    ap.add_argument("--drop", action="append", default=["MarkdownNote", "Note"])
    ap.add_argument("--replace-missing", action="append",
                    default=["VHS_VideoCombine", "SaveVideo"])
    args = ap.parse_args()

    ui = json.load(open(args.workflow, encoding="utf-8"))
    oi = http_json(args.host + "/object_info", timeout=180)
    print("object_info 节点数: %d\n" % len(oi))

    api = convert(ui, oi, set(args.drop), set(args.replace_missing), args.prefix)

    out = args.out or (args.workflow.rsplit(".json", 1)[0] + ".api.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(api, fh, ensure_ascii=False, indent=1)
    print("已写出 API 工作流: %s（%d 个节点）" % (out, len(api)))

    if not args.submit:
        return 0

    print("\n--- 提交 ---")
    try:
        res = http_json(args.host + "/prompt", {"prompt": api, "client_id": "a100-verify"})
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print("!! 提交被拒 HTTP %s" % e.code)
        print(body[:4000])
        return 2

    pid = res.get("prompt_id")
    print("prompt_id = %s" % pid)

    t0 = time.time()
    last = None
    while time.time() - t0 < args.timeout:
        time.sleep(10)
        try:
            hist = http_json(args.host + "/history/" + pid, timeout=60)
        except Exception as e:
            print("  轮询异常: %s" % e)
            continue
        if pid not in hist:
            el = int(time.time() - t0)
            if el % 60 < 10:
                print("  [%4ds] 执行中..." % el)
            continue
        entry = hist[pid]
        status = entry.get("status", {})
        print("\n=== 结束，用时 %ds ===" % int(time.time() - t0))
        print("status_str = %s  completed = %s" % (status.get("status_str"), status.get("completed")))
        msgs = status.get("messages") or []
        for m in msgs:
            kind = m[0] if m else "?"
            if kind in ("execution_error", "execution_interrupted"):
                print("\n!! %s" % kind)
                print(json.dumps(m[1], ensure_ascii=False, indent=1)[:4000])
        outs = entry.get("outputs") or {}
        for nid, o in outs.items():
            if o.get("gifs") or o.get("images") or o.get("audio"):
                print("  输出节点 %s: %s" % (nid, json.dumps(o, ensure_ascii=False)[:300]))
        if status.get("completed"):
            print("\n✅ 执行完成")
            return 0
        print("\n❌ 未完成")
        return 1
    print("!! 超时 %ds" % args.timeout)
    return 3


if __name__ == "__main__":
    sys.exit(main())
