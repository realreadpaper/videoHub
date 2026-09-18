#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
export_prompts.py — 把两部片子的 manifest.json 里的 H3 生产 Prompt 导出成可读文件。

产出（每片一份 md + 一份纯文本，另加一份两片合并的浅色 HTML 总览）：
  film1-office/PROMPTS.md       逐镜可读版（含景别/角色/场景/台词/音效/配乐 + 完整 prompt）
  film1-office/PROMPTS_flat.txt 纯 prompt 拼接版（批处理粘贴用）
  film2-blinddate/...           同上
  两剧本提示词总览.html          浅色主题总览，带一键复制

用法：
  python3 export_prompts.py                 # 导出 workspace 里两部片
  python3 export_prompts.py a/manifest.json b/manifest.json
"""
import html
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MANIFESTS = [
    os.path.join(HERE, "film1-office", "manifest.json"),
    os.path.join(HERE, "film2-blinddate", "manifest.json"),
]


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def meta_line(m, shot):
    bits = [
        f"景别 {shot.get('framing', '-')}",
        f"时长 {shot.get('duration', '-')}s",
        f"角色 {shot.get('character', '-')}",
        f"场景 {shot.get('scene', '-')}",
    ]
    flags = []
    if shot.get("anchored"):
        flags.append("首帧锚定")
    if shot.get("ref"):
        flags.append("参考图")
    if flags:
        bits.append("／".join(flags))
    return " ｜ ".join(bits)


def write_film_md(m, out_dir, manifest_path):
    title = m["film_title"]
    shots = m["shots"]
    lines = [
        f"# H3 生产 Prompt · {title}",
        "",
        f"> 来源：`{os.path.relpath(manifest_path, HERE)}`　"
        f"｜ schema `{m.get('prompt_schema', '-')}`",
        f"> 影调：{m.get('director_style', '-')}",
        "",
        "## 全局参数",
        "",
        "| 项 | 值 |",
        "|---|---|",
        f"| 主题 | {m.get('theme', '-')} |",
        f"| 帧率 | {m.get('fps')} → 交付 {m.get('target_fps')} |",
        f"| 单镜时长 | {m.get('shot_duration_sec')}s（{m.get('h3_length')} 帧） |",
        f"| 画幅 | {m.get('aspect_ratio')} |",
        f"| S1 分辨率 | {m.get('resolution_stage1')} |",
        f"| S2 分辨率 | {m.get('resolution_stage2')}（{m.get('refined_frames')} 帧） |",
        f"| 固定 seed | `{m.get('seed')}` |",
        f"| 镜头数 | {len(shots)} |",
        "",
        f"> 全片 prompt 合计 {sum(len(s['prompt']) for s in shots):,} 字符，"
        f"平均 {sum(len(s['prompt']) for s in shots) // len(shots):,} 字符/镜。",
        "",
        "---",
        "",
        "## 逐镜 Prompt",
        "",
    ]
    for s in shots:
        lines += [
            f"### 镜 {s['no']:02d} · `{s.get('file', '-')}`",
            "",
            f"**{meta_line(m, s)}**",
            "",
        ]
        if s.get("dialogue"):
            lines.append("**台词**")
            lines.append("")
            for who, text in s["dialogue"]:
                lines.append(f"- `{who}` {text}")
            lines.append("")
        lines += ["**Prompt**", "", "```text", s["prompt"], "```", "", "---", ""]
    out = os.path.join(out_dir, "PROMPTS.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + "\n")
    return out


def write_film_flat(m, out_dir):
    shots = m["shots"]
    parts = ["#" * 72, f"# FILM: {m['film_title']}", f"# shots: {len(shots)}", "#" * 72, ""]
    for s in shots:
        parts += [
            "",
            "#" * 8,
            f"# SHOT {s['no']:02d} | {s.get('file', '-')} | {s.get('framing', '-')} "
            f"| {s.get('duration', '-')}s",
            "#" * 8,
            "",
            s["prompt"],
            "",
        ]
    out = os.path.join(out_dir, "PROMPTS_flat.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(parts).rstrip() + "\n")
    return out


def write_overview(films, out_path):
    e = html.escape
    rows = []
    nav = []
    for fi, m in enumerate(films):
        fid = f"film{fi + 1}"
        nav.append(f'<a class="chip" href="#{fid}">{e(m["film_title"])}</a>')
        rows.append(f'<section id="{fid}"><h2>{e(m["film_title"])}</h2>')
        rows.append(
            f'<p class="sub">seed <code>{m.get("seed")}</code> · '
            f'{m.get("resolution_stage1")} → {m.get("resolution_stage2")} · '
            f'{len(m["shots"])} 镜 · 单镜 {m.get("shot_duration_sec")}s</p>'
        )
        for s in m["shots"]:
            dlg = ""
            if s.get("dialogue"):
                items = "".join(
                    f'<li><b>{e(w)}</b> {e(t)}</li>' for w, t in s["dialogue"]
                )
                dlg = f'<details class="dlg"><summary>台词 {len(s["dialogue"])} 句</summary><ul>{items}</ul></details>'
            badge = ""
            if s.get("anchored"):
                badge += '<span class="tag t-anchor">首帧锚定</span>'
            if s.get("ref"):
                badge += '<span class="tag t-ref">参考图</span>'
            pid = f"p-{fid}-{s['no']:02d}"
            rows.append(
                '<article class="shot">'
                f'<header><span class="no">镜 {s["no"]:02d}</span>'
                f'<span class="slug">{e(s.get("file", "-"))}</span>{badge}'
                f'<button class="copy" data-target="{pid}">复制 Prompt</button></header>'
                f'<p class="meta">{e(meta_line(m, s))}</p>{dlg}'
                f'<pre id="{pid}">{e(s["prompt"])}</pre>'
                "</article>"
            )
        rows.append("</section>")

    doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>两剧本提示词总览 · H3 生产 Prompt</title>
<style>
  :root {{
    --bg:#f6f7f9; --panel:#ffffff; --ink:#1c1f23; --muted:#6b7280;
    --line:#e5e7eb; --accent:#c0392b; --accent-soft:#fdecea; --code:#fafafa;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
    font:15px/1.65 -apple-system,BlinkMacSystemFont,"PingFang SC","Helvetica Neue",sans-serif; }}
  .wrap {{ max-width:1080px; margin:0 auto; padding:40px 24px 80px; }}
  h1 {{ font-size:26px; margin:0 0 6px; }}
  .lede {{ color:var(--muted); margin:0 0 22px; }}
  nav {{ display:flex; gap:8px; flex-wrap:wrap; margin-bottom:28px; }}
  .chip {{ text-decoration:none; color:var(--ink); background:var(--panel);
    border:1px solid var(--line); border-radius:999px; padding:6px 14px; font-size:13px; }}
  .chip:hover {{ border-color:var(--accent); color:var(--accent); }}
  section {{ margin-bottom:44px; }}
  h2 {{ font-size:20px; margin:0 0 4px; padding-top:12px; border-top:2px solid var(--ink); }}
  .sub {{ color:var(--muted); font-size:13px; margin:0 0 18px; }}
  .shot {{ background:var(--panel); border:1px solid var(--line); border-radius:12px;
    padding:16px 18px; margin-bottom:14px; }}
  .shot header {{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; }}
  .no {{ font-weight:700; }}
  .slug {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12.5px; color:var(--muted); }}
  .tag {{ font-size:11.5px; padding:2px 8px; border-radius:999px; }}
  .t-anchor {{ background:#eef6ff; color:#1d4ed8; }}
  .t-ref {{ background:#eefaf1; color:#15803d; }}
  .copy {{ margin-left:auto; font:inherit; font-size:12.5px; cursor:pointer;
    background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:5px 12px; }}
  .copy:hover {{ border-color:var(--accent); color:var(--accent); }}
  .copy.done {{ background:var(--accent-soft); border-color:var(--accent); color:var(--accent); }}
  .meta {{ font-size:13px; color:var(--muted); margin:8px 0 10px; }}
  .dlg {{ font-size:13.5px; margin-bottom:10px; }}
  .dlg summary {{ cursor:pointer; color:var(--muted); }}
  .dlg ul {{ margin:8px 0 0; padding-left:20px; }}
  pre {{ background:var(--code); border:1px solid var(--line); border-radius:8px;
    padding:14px; margin:0; font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
    font-size:12.5px; line-height:1.55; white-space:pre-wrap; word-break:break-word;
    max-height:420px; overflow:auto; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>两剧本提示词总览</h1>
  <p class="lede">H3 生产 Prompt · 共 {sum(len(m["shots"]) for m in films)} 镜 ·
    合计 {sum(len(s["prompt"]) for m in films for s in m["shots"]):,} 字符 ·
    来源 manifest.json（schema {e(films[0].get("prompt_schema", "-"))}）</p>
  <nav>{"".join(nav)}</nav>
  {"".join(rows)}
</div>
<script>
document.querySelectorAll('.copy').forEach(function (b) {{
  b.addEventListener('click', function () {{
    var t = document.getElementById(b.dataset.target).textContent;
    navigator.clipboard.writeText(t).then(function () {{
      var old = b.textContent; b.textContent = '已复制 ✓'; b.classList.add('done');
      setTimeout(function () {{ b.textContent = old; b.classList.remove('done'); }}, 1400);
    }});
  }});
}});
</script>
</body>
</html>
"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(doc)
    return out_path


def main():
    paths = sys.argv[1:] or DEFAULT_MANIFESTS
    films = []
    for p in paths:
        if not os.path.exists(p):
            print(f"跳过（不存在）：{p}")
            continue
        m = load(p)
        d = os.path.dirname(os.path.abspath(p))
        print("md   :", write_film_md(m, d, p))
        print("flat :", write_film_flat(m, d))
        films.append(m)
    if films:
        print("html :", write_overview(films, os.path.join(HERE, "两剧本提示词总览.html")))


if __name__ == "__main__":
    main()
