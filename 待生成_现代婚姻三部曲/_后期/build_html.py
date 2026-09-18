#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用「工程台本 HTML」生成器
读取 manifest.json（+ 可选的 production.json 实测数据），输出一份浅色主题的完整拍摄台本。
换片只需换 manifest，脚本不动。
"""
import json, os, sys, html, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.normpath(os.path.join(HERE, ".."))


def resolve(film=None, root=None):
    """定位 manifest / production。兼容两种工程布局：
       A) <root>/<film>/manifest.json         （三部曲式，一目录一片）
       B) <root>/manifest.json                （单片工程）
    """
    if film:
        d = os.path.join(root or BASE, film) if not os.path.isabs(film) else film
        return (os.path.join(d, "manifest.json"),
                os.path.join(d, "production.json"), d)
    return (os.path.join(root or BASE, "manifest.json"),
            os.path.join(root or BASE, "production.json"), root or BASE)


def normalize(m, d):
    """把 manifest 归一化成台本生成器统一字段。
    新格式(三部曲) → 旧格式(不可剥夺) 的映射：
       film_title→film, h3_length→length_frames, resolution_stage2→refine_w/h
    同时补齐旧格式没有的：refined_frames / shot_duration / start 累加。
    """
    def _res(key, defv):
        v = m.get(key)
        if isinstance(v, str) and "x" in v:
            a, b = v.lower().split("x"); return int(a), int(b)
        return defv

    film = m.get("film") or m.get("film_title") or os.path.basename(d)
    fps = int(m.get("fps") or 24)
    L = int(m.get("length_frames") or m.get("h3_length") or 124)
    RF = int(m.get("refined_frames") or 0) or (8 * ((L - 1) // 8) + 1)
    rw, rh = _res("resolution_stage2", (m.get("refine_w") or 1344, m.get("refine_h") or 768))
    dw, dh = _res("resolution_stage1", (m.get("draft_w") or 672, m.get("draft_h") or 384))

    shots = m["shots"]
    # 补 start 时间码（旧格式自带，新格式没有）
    t = 0.0
    for sh in shots:
        if "start" not in sh:
            sh["start"] = int(round(t))
        dur = sh.get("duration") or round(RF / fps)
        sh["duration"] = int(round(dur))
        t += dur

    return {
        "raw": m, "dir": d, "film": film, "shots": shots,
        "fps": fps, "length_frames": L, "refined_frames": RF,
        "draft_w": dw, "draft_h": dh, "refine_w": rw, "refine_h": rh,
        "seed": m.get("seed", 20260914),
        "series": m.get("series") or (m.get("director_style") and "%s 风格单元" % m["director_style"]) or "自建 H3 管线出品",
        "title_en": m.get("title_en") or (m.get("director_style") or ""),
        "theme": m.get("theme") or "",
        "total_seconds": int(round(sum(s["duration"] for s in shots))),
        "shot_sec": round(L / fps, 3),
        "ref_sec": round(RF / fps, 3),
        "n": len(shots),
    }

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{
--bg:#f4f2ee; --paper:#ffffff; --ink:#22201d; --ink2:#4a463f; --muted:#8a8378;
--line:#e3ded5; --line2:#cec7ba;
--red:#a8322a; --redbg:#fdf1ef;
--amber:#a06a12; --amberbg:#fdf6e8;
--teal:#1f6f63; --tealbg:#edf7f5;
--blue:#2c5f8f; --bluebg:#eef4fa;
--violet:#5c4a86; --violetbg:#f4f1fa;
--serif:"Songti SC","SimSun","Source Han Serif SC",Georgia,serif;
--sans:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
--mono:"SF Mono","JetBrains Mono",Menlo,Consolas,monospace;
}
body{background:var(--bg);color:var(--ink);font-family:var(--sans);line-height:1.75;
  font-size:15px;-webkit-font-smoothing:antialiased}
.wrap{max-width:1100px;margin:0 auto;padding:0 26px 90px}

header.top{background:var(--paper);border-bottom:1px solid var(--line);
  padding:44px 0 34px;margin-bottom:30px}
header.top .wrap{padding-bottom:0}
.kicker{font-family:var(--mono);font-size:11.5px;letter-spacing:.18em;
  color:var(--red);text-transform:uppercase;margin-bottom:14px}
h1{font-family:var(--serif);font-size:42px;line-height:1.18;letter-spacing:.01em;margin-bottom:6px}
h1 small{display:block;font-size:15px;font-weight:400;color:var(--muted);
  font-family:var(--mono);letter-spacing:.08em;margin-top:8px}
.lead{margin-top:18px;font-size:16px;color:var(--ink2);max-width:760px}
.lead b{color:var(--red)}

h2{font-family:var(--serif);font-size:25px;margin:52px 0 8px;padding-top:26px;
  border-top:2px solid var(--ink);display:flex;align-items:baseline;gap:12px}
h2 .n{font-family:var(--mono);font-size:13px;color:var(--muted);font-weight:400}
h3{font-size:17px;margin:30px 0 12px;padding-left:11px;border-left:3px solid var(--red)}
h4{font-size:14.5px;margin:20px 0 8px;color:var(--ink2)}
p{margin:10px 0}
a{color:var(--blue);text-decoration:none;border-bottom:1px solid var(--line2)}
a:hover{border-bottom-color:var(--blue)}
code{font-family:var(--mono);font-size:12.5px;background:#efece5;
  padding:1.5px 5px;border-radius:3px;color:#7a4a20}

.grid{display:grid;gap:13px;margin:16px 0}
.g2{grid-template-columns:1fr 1fr} .g3{grid-template-columns:repeat(3,1fr)}
.g4{grid-template-columns:repeat(4,1fr)}
.card{background:var(--paper);border:1px solid var(--line);border-radius:9px;padding:16px 18px}
.card .k{font-size:11.5px;font-family:var(--mono);color:var(--muted);letter-spacing:.09em;
  text-transform:uppercase;margin-bottom:7px}
.card .v{font-family:var(--serif);font-size:25px;line-height:1.15}
.card .v small{font-size:13px;color:var(--muted);font-family:var(--sans);margin-left:3px}
.card .d{font-size:12.5px;color:var(--muted);margin-top:6px;line-height:1.55}

table{width:100%;border-collapse:collapse;margin:16px 0;font-size:13.5px;
  background:var(--paper);border:1px solid var(--line);border-radius:8px;overflow:hidden}
th{background:#ebe7df;text-align:left;padding:10px 13px;font-weight:600;
  font-size:12.5px;color:var(--ink2);border-bottom:1px solid var(--line2)}
td{padding:10px 13px;border-bottom:1px solid var(--line);vertical-align:top}
tr:last-child td{border-bottom:none}
td.num,th.num{font-family:var(--mono);font-size:12.5px;white-space:nowrap}

.box{border-radius:8px;padding:14px 17px;margin:16px 0;font-size:13.5px;border:1px solid}
.box .t{display:block;font-weight:700;margin-bottom:6px;font-size:13.5px}
.b-red{background:var(--redbg);border-color:#eccfc9} .b-red .t{color:var(--red)}
.b-amber{background:var(--amberbg);border-color:#e8d9b5} .b-amber .t{color:var(--amber)}
.b-teal{background:var(--tealbg);border-color:#c8e2dc} .b-teal .t{color:var(--teal)}
.b-blue{background:var(--bluebg);border-color:#cddff0} .b-blue .t{color:var(--blue)}
.b-violet{background:var(--violetbg);border-color:#d8cff0} .b-violet .t{color:var(--violet)}

/* 分镜 */
.shot{background:var(--paper);border:1px solid var(--line);border-radius:10px;
  margin:18px 0;overflow:hidden}
.shot-h{display:flex;align-items:center;gap:13px;padding:13px 18px;
  background:linear-gradient(180deg,#fbfaf8,#f4f1ea);border-bottom:1px solid var(--line)}
.shot-no{font-family:var(--mono);font-size:19px;font-weight:700;color:var(--red);
  min-width:44px}
.shot-h .ti{font-family:var(--serif);font-size:18px;flex:1}
.tag{font-family:var(--mono);font-size:11px;padding:2.5px 8px;border-radius:20px;
  border:1px solid var(--line2);color:var(--ink2);background:#fff;white-space:nowrap}
.shot-b{padding:16px 18px}
.meta{display:grid;grid-template-columns:repeat(auto-fit,minmax(165px,1fr));
  gap:9px;margin-bottom:14px}
.meta div{font-size:12.5px}
.meta .k{font-family:var(--mono);font-size:10.5px;color:var(--muted);
  letter-spacing:.08em;text-transform:uppercase}
.dia{margin:12px 0;padding:11px 15px;background:var(--redbg);
  border-left:3px solid var(--red);border-radius:0 6px 6px 0;font-size:13.5px}
.dia .who{font-family:var(--mono);font-size:11px;color:var(--red);
  letter-spacing:.08em;display:block;margin-bottom:3px}
pre{background:#2c2a26;color:#e8e4dc;padding:14px 16px;border-radius:7px;
  overflow-x:auto;font-family:var(--mono);font-size:12px;line-height:1.62;
  margin:10px 0;white-space:pre-wrap;word-break:break-word}
pre.prose{background:#f7f5f1;color:#3a352d;border:1px solid var(--line);
  font-family:var(--sans);font-size:13px}
.toc{background:var(--paper);border:1px solid var(--line);border-radius:9px;
  padding:18px 22px;margin:22px 0}
.toc ol{list-style:none;counter-reset:t;columns:2;column-gap:34px}
.toc li{counter-increment:t;font-size:13.5px;padding:3.5px 0;break-inside:avoid}
.toc li::before{content:counter(t,decimal-leading-zero);font-family:var(--mono);
  font-size:11px;color:var(--red);margin-right:9px}
footer{margin-top:60px;padding-top:22px;border-top:1px solid var(--line);
  font-size:12.5px;color:var(--muted);text-align:center}
.cap{font-size:12.5px;color:var(--muted);margin-top:-6px}
@media(max-width:760px){
  h1{font-size:29px} .g2,.g3,.g4{grid-template-columns:1fr}
  .toc ol{columns:1} .wrap{padding:0 15px 60px}
}
"""

def esc(s):
    return html.escape(str(s), quote=False)


def build(film=None):
    MAN, PROD, D = resolve(film)
    m = normalize(json.load(open(MAN, encoding="utf-8")), D)
    p = json.load(open(PROD, encoding="utf-8")) if os.path.exists(PROD) else {}
    shots = m["shots"]
    n = m["n"]
    total = m["total_seconds"]

    s = []
    A = s.append
    A('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">')
    A('<meta name="viewport" content="width=device-width,initial-scale=1">')
    A('<title>《%s》完整工程台本 · %d镜AI微电影生产册</title>' % (esc(m["film"]), n))
    A('<style>%s</style></head><body>' % CSS)

    A('<header class="top"><div class="wrap">')
    A('<div class="kicker">AI 微电影工程台本 · 自建 H3 两阶段管线出片</div>')
    A('<h1>《%s》<small>%s · %s</small></h1>' % (esc(m["film"]), esc(m["title_en"]), esc(m["series"])))
    A('<p class="lead">全片 <b>%d 镜 · %d 秒</b>，%d×%d / %d fps，含原生中文对白音轨。'
      '%s</p>'
      % (n, total, m["refine_w"], m["refine_h"], m["fps"],
         ('主题：' + esc(m["theme"]) + '。') if m.get("theme") else ""))
    A('</div></header><div class="wrap">')

    # KPI
    A('<div class="grid g4">')
    for k, v, u, d in [
        ("镜头数", n, "镜", "每镜 %d 帧 / %.3f 秒" % (m["length_frames"], m["shot_sec"])),
        ("成片时长", total, "秒", "%d fps · 电影帧率" % m["fps"]),
        ("成片分辨率", "%d×%d" % (m["refine_w"], m["refine_h"]), "", "长宽比 %.2f" % (m["refine_w"] / m["refine_h"])),
        ("生成成本", "0", "元", "自有 4090，未用付费 API"),
    ]:
        A('<div class="card"><div class="k">%s</div><div class="v">%s<small>%s</small></div>'
          '<div class="d">%s</div></div>' % (esc(k), esc(v), esc(u), esc(d)))
    A('</div>')

    # TOC
    toc = ["影片规格与生产路径", "一致性锚点（防漂移）", "%d 镜完整分镜台本" % n,
           "生产参数与一键复现", "真机实测记录", "已知限制与优化方向"]
    A('<div class="toc"><ol>')
    for i, t in enumerate(toc, 1):
        A('<li><a href="#s%d">%s</a></li>' % (i, esc(t)))
    A('</ol></div>')

    # 1
    A('<h2 id="s1"><span class="n">01</span>影片规格与生产路径</h2>')
    A('<table><tbody>')
    for k, v in [
        ("片名", "《%s》" % m["film"]),
        ("风格 / 系列", "%s / %s" % (m["title_en"] or "—", m["series"])),
        ("主题", m["theme"] or "—"),
        ("画面规格", "%d×%d，%d fps，H.264 + AAC" % (m["refine_w"], m["refine_h"], m["fps"])),
        ("单镜帧数", "%d 帧（草稿）→ %d 帧（精修裁切后，%.3f 秒）" % (m["length_frames"], m["refined_frames"], m["ref_sec"])),
        ("时长", "%d 镜 × %.3f 秒 = %d 秒" % (n, m["ref_sec"], total)),
        ("引擎", "MiniMax H3（pruned INT8-ConvRot）+ LTX-2.5 精修"),
        ("硬件", "RTX 4090 单卡 / 92 GiB 内存 / 自建 ComfyUI"),
        ("成本", "0 元（不走付费 API）"),
    ]:
        A('<tr><td style="width:150px;color:#8a8378">%s</td><td>%s</td></tr>' % (esc(k), esc(v)))
    A('</tbody></table>')

    A('<h3>为什么是两阶段</h3>')
    A('<p>草稿阶段用 <b>%d×%d / 4 步</b> 快速生成，再交给 <b>LTX-2.5</b> 精修到 '
      '<b>%d×%d</b>。这条路径把"试错"和"出画质"分开：调提示词时只跑草稿，'
      '定稿后再精修，重跑成本低。</p>' % (m["draft_w"], m["draft_h"], m["refine_w"], m["refine_h"]))
    A('<div class="box b-amber"><span class="t">帧数必须落在 17n+5 网格上</span>'
      '<p style="margin:0">H3 的 <code>length</code> 只接受 <b>17n+5</b>（≈%d fps）。本片取 '
      '<b>%d 帧</b>（%.3f 秒）；精修阶段 LTX-2.5 的 <code>frame_policy=trim_to_8n_plus_1</code> 再裁到 '
      '<b>%d 帧</b>（8n+1），最终 <b>%.3f 秒</b>。乱填帧数会直接报错或产生音画错位。</p></div>'
      % (m["fps"], m["length_frames"], m["shot_sec"], m["refined_frames"], m["ref_sec"]))

    # 2
    A('<h2 id="s2"><span class="n">02</span>一致性锚点（防漂移）</h2>')
    A('<p>AI 视频的头号敌人是<b>角色一致性</b>。文生视频模式下无法锁脸，本片用的是最稳的做法：'
      '把同一段角色特征 Token 在 %d 镜里<b>逐字机械复制</b>，绝不换同义词。</p>' % n)
    chars = sorted({sh.get("character", "") for sh in shots if sh.get("character")})
    A('<h3>角色锚点</h3><p>%s</p>' % ("、".join("<code>%s</code>" % esc(c) for c in chars) or "—"))
    A('<h3>镜 01 Prompt 全文（其余各镜同一写法，角色段逐字复制）</h3>'
      '<pre>%s</pre>' % esc(shots[0].get("prompt", "")))
    A('<div class="box b-teal"><span class="t">全局同 seed：%s</span>'
      '<p style="margin:0">文生视频锁不住脸，<b>同 seed 是最省力的稳定杠杆</b>：内容由 Prompt 决定'
      '（景别、动作都能被正确执行），噪声基底一致让同一张脸在各镜之间更稳。'
      '要工业化复用同一角色时，应升级到 <code>fl2va</code> 首尾帧驱动路径。</p></div>' % m.get("seed", 20260914))

    # 3
    A('<h2 id="s3"><span class="n">03</span>%d 镜完整分镜台本</h2>' % n)
    A('<p class="cap">每镜均含景别 / 时长 / 画面调度 / 台词 / 可直接复制的生成 Prompt。</p>')
    for sh in shots:
        A('<div class="shot">')
        A('<div class="shot-h"><span class="shot-no">%02d</span>'
          '<span class="ti">%s</span>'
          '<span class="tag">%s</span>'
          '<span class="tag">%ds</span></div>' % (sh["no"], esc(sh["framing"].split(" (")[0]),
                                                 esc(sh["framing"]), sh["duration"]))
        A('<div class="shot-b">')
        A('<div class="meta">'
          '<div><div class="k">时间码</div>%02d:%02d – %02d:%02d</div>'
          '<div><div class="k">景别</div>%s</div>'
          '<div><div class="k">帧数</div>%d → %d</div>'
          '<div><div class="k">台词</div>%s</div></div>'
          % (sh["start"] // 60, sh["start"] % 60,
             (sh["start"] + sh["duration"]) // 60, (sh["start"] + sh["duration"]) % 60,
             esc(sh["framing"]), m["length_frames"], m["refined_frames"],
             "有" if sh.get("dialogue_cn") else "无（纯环境声）"))
        if sh.get("dialogue_cn"):
            for line in sh["dialogue_cn"].split("／"):
                A('<div class="dia"><span class="who">台词</span>%s</div>' % esc(line))
        A('<h4>生成 Prompt</h4><pre>%s</pre>' % esc(sh.get("prompt", "")))
        A('</div></div>')
    A('</div>')

    # 4
    A('<h2 id="s4"><span class="n">04</span>生产参数与一键复现</h2>')
    A('<h3>阶段 1 · H3 草稿</h3>')
    A('<table><thead><tr><th>项</th><th>值</th></tr></thead><tbody>')
    for k, v in [
        ("工作流", "01-basic-generation/2026-08-06_H3_Turbo_Stable_4V4A.json"),
        ("unet_name", "minimax_h3_fl2va_pruned_int8_convrot.safetensors"),
        ("lora_name", "minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors"),
        ("clip_name", "minimax_h3/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"),
        ("节点 6", "prompt / width=%d / height=%d / length=%d / task_type=T2VA"
                   % (m["draft_w"], m["draft_h"], m["length_frames"])),
        ("节点 7", "steps=4 / shift_video=12.0 / shift_audio=3.0"),
        ("节点 9", "noise_seed=%d" % m.get("seed", 20260914)),
    ]:
        A('<tr><td style="width:130px">%s</td><td><code>%s</code></td></tr>' % (esc(k), esc(v)))
    A('</tbody></table>')
    A('<h3>阶段 2 · LTX-2.5 精修</h3>')
    A('<table><thead><tr><th>项</th><th>值</th></tr></thead><tbody>')
    for k, v in [
        ("工作流", "22-sol-engine-h3-super/2026-08-29_..._LTX25_Advanced_EXP.json"),
        ("节点 1 file", "上一步草稿（须放入 ComfyUI/input/）"),
        ("节点 3", "target_width=%d / target_height=%d / frame_policy=trim_to_8n_plus_1"
                   % (m["refine_w"], m["refine_h"])),
        ("节点 12 text", "与阶段 1 <b>逐字完全相同</b>的 Prompt"),
        ("节点 9", "LTX 蒸馏 LoRA 强度 0.8"),
    ]:
        A('<tr><td style="width:130px">%s</td><td>%s</td></tr>' % (esc(k), v))
    A('</tbody></table>')
    fd = os.path.basename(m["dir"])
    A('<h3>一键命令</h3><pre>'
      '# 全套 %d 镜（草稿 + 精修）\n'
      '/workspace/venv/bin/python /workspace/films/%s/10_run_film.py --shots 1-%d\n\n'
      '# 推荐分两趟（先全草稿再全精修，省掉逐镜换模型的开销）\n'
      '10_run_film.py --shots 1-%d --stage draft\n'
      '10_run_film.py --shots 1-%d --stage refine\n\n'
      '# 只跑某一镜\n'
      '10_run_film.py --shots 3\n\n'
      '# 断点续跑（已存在的自动跳过）\n'
      '10_run_film.py --shots 2-%d\n\n'
      '# 合成全片（含响度归一化）\n'
      '10_run_film.py --concat</pre>' % (n, fd, n, n, n, n))

    # 5
    A('<h2 id="s5"><span class="n">05</span>真机实测记录</h2>')
    rows = p.get("rows") or []
    if rows:
        A('<table><thead><tr><th class="num">镜</th><th>景别</th><th class="num">草稿(s)</th>'
          '<th class="num">精修(s)</th><th class="num">峰值显存(GiB)</th><th>台词</th></tr></thead><tbody>')
        for r in rows:
            A('<tr><td class="num">%02d</td><td>%s</td><td class="num">%s</td>'
              '<td class="num">%s</td><td class="num">%s</td><td>%s</td></tr>'
              % (r["no"], esc(r.get("framing", "")), r.get("draft_s", "—"),
                 r.get("refine_s", "—"), r.get("vram", "—"),
                 "有" if r.get("dialogue") else "—"))
        A('</tbody></table>')
    for k, v, cls in p.get("notes", []):
        A('<div class="box %s"><span class="t">%s</span><p style="margin:0">%s</p></div>'
          % (cls, esc(k), v))
    if not rows and not p.get("notes"):
        A('<p class="cap">（实测数据将在成片跑完后回填）</p>')

    # 6
    A('<h2 id="s6"><span class="n">06</span>已知限制与优化方向</h2>')
    A('<ol style="padding-left:22px;font-size:14px">')
    for t in [
        "<b>单镜安全上限 15.08 秒（362 帧）。</b>实测 17 秒起必然出现帧间跳变（帧差 MAE 从 2.5 跃到 38 以上）。人物特写是最敏感题材，动作/多主体镜头余量更小，上排产前先拿目标镜头单发验证。",
        "<b>角色一致性靠 Token 复述 + 同 seed，不是锁脸。</b>工业化复用同一角色时，应改用 <code>fl2va</code>（首尾帧驱动）路径：先生成定妆图，再以首帧垫图驱动每一镜，漂移率可再降一个量级。",
        "<b>模型会自发在台词镜烧中文字幕，且渲染不稳、常出乱码。</b>本片 Prompt 已显式抑制（<code>no subtitles, no captions, no on-screen text</code>），中文硬字幕由本地后期用 Pillow 渲染 + overlay 烧入。",
        "<b>台词为模型原生生成</b>，个别字可能音近而非精确。某镜台词不达标时，<b>只需重跑该镜</b>，画面无需单独重生成。",
        "<b>音轨电平天然不齐</b>（各镜独立生成）。合成阶段必须做两遍 <code>loudnorm</code>（I=-16 / TP=-1.5 / LRA=11）——单遍是动态估计，实测只能到 -18.5 LUFS。",
        "<b>画面文字需节制</b>：ASCII 数字渲染干净；中文界面文字会糊，原稿的中文 HUD 应改写成纯数字。",
        "<b>原稿的 <code>--no watermark,...</code> 是 Midjourney 语法</b>，H3 不认，改用自然语言负向约束写在 Prompt 尾部。",
    ]:
        A('<li style="margin:8px 0">%s</li>' % t)
    A('</ol>')

    A('<footer>《%s》完整工程台本 · 由自建 H3 两阶段管线生产 · 生成于 %s'
      '</footer>' % (esc(m["film"]), "2026-09-14"))
    A('</div></body></html>')

    out = os.path.join(m["dir"], "《%s》完整工程台本.html" % m["film"])
    open(out, "w", encoding="utf-8").write("\n".join(s))
    print("已生成", os.path.normpath(out), "%.1f KB" % (os.path.getsize(out) / 1024))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--film", default=None,
                    help="工程子目录名，如 01_周星驰_三十八万八；省略则用脚本上级目录")
    a = ap.parse_args()
    build(a.film)
