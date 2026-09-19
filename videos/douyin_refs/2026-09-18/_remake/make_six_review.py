#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成「六镜审查页」：3 部 × (剧情镜 + 产品镜)。

每镜给到：
  ① 原片片段 ↔ 复刻片段 并排播放（原片带原声音轨，直接听口型对不对）
  ② 时间轴 / 时长 / 帧数 / 景别 / 说话人 / 台词 / 剧情段落
  ③ 角色与关系（这一镜谁在场、彼此是什么关系）—— 可逐条打勾
  ④ 完整提示词（含 <Characters> 段），可一键复制
  ⑤ 量化指标：帧0 vs 钉首帧、末帧 vs 钉末帧、生成帧 vs 原片参考帧（SSIM）
"""
import json, os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
FF = "/usr/local/bin/ffmpeg"


def ssim(a, b):
    if not (os.path.exists(a) and os.path.exists(b)):
        return None
    r = subprocess.run([FF, "-y", "-i", a, "-i", b, "-lavfi", "ssim", "-f", "null", "-"],
                       capture_output=True, text=True)
    for line in r.stderr.splitlines():
        if "All:" in line:
            try:
                return float(line.split("All:")[1].split()[0])
            except Exception:
                return None
    return None


def frame_of(mp4, t, out):
    subprocess.run([FF, "-v", "error", "-y", "-ss", str(t), "-i", mp4, "-frames:v", "1", out], check=False)
    return os.path.exists(out)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--wf_dir", default="wf_six", help="提示词取自哪批工作流（wf_six / wf_six3）")
    ap.add_argument("--gen", default="_six/gen", help="主版本成片目录（人工动作）")
    ap.add_argument("--gen1", default="_six/gen1", help="对照版成片目录（自动动作，可缺）")
    ap.add_argument("--gen3", default="_six/gen3", help="v5 干净参考帧重出版（可缺）")
    ap.add_argument("--ref_dir", default="full_ref2_v3")
    ap.add_argument("--first_dir", default="full_first4")
    ap.add_argument("--last_dir", default="full_last4")
    ap.add_argument("--out", default="六镜审查.html")
    A = ap.parse_args()
    wf_dir, GEND, GEN1D, GEN3D = A.wf_dir, A.gen, A.gen1, A.gen3
    REFD, FIRSTD, LASTD = A.ref_dir, A.first_dir, A.last_dir

    def rel(d):
        return os.path.relpath(d if os.path.isabs(d) else os.path.join(HERE, d), HERE)
    RG, R1, R3 = rel(GEND), rel(GEN1D), rel(GEN3D)

    rows = json.load(open(f"{HERE}/shots_all.json", encoding="utf-8"))
    six = json.load(open(f"{HERE}/six.json", encoding="utf-8"))
    direct = json.load(open(f"{HERE}/directing_all.json", encoding="utf-8"))
    den = json.load(open(f"{HERE}/directing_en.json", encoding="utf-8"))
    ACT = json.load(open(f"{HERE}/six_action.json", encoding="utf-8"))
    rmap = {f: {x["index"]: x for x in l} for f, l in rows.items()}
    dmap = {f: {x["index"]: x for x in l} for f, l in direct.items()}

    order = ["dy1_s093", "dy1_s088", "dy2_s118", "dy2_s075", "dy3_s145", "dy3_s119"]
    order = [n for n in order if n in six]

    cards = []
    for nm in order:
        ov = six[nm]
        film, idx = ov["film"], ov["shot"]
        r = rmap[film][idx]
        dd = dmap.get(film, {}).get(idx, {})
        act_cn, cam_cn = dd.get("action", ""), dd.get("camera", "")
        act_en = den.get(act_cn, act_cn)
        cam_en = den.get(cam_cn, cam_cn)
        wf = json.load(open(f"{HERE}/{wf_dir}/wf_{nm}.json", encoding="utf-8"))
        prompt = wf["6"]["inputs"]["prompt"]
        sec = wf["14"]["inputs"]["scene_duration_seconds"]
        gen = f"{HERE}/{GEND}/{nm}.mp4"
        gen1 = f"{HERE}/{GEN1D}/{nm}.mp4"
        gen3 = f"{HERE}/{GEN3D}/{nm}.mp4"
        og = f"{HERE}/_six/orig/{nm}.mp4"
        ref = f"{HERE}/{REFD}/{nm}.jpg"
        f_first = f"{HERE}/{FIRSTD}/{nm}.jpg"
        f_last = f"{HERE}/{LASTD}/{nm}.jpg"

        def metrics(path):
            m = {}
            if not os.path.exists(path):
                return m
            g0 = f"/tmp/_six_{nm}_f0.jpg"
            gl = f"/tmp/_six_{nm}_fl.jpg"
            gm = f"/tmp/_six_{nm}_fm.jpg"
            frame_of(path, 0.02, g0)
            frame_of(path, max(0.0, sec - 0.05), gl)
            frame_of(path, sec * 0.35, gm)
            m["f0"] = ssim(g0, f_first)
            m["fl"] = ssim(gl, f_last)
            m["mid"] = ssim(gm, ref)
            return m

        m = metrics(gen)
        m1 = metrics(gen1)
        m3 = metrics(gen3)
        cards.append(dict(nm=nm, ov=ov, r=r, act_cn=act_cn, cam_cn=cam_cn, act_en=act_en, cam_en=cam_en,
                          prompt=prompt, sec=sec, gen=gen, gen1=gen1, gen3=gen3, og=og, ref=ref,
                          f_first=f_first, f_last=f_last, m=m, m1=m1, m3=m3))
        if nm in ACT:
            cards[-1]["act_human_en"] = ACT[nm]["action"]
            cards[-1]["cam_human_en"] = ACT[nm]["camera"]
            cards[-1]["act_human_cn"] = ACT[nm].get("action_cn", "")
            cards[-1]["cam_human_cn"] = ACT[nm].get("camera_cn", "")

    def fnum(v):
        return "—" if v is None else f"{v:.3f}"

    def cls(v):
        if v is None:
            return "na"
        return "good" if v >= 0.55 else ("mid" if v >= 0.4 else "bad")

    body = []
    for c in cards:
        nm, ov, r, m = c["nm"], c["ov"], c["r"], c["m"]
        gen_ok = os.path.exists(c["gen"])
        gen1_ok = os.path.exists(c["gen1"])
        gen3_ok = os.path.exists(c["gen3"])
        m1 = c.get("m1", {})
        m3 = c.get("m3", {})
        kind = ov["kind"]
        kcls = "drama" if kind == "剧情镜" else "prod"
        body.append(f"""
<section class="card" id="{nm}">
  <header class="chead">
    <div class="ctitle"><span class="badge {kcls}">{kind}</span>
      <b>{ov['film']}</b> · <code>{nm}</code> · s{ov['shot']:03d}
      <span class="muted">原片 {r['start']:.2f}s–{r['end']:.2f}s（{r['dur']:.2f}s）→ 生成 {c['sec']:.2f}s / {c['r']['frames']} 帧（栅格向上吸附）</span>
    </div>
    <div class="cfg">Hybrid 双端锁定 · 4 步 · ref_image_size=max · 参考帧已去字</div>
  </header>

  <div class="videos{' v3' if gen1_ok else ''}">
    <figure><figcaption>① 原片片段（原声）</figcaption>
      <video src="_six/orig/{nm}.mp4" controls loop preload="metadata" poster="_six/orig/{nm}_poster.jpg"></video>
    </figure>
    <figure class="main"><figcaption>② 复刻片段 · <b>{'干净参考帧 v5（本次）' if gen3_ok else '人工动作文本'}</b>（H3 · 原片音轨驱动口型）</figcaption>
      {'<video src="' + (R3 if gen3_ok else RG) + '/' + nm + '.mp4" controls loop preload="metadata"></video>'
         if (gen3_ok or gen_ok) else '<div class="pending">尚未回收</div>'}
    </figure>
    {('<figure><figcaption>③ 对照 · v3 参考帧版（字幕未洗净）</figcaption><video src="' + RG + '/' + nm
      + '.mp4" controls loop preload="metadata"></video></figure>') if (gen3_ok and gen_ok) else ''}
    {('<figure><figcaption>④ 对照 · 自动动作文本版（旧）</figcaption><video src="' + R1 + '/' + nm
      + '.mp4" controls loop preload="metadata"></video></figure>') if gen1_ok else ''}
  </div>

  <div class="grid">
    <div class="box">
      <h4>台词与镜头</h4>
      <table class="kv">
        <tr><th>景别</th><td>{r['framing']}</td></tr>
        <tr><th>说话人</th><td>{r['speaker']}</td></tr>
        <tr><th>台词</th><td class="line">{r['line']}</td></tr>
        <tr><th>剧情段落</th><td>{r.get('seg','')}</td></tr>
        <tr><th>镜头运动</th><td>{c['cam_cn'] or '—'}</td></tr>
        <tr><th>镜内动作</th><td>{c['act_cn'] or '—'}</td></tr>
      </table>
    </div>
    <div class="box">
      <h4>角色与关系（可打勾核对）</h4>
      <ul class="cast">
        {''.join(f'<li><label><input type="checkbox">{x}</label></li>' for x in ov['cast_cn'])}
      </ul>
      <p class="rel"><b>关系：</b>{ov['rel_cn']}</p>
    </div>
  </div>

  <div class="box">
    <h4>量化指标 <span class="muted">（SSIM，越高越贴原片；0.85+ = 被钉住）</span></h4>
    <table class="metrics">
      <tr><th>版本</th><th>帧 0 vs 钉死首帧</th><th>末帧 vs 钉死末帧</th><th>中段 vs 原片参考帧</th></tr>
      {('<tr><td class="lab">干净参考帧 v5</td><td class="' + cls(m3.get('f0')) + '">' + fnum(m3.get('f0')) + '</td>'
        + '<td class="' + cls(m3.get('fl')) + '">' + fnum(m3.get('fl')) + '</td>'
        + '<td class="' + cls(m3.get('mid')) + '">' + fnum(m3.get('mid')) + '</td></tr>') if gen3_ok else ''}
      <tr><td class="lab">人工动作（v3 参考帧）</td>
        <td class="{cls(m.get('f0'))}">{fnum(m.get('f0'))}</td>
        <td class="{cls(m.get('fl'))}">{fnum(m.get('fl'))}</td>
        <td class="{cls(m.get('mid'))}">{fnum(m.get('mid'))}</td></tr>
      {('<tr><td class="lab">自动动作</td><td class="' + cls(m1.get('f0')) + '">' + fnum(m1.get('f0')) + '</td>'
        + '<td class="' + cls(m1.get('fl')) + '">' + fnum(m1.get('fl')) + '</td>'
        + '<td class="' + cls(m1.get('mid')) + '">' + fnum(m1.get('mid')) + '</td></tr>') if gen1_ok else ''}
    </table>
    <p class="hint">末帧掉到 0.6 以下 = 中途推镜跑了；中段偏低 = 构图被改。</p>
  </div>

  <div class="box">
    <h4>镜内动作与运镜：自动台本 vs 人工重写</h4>
    <table class="actcmp">
      <tr><th>来源</th><th>动作</th><th>运镜</th></tr>
      <tr class="badrow"><td>脚本自动分配</td><td>{c['act_cn'] or '—'}</td><td class="bad">{c['cam_cn'] or '—'}</td></tr>
      <tr class="goodrow"><td>人工按原片重写</td><td>{c.get('act_human_cn','—')}</td>
        <td class="good">{c.get('cam_human_cn','—')}</td></tr>
    </table>
  </div>

  <details class="box">
    <summary><b>完整提示词</b>（{len(c['prompt'])} 字符，含 &lt;Characters&gt; 段）<button class="copy" data-t="{nm}">复制</button></summary>
    <pre id="p_{nm}">{c['prompt'].replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')}</pre>
  </details>

  <div class="box note">
    <h4>审核要点</h4>
    <ul class="cast">
      {''.join(f'<li><label><input type="checkbox">{x}</label></li>' for x in ov['note_cn'].split('；'))}
    </ul>
  </div>
</section>""")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>六镜审查 · 三部复刻（剧情镜 + 产品镜）</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;background:#0d0f12;color:#e8ecf1;font:15px/1.65 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif}}
.wrap{{max-width:1180px;margin:0 auto;padding:28px 20px 80px}}
h1{{font-size:26px;margin:0 0 6px}}
.sub{{color:#9aa7b6;margin-bottom:22px}}
.summary{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin:18px 0 30px}}
.sm{{background:#151a20;border:1px solid #232b34;border-radius:10px;padding:12px 14px}}
.sm b{{display:block;font-size:20px;color:#fff;margin-bottom:2px}}
.sm span{{color:#94a3b3;font-size:13px}}
.card{{background:#12161b;border:1px solid #232b34;border-radius:14px;padding:18px;margin-bottom:26px}}
.chead{{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap;margin-bottom:14px}}
.ctitle{{font-size:16px}}
.badge{{display:inline-block;padding:2px 9px;border-radius:20px;font-size:12px;margin-right:8px;vertical-align:1px}}
.badge.drama{{background:#3a2a4d;color:#d9b8ff}}
.badge.prod{{background:#1f3b2c;color:#9ff0bd}}
.muted{{color:#8b98a6;font-size:13px}}
.cfg{{color:#7f8b99;font-size:12px;border:1px dashed #2c353f;border-radius:8px;padding:6px 10px;white-space:nowrap}}
.videos{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:16px}}
.videos.v3{{grid-template-columns:1fr 1fr 1fr}}
figure.main figcaption b{{color:#9ff0bd}}
figure{{margin:0}}
figcaption{{color:#9aa7b6;font-size:13px;margin-bottom:6px}}
video{{width:100%;border-radius:10px;background:#000;display:block}}
.pending{{aspect-ratio:768/1344;border:1px dashed #35404c;border-radius:10px;display:flex;align-items:center;justify-content:center;color:#6f7c8a}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px}}
.box{{background:#151a20;border:1px solid #232b34;border-radius:10px;padding:13px 15px;margin-bottom:12px}}
.box h4{{margin:0 0 9px;font-size:14px;color:#cfe0f0}}
table.kv{{width:100%;border-collapse:collapse;font-size:13.5px}}
table.kv th{{text-align:left;color:#8b98a6;font-weight:400;width:74px;vertical-align:top;padding:3px 0}}
table.kv td{{padding:3px 0}}
td.line{{color:#ffd88a}}
ul.cast{{margin:0;padding-left:2px;list-style:none;font-size:13.5px}}
ul.cast li{{margin-bottom:5px}}
ul.cast label{{display:flex;gap:8px;align-items:flex-start;cursor:pointer}}
p.rel{{margin:10px 0 0;color:#b9e6c9;font-size:13.5px;border-top:1px dashed #2c353f;padding-top:9px}}
table.metrics{{width:100%;border-collapse:collapse;text-align:center;font-size:14px}}
table.metrics th{{color:#8b98a6;font-weight:400;font-size:12.5px;padding-bottom:5px}}
table.metrics td{{font-size:18px;font-variant-numeric:tabular-nums;padding:4px 0;border-radius:6px}}
td.good{{color:#7ef2a8}} td.mid{{color:#ffd166}} td.bad{{color:#ff8f8f}} td.na{{color:#66707c}}
table.metrics td.lab{{text-align:left;font-size:13px;color:#9aa7b6;white-space:nowrap}}
table.actcmp{{width:100%;border-collapse:collapse;font-size:13px}}
table.actcmp th{{text-align:left;color:#8b98a6;font-weight:400;font-size:12.5px;padding:3px 8px 6px 0}}
table.actcmp td{{padding:8px 10px 8px 0;vertical-align:top;border-top:1px solid #232b34;line-height:1.55}}
table.actcmp td:first-child{{color:#9aa7b6;white-space:nowrap;width:104px}}
tr.badrow td{{color:#cbb2b2}}
tr.goodrow td{{color:#b9e6c9}}
td.bad{{color:#ff9a9a}} td.good{{color:#7ef2a8}}
.hint{{margin:9px 0 0;color:#7f8b99;font-size:12.5px}}
details.box summary{{cursor:pointer;color:#cfe0f0}}
pre{{background:#0b0e12;border:1px solid #232b34;border-radius:8px;padding:12px;overflow:auto;max-height:440px;
   white-space:pre-wrap;font:12.5px/1.6 ui-monospace,Menlo,Consolas,monospace;color:#c8d6e5;margin:11px 0 0}}
button.copy{{background:#243040;color:#cfe0f0;border:1px solid #35404c;border-radius:6px;padding:2px 10px;font-size:12px;cursor:pointer;margin-left:8px}}
button.copy:hover{{background:#2e3d50}}
.box.note{{border-color:#3a3320;background:#1a1710}}
.box.note h4{{color:#ffd88a}}
@media(max-width:860px){{.videos,.grid{{grid-template-columns:1fr}}}}
</style></head><body><div class="wrap">
<h1>六镜审查 · 三部复刻</h1>
<div class="sub">每部各挑 <b>1 个剧情镜</b>（人物关系戏）+ <b>1 个产品镜</b>（产品露出）。全部从原片逐镜拆解表中按真实时间轴取镜，
参考帧取自原片同镜（已抹掉原片字幕/时间戳），音频用原片该镜音轨切片驱动口型。配置：<b>Hybrid 首尾双端锁定 + 4 步</b>。</div>
<div class="summary">
  <div class="sm"><b>6</b><span>镜（3 剧情 + 3 产品）</span></div>
  <div class="sm"><b>{sum(c['r']['frames'] for c in cards)}</b><span>总帧数（24fps）</span></div>
  <div class="sm"><b>{sum(c['sec'] for c in cards):.1f}s</b><span>生成总时长（原片 {sum(c['r']['dur'] for c in cards):.1f}s）</span></div>
  <div class="sm"><b>4 步</b><span>采样步数（按你定的，不再上调）</span></div>
</div>
{''.join(body)}
</div>
<script>
document.querySelectorAll('button.copy').forEach(b=>b.addEventListener('click',e=>{{
  e.preventDefault();
  const t=document.getElementById('p_'+b.dataset.t).innerText;
  navigator.clipboard.writeText(t).then(()=>{{b.textContent='已复制';setTimeout(()=>b.textContent='复制',1400);}});
}}));
</script></body></html>"""
    out = f"{HERE}/{A.out}"
    open(out, "w", encoding="utf-8").write(html)
    print(f"[✓] {out}  共 {len(cards)} 镜")
    for c in cards:
        m = c["m"]
        print(f"  {c['nm']} {c['ov']['kind']}: f0={fnum(m.get('f0'))} last={fnum(m.get('fl'))} mid={fnum(m.get('mid'))}")


if __name__ == "__main__":
    main()
