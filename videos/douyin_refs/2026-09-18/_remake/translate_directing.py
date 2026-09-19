#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把导演台本的中文动作/镜头描述翻成英文（prompt 全英文，避免混语言降低遵从度）。
产出 directing_en.json：{中文: 英文}
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = open(os.path.expanduser("~/.workbuddy/secrets/dashscope.key")).read().strip()
API_KEY = RAW.split("=", 1)[1].strip() if "=" in RAW else RAW

import dashscope
from dashscope import Generation

SYS = (
    "You are a film director's assistant. Translate each Chinese shot description into ONE concise, "
    "concrete English instruction for a video-generation model. Rules:\n"
    "- Keep it a single sentence fragment, present tense, describing ONE visible physical action with a clear "
    "start and end (who moves what, where, with which prop).\n"
    "- Be specific about body parts, props and direction (e.g. 'presses a folded towel against the boy's "
    "forehead', not 'is caring').\n"
    "- For camera descriptions, translate as a short imperative camera instruction.\n"
    "- Never add timings, shot numbers or extra sentences. Never use the words 'subtitle', 'text', 'caption'.\n"
    "Output ONLY a JSON object mapping each input string to its English translation, no commentary."
)


def call(strings):
    payload = json.dumps(strings, ensure_ascii=False)
    r = Generation.call(model="qwen-plus", api_key=API_KEY, messages=[
        {"role": "system", "content": SYS},
        {"role": "user", "content": payload},
    ], result_format="message", temperature=0.2)
    if r.status_code != 200:
        raise RuntimeError(f"{r.status_code} {r.message}")
    txt = r.output.choices[0].message.content.strip()
    m = re.search(r"\{.*\}", txt, re.S)
    return json.loads(m.group(0) if m else txt)


def main():
    d = json.load(open(f"{HERE}/directing_all.json", encoding="utf-8"))
    acts, cams = set(), set()
    for lst in d.values():
        for x in lst:
            acts.add(x["action"]); cams.add(x["camera"])
    acts, cams = sorted(acts), sorted(cams)
    print(f"待翻译：动作 {len(acts)} 条 / 镜头 {len(cams)} 条 = {len(acts)+len(cams)}")
    out = {}
    if os.path.exists(f"{HERE}/directing_en.json"):
        out = json.load(open(f"{HERE}/directing_en.json", encoding="utf-8"))
    todo = [s for s in acts + cams if s not in out]
    B = 40
    for i in range(0, len(todo), B):
        chunk = todo[i:i + B]
        try:
            got = call(chunk)
            for k, v in got.items():
                out[k] = v
            json.dump(out, open(f"{HERE}/directing_en.json", "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)   # 每批落盘，断点可续
            print(f"  [{i+len(chunk)}/{len(todo)}] ok", flush=True)
        except Exception as e:
            print(f"  [!] 批次 {i} 失败: {e}", flush=True)
    json.dump(out, open(f"{HERE}/directing_en.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    miss = [s for s in acts + cams if s not in out]
    print(f"\n[✓] 已翻译 {len(out)} 条，缺 {len(miss)} 条")
    for s in miss[:6]:
        print("   缺:", s[:60])


if __name__ == "__main__":
    main()
