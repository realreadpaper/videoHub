#!/usr/bin/env python3
"""阿里云百炼语音识别流水线：本地音频 -> 上传百炼 OSS -> paraformer-v2 文件转写 -> 词/句级时间戳 -> SRT。

用法:
  uv run --with requests python asr_pipeline.py submit <audio.mp3> --name <标签> --outdir <目录>
  uv run --with requests python asr_pipeline.py poll   --name <标签> --outdir <目录> --task-id <id>
  uv run --with requests python asr_pipeline.py run    <audio.mp3> --name <标签> --outdir <目录>

产出（outdir 下）:
  <标签>/asr_raw.json         接口原始结果（含句级/词级时间戳）
  <标签>/transcript.txt       纯文本
  <标签>/<标签>.srt           字幕文件
  <标签>/asr_task.json        任务状态记录
"""
import argparse
import json
import os
import sys
import time

import requests

KEY_PATH = os.path.expanduser("~/.workbuddy/secrets/dashscope.key")
UPLOAD_URL = "https://dashscope.aliyuncs.com/api/v1/uploads"
ASR_URL = "https://dashscope.aliyuncs.com/api/v1/services/audio/asr/transcription"
TASK_URL = "https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
MODEL = "paraformer-v2"


def api_key() -> str:
    return open(KEY_PATH).read().strip()


def auth_header() -> dict:
    return {"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"}


def get_policy() -> dict:
    """上传凭证。查询参数必须小写，大写会 InvalidParameter。"""
    r = requests.get(
        UPLOAD_URL,
        params={"action": "getPolicy", "model": MODEL},
        headers={"Authorization": f"Bearer {api_key()}"},
        timeout=30,
    )
    r.raise_for_status()
    body = r.json()
    if "data" not in body:
        raise RuntimeError(f"获取凭证失败: {json.dumps(body, ensure_ascii=False)[:400]}")
    return body["data"]


def upload_file(path: str, policy: dict) -> str:
    key = f"{policy['upload_dir']}/{os.path.basename(path)}"
    with open(path, "rb") as f:
        r = requests.post(
            policy["upload_host"],
            files={
                "key": (None, key),
                "policy": (None, policy["policy"]),
                "OSSAccessKeyId": (None, policy["oss_access_key_id"]),
                "signature": (None, policy["signature"]),
                "x-oss-object-acl": (None, policy["x_oss_object_acl"]),
                "x-oss-forbid-overwrite": (None, policy["x_oss_forbid_overwrite"]),
                "success_action_status": (None, "200"),
                "file": (os.path.basename(path), f, "audio/mpeg"),
            },
            timeout=900,
        )
    if r.status_code != 200:
        raise RuntimeError(f"上传失败 HTTP {r.status_code}: {r.text[:400]}")
    # 百炼的桶非公共读，必须用 oss:// 前缀交给服务端内部解析；
    # 直接给 https://dashscope-file-mgr... 会报 FILE_403_FORBIDDEN。
    return f"oss://{key}"


def submit(file_url: str) -> str:
    r = requests.post(
        ASR_URL,
        headers={**auth_header(), "X-DashScope-Async": "enable",
                 "X-DashScope-OssResourceResolve": "enable"},
        json={
            "model": MODEL,
            "input": {"file_urls": [file_url]},
            "parameters": {"language_hints": ["zh"], "channel_id": [0]},
        },
        timeout=120,
    )
    body = r.json()
    if r.status_code != 200 or "output" not in body:
        raise RuntimeError(f"提交失败 HTTP {r.status_code}: {json.dumps(body, ensure_ascii=False)[:400]}")
    return body["output"]["task_id"]


def poll(task_id: str, interval: int = 10, timeout_s: int = 1800) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        r = requests.get(TASK_URL.format(task_id=task_id), headers=auth_header(), timeout=60)
        body = r.json()
        status = body.get("output", {}).get("task_status")
        if status in ("SUCCEEDED", "FAILED"):
            return body
        print(f"  [{int(time.time() % 1000):03d}] 状态 {status}，等待 {interval}s…", flush=True)
        time.sleep(interval)
    raise TimeoutError(f"任务 {task_id} 轮询超时")


def ms_to_srt_time(ms: int) -> str:
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, msec = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{msec:03d}"


def write_srt(sentences: list, out_path: str) -> int:
    """按句级时间戳出 SRT；相邻过短句合并到 1 秒以上，避免闪现。"""
    cues = []
    for s in sentences:
        text = (s.get("text") or "").strip()
        if not text:
            continue
        cues.append({"start": s.get("begin_time", 0), "end": s.get("end_time", 0), "text": text})
    # 合并过短片段
    merged = []
    for c in cues:
        if merged and (c["end"] - c["start"] < 800 or (c["start"] - merged[-1]["end"] < 120 and len(merged[-1]["text"]) < 12)):
            merged[-1]["text"] += c["text"]
            merged[-1]["end"] = c["end"]
        else:
            merged.append(dict(c))
    with open(out_path, "w", encoding="utf-8") as f:
        for i, c in enumerate(merged, 1):
            f.write(f"{i}\n{ms_to_srt_time(c['start'])} --> {ms_to_srt_time(c['end'])}\n{c['text']}\n\n")
    return len(merged)


def save_result(raw: dict, outdir: str, name: str) -> dict:
    os.makedirs(outdir, exist_ok=True)
    results = raw.get("output", {}).get("results", [])
    summary = {"task_id": raw.get("output", {}).get("task_id"), "files": []}
    for res in results:
        turl = res.get("transcription_url")
        if not turl:
            summary["files"].append({"error": res.get("message") or res.get("code")})
            continue
        t = requests.get(turl, timeout=120).json()
        json.dump(t, open(os.path.join(outdir, "asr_raw.json"), "w"), ensure_ascii=False, indent=2)
        sentences = (t.get("transcripts") or [{}])[0].get("sentences", [])
        text = (t.get("transcripts") or [{}])[0].get("text", "")
        open(os.path.join(outdir, "transcript.txt"), "w", encoding="utf-8").write(text)
        n = write_srt(sentences, os.path.join(outdir, f"{name}.srt"))
        words = sum(len(s.get("words") or []) for s in sentences)
        summary["files"].append({
            "sentences": len(sentences), "words": words, "srt_cues": n,
            "duration_ms": (t.get("transcripts") or [{}])[0].get("properties", {}).get("original_duration_in_milliseconds"),
            "text_len": len(text),
        })
    json.dump(summary, open(os.path.join(outdir, "asr_summary.json"), "w"), ensure_ascii=False, indent=2)
    return summary


def cmd_submit(args) -> None:
    os.makedirs(args.outdir, exist_ok=True)
    policy = get_policy()
    print(f"上传 {args.audio} …", flush=True)
    url = upload_file(args.audio, policy)
    print(f"  已上传: {url[:110]}…", flush=True)
    task_id = submit(url)
    print(f"  任务已提交: {task_id}", flush=True)
    json.dump({"task_id": task_id, "audio": args.audio, "file_url": url, "name": args.name},
              open(os.path.join(args.outdir, "asr_task.json"), "w"), ensure_ascii=False, indent=2)


def cmd_poll(args) -> None:
    task_id = getattr(args, "task_id", None)
    if not task_id:
        task_id = json.load(open(os.path.join(args.outdir, "asr_task.json")))["task_id"]
    print(f"轮询任务 {task_id} …", flush=True)
    raw = poll(task_id)
    json.dump(raw, open(os.path.join(args.outdir, "asr_response.json"), "w"), ensure_ascii=False, indent=2)
    s = save_result(raw, args.outdir, args.name)
    print(json.dumps(s, ensure_ascii=False, indent=2))


def cmd_run(args) -> None:
    cmd_submit(args)
    cmd_poll(args)


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("submit", "run"):
        sp = sub.add_parser(name)
        sp.add_argument("audio")
        sp.add_argument("--name", required=True)
        sp.add_argument("--outdir", required=True)
        sp.set_defaults(func=cmd_submit if name == "submit" else cmd_run)
    sp = sub.add_parser("poll")
    sp.add_argument("--name", required=True)
    sp.add_argument("--outdir", required=True)
    sp.add_argument("--task-id")
    sp.set_defaults(func=cmd_poll)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
