#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""submit_api.py — 直接提交「已是 API 格式」的工作流到 ComfyUI，并轮询到结束。

与 ui_to_api.py 的分工：
  ui_to_api.py   : UI 格式(前端导出) → API 格式 → 提交
  submit_api.py  : API 格式 → 提交（本文件，用于程序化生成的批次工作流）

用法：
  python3 submit_api.py api.json                    # 提交并轮询
  python3 submit_api.py api.json --json-out r.json  # 把 history 结果落盘
  python3 submit_api.py api.json --host http://127.0.0.1:8188
退出码：0 成功 / 2 执行失败 / 3 网络或提交被拒
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid


def post(url, payload, timeout=60):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def get(url, timeout=60):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("api_json")
    ap.add_argument("--host", default="http://127.0.0.1:8188")
    ap.add_argument("--timeout", type=int, default=7200)
    ap.add_argument("--poll", type=int, default=10)
    ap.add_argument("--json-out")
    a = ap.parse_args()

    raw = json.load(open(a.api_json))
    # 顶层只允许节点对象（必须带 class_type）。混进 "_meta"/注释键会让
    # /prompt 直接 400 missing_node_type，这里主动剥离并告警。
    wf = {}
    for k, v in raw.items():
        if isinstance(v, dict) and v.get("class_type"):
            wf[k] = v
        else:
            print("[!] 跳过非节点顶层键: %r" % (k,), file=sys.stderr)
    if not wf:
        print("[✗] 工作流为空", file=sys.stderr)
        return 3
    client = str(uuid.uuid4())
    try:
        res = post(a.host + "/prompt", {"prompt": wf, "client_id": client})
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        print("[✗] 提交被拒 HTTP %s\n%s" % (e.code, body[:2000]), file=sys.stderr)
        return 3
    except Exception as e:  # noqa: BLE001
        print("[✗] 提交异常: %r" % (e,), file=sys.stderr)
        return 3

    pid = res.get("prompt_id")
    print("[i] prompt_id =", pid)
    t0 = time.time()
    last = None
    while True:
        el = time.time() - t0
        if el > a.timeout:
            print("[✗] 超时 %ss" % a.timeout, file=sys.stderr)
            return 2
        try:
            h = get(a.host + "/history/" + pid)
        except Exception:  # noqa: BLE001
            h = {}
        if pid in h:
            e = h[pid]
            st = e.get("status", {}) or {}
            ok = st.get("completed") and st.get("status_str") == "success"
            print("[%s] 用时 %.1f s  status=%s completed=%s"
                  % ("✓" if ok else "✗", el, st.get("status_str"), st.get("completed")))
            for msg in (st.get("messages") or []):
                if msg[0] in ("execution_error", "execution_interrupted"):
                    print("   !! %s" % (json.dumps(msg[1], ensure_ascii=False)[:600],))
            for nid, out in (e.get("outputs") or {}).items():
                compact = {k: v for k, v in out.items() if k != "text"}
                if compact:
                    print("   节点#%s → %s" % (nid, json.dumps(compact, ensure_ascii=False)[:300]))
            if a.json_out:
                with open(a.json_out, "w", encoding="utf-8") as f:
                    json.dump(e, f, ensure_ascii=False, indent=1)
            return 0 if ok else 2
        # 队列/进度提示
        try:
            q = get(a.host + "/queue")
            n = len(q.get("queue_pending", []) or [])
            r = len(q.get("queue_running", []) or [])
            msg = "  排队 %d / 运行 %d  %.0fs" % (n, r, el)
        except Exception:  # noqa: BLE001
            msg = "  %.0fs" % el
        if msg != last:
            print(msg)
            last = msg
        time.sleep(a.poll)


if __name__ == "__main__":
    sys.exit(main())
