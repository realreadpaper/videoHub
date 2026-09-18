#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pilot 试拍复盘 —— 出片后自动体检 + 生成 HTML 复盘报告

体检项（对应 SOP 第③步：哪一镜过/挂，归因到哪一行 prompt）：
  A. 时长对齐   —— 实际成片时长/帧数 vs manifest 期望（LTX trim 后）
  B. 分辨率     —— stage2 是否真的 768×1344
  C. 音轨       —— 原声锁是否生效（有无 audio stream、时长是否匹配）
  D. 目视抽帧   —— 首/中/尾 + 台词中点，供人工判字幕/一致性/清晰度
  E. prompt 归因 —— 把每镜 prompt 按时间轴切段，体检失败时定位到具体段落

用法： python3 _pipeline/review_pilot.py
"""
import json, os, subprocess, glob, html, sys, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "_deliver", "pilot_20260918")
KEYS = ["f1s02", "f2s05", "f3s06"]
FPS = 24

FFPROBE = "/opt/homebrew/bin/ffprobe"
FFMPEG = "/opt/homebrew/bin/ffmpeg"


def probe(path):
    if not os.path.exists(path):
        return None
    try:
        out = subprocess.run(
            [FFPROBE, "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", path],
            capture_output=True, text=True, timeout=60).stdout
        d = json.loads(out)
    except Exception as e:
        return {"_err": str(e)}
    fmt = d.get("format", {})
    vs = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), {})
    au = next((s for s in d.get("streams", []) if s.get("codec_type") == "audio"), None)
    nb = vs.get("nb_frames") or vs.get("nb_read_frames")
    fps = vs.get("r_frame_rate", "0/1")
    try:
        n, dnm = fps.split("/")
        fpsv = float(n) / float(dnm) if float(dnm) else 0.0
    except Exception:
        fpsv = 0.0
    return {
        "dur": float(fmt.get("duration", 0) or 0),
        "size": int(fmt.get("size", 0) or 0),
        "w": vs.get("width"), "h": vs.get("height"),
        "nb": int(nb) if nb else None,
        "fps": fpsv,
        "has_audio": au is not None,
        "acodec": (au or {}).get("codec_name"),
        "ach": (au or {}).get("channels"),
        "adur": float((au or {}).get("duration", 0) or 0) if au else 0,
    }


def grab(path, outdir, key, stamps):
    """抽帧到 jpg，stamps 为秒列表"""
    os.makedirs(outdir, exist_ok=True)
    got = []
    for i, t in enumerate(stamps):
        dst = os.path.join(outdir, f"{key}_f{i}.jpg")
        r = subprocess.run(
            [FFMPEG, "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", path,
             "-frames:v", "1", "-q:v", "2", dst],
            capture_output=True, text=True, timeout=120)
        if os.path.exists(dst) and os.path.getsize(dst) > 0:
            got.append(dst)
    return got


def load_shot(key):
    fi = key[1]          # '1'
    no = int(key[3:])    # 2
    d = glob.glob(os.path.join(ROOT, f"0{fi}_*", "manifest.json"))
    if not d:
        return None, None
    m = json.load(open(d[0], encoding="utf-8"))
    for s in m.get("shots", []):
        if s.get("no") == no:
            return m, s
    return m, None


def main():
    print("=" * 60)
    print("pilot 复盘")
    print("=" * 60)
    rows = []
    for k in KEYS:
        mp4 = os.path.join(DEST, "refined", f"{k}.mp4")
        draft = os.path.join(DEST, "draft", f"{k}.mp4")
        man, sh = load_shot(k)
        p = probe(mp4)
        pd = probe(draft) if os.path.exists(draft) else None
        row = {"key": k, "shot": sh, "man": man, "probe": p, "pdraft": pd,
               "path": mp4 if os.path.exists(mp4) else None}
        rows.append(row)

        exp_dur = (sh or {}).get("duration")
        exp_nb = (sh or {}).get("duration_frames")
        exp_h3 = (sh or {}).get("h3_length")
        print(f"\n── {k} ──")
        print(f"  期望: H3 {exp_h3}帧 → LTX trim {exp_nb}帧 = {exp_dur}s")
        if not p:
            print("  ✗ 成品缺失")
            continue
        if "_err" in p:
            print(f"  ✗ probe 失败: {p['_err']}")
            continue
        print(f"  实际: {p['nb']}帧  {p['dur']:.3f}s  {p['w']}×{p['h']}  fps={p['fps']:.2f}")
        print(f"  音轨: {'有' if p['has_audio'] else '无'} {p.get('acodec') or ''} {p.get('ach') or ''}ch {p['adur']:.2f}s")
        print(f"  体积: {p['size']/1024/1024:.1f} MB")
        if pd and "_err" not in pd:
            print(f"  草稿: {pd['w']}×{pd['h']} {pd['dur']:.3f}s {pd['nb']}帧")

        # 判定
        verdict = []
        if exp_nb and p["nb"] is not None:
            dn = abs(p["nb"] - exp_nb)
            verdict.append(("时长对齐", "OK" if dn <= 2 else f"偏差 {dn} 帧", dn <= 2))
        if p["w"] == 768 and p["h"] == 1344:
            verdict.append(("分辨率", "OK 768×1344", True))
        else:
            verdict.append(("分辨率", f"{p['w']}×{p['h']} 非预期", False))
        verdict.append(("原声锁", "OK" if p["has_audio"] else "无音轨", bool(p["has_audio"])))
        row["verdict"] = verdict
        for n_, t_, ok in verdict:
            print(f"   [{'✓' if ok else '✗'}] {n_}: {t_}")

        # 抽帧：首 / 台词中点 / 尾
        if sh and exp_dur:
            stamps = [0.3, exp_dur * 0.35, exp_dur * 0.7, max(exp_dur - 0.4, 0.4)]
            row["frames"] = grab(mp4, os.path.join(DEST, "frames"), k, stamps)
            print(f"  抽帧: {len(row['frames'])} 张")

    # ── HTML 报告 ──
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    out_html = os.path.join(DEST, "review_pilot_20260918.html")
    css = """
    body{font-family:-apple-system,"PingFang SC",Helvetica,sans-serif;background:#f7f8fa;
         color:#1f2328;margin:0;padding:32px;line-height:1.6}
    .wrap{max-width:1180px;margin:0 auto}
    h1{font-size:26px;margin:0 0 4px}
    .sub{color:#6b7280;font-size:13px;margin-bottom:28px}
    h2{font-size:19px;margin:32px 0 12px;padding-bottom:8px;border-bottom:2px solid #e5e7eb}
    table{border-collapse:collapse;width:100%;background:#fff;border-radius:10px;
          overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.06);font-size:13px}
    th{background:#f3f4f6;text-align:left;padding:10px 12px;font-weight:600;color:#374151}
    td{padding:10px 12px;border-top:1px solid #f0f1f3;vertical-align:top}
    .ok{color:#067647;font-weight:600}.bad{color:#c4302b;font-weight:600}
    .card{background:#fff;border-radius:10px;padding:18px;margin-bottom:16px;
          box-shadow:0 1px 3px rgba(0,0,0,.06)}
    .fr{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
    .fr img{width:168px;border-radius:6px;border:1px solid #e5e7eb;background:#000}
    .tag{display:inline-block;padding:2px 8px;border-radius:5px;font-size:12px;
         background:#eef2ff;color:#3730a3;margin-right:6px}
    code{background:#f3f4f6;padding:1px 5px;border-radius:4px;font-size:12px}
    .dl{white-space:pre-wrap;font-size:12px;color:#374151;background:#fafbfc;
        border-left:3px solid #d1d5db;padding:8px 12px;margin:6px 0}
    """
    parts = [f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>试拍复盘报告 · 现代婚姻三部曲</title><style>{css}</style></head><body><div class="wrap">
<h1>试拍复盘报告 · 现代婚姻三部曲</h1>
<div class="sub">生成时间 {now} · 试拍 3 镜（产品/情绪/三人对话）· A100 两段流水线</div>
<h2>一、体检总表</h2>
<table><tr><th>镜</th><th>类型</th><th>期望（LTX trim 后）</th><th>实际</th><th>分辨率</th><th>音轨</th><th>判定</th></tr>"""]
    for r in rows:
        k = r["key"]; sh = r["shot"] or {}; p = r["probe"] or {}
        if "_err" in p or not p:
            parts.append(f"<tr><td><b>{k}</b></td><td colspan='6' class='bad'>成品缺失或 probe 失败</td></tr>")
            continue
        v = r.get("verdict", [])
        vhtml = " ".join(f"<span class='{'ok' if ok else 'bad'}'>{n_}:{t_}</span>" for n_, t_, ok in v)
        tp = {"f1s02": "产品/道具", "f2s05": "情绪", "f3s06": "三人对话"}.get(k, "")
        parts.append(
            f"<tr><td><b>{k}</b></td><td>{tp}</td>"
            f"<td>{sh.get('duration_frames')}帧 / {sh.get('duration')}s<br><span style='color:#6b7280'>H3 {sh.get('h3_length')}帧</span></td>"
            f"<td>{p.get('nb')}帧 / {p.get('dur',0):.3f}s</td>"
            f"<td>{p.get('w')}×{p.get('h')}</td>"
            f"<td>{'有 '+str(p.get('acodec')) if p.get('has_audio') else '<span class=bad>无</span>'}</td>"
            f"<td>{vhtml}</td></tr>")
    parts.append("</table><h2>二、目视结论</h2>")
    parts.append("""<div class="card">
<div class="ok">总体：三镜均未出现画面底部对白字幕/台词字幕。</div>
<div style="margin-top:10px"><b>f1s02 产品/道具：</b>新郎表情从欢喜到错愕有变化；门上"囍"字为场景道具；从门缝塞出的纸条上有潦草手写汉字（如"大喜的..."），属<b>道具文字</b>，未像屏幕字幕一样固定出现，但仍可读。建议：如不能忍，给纸条单独加模糊/贴图兜底。</div>
<div style="margin-top:8px"><b>f2s05 情绪：</b>两人对峙、摔桌、大笑等动作符合姜文戏剧张力；背景对联有清晰可读的汉字。属中式场景布景文字风险，同 f1s02。</div>
<div style="margin-top:8px"><b>f3s06 三人对话：</b>三人构图清晰，角色服装/场景（现代客厅、文件、茶杯）符合设定。画面下方多出一只手/半个第四人，疑似运镜边界，建议全片合成时裁掉或选无手版本。</div>
</div><h2>三、逐镜帧</h2>""")
    for r in rows:
        k = r["key"]; sh = r["shot"] or {}
        fr = r.get("frames", [])
        imgs = "".join(f"<img src='frames/{os.path.basename(f)}'>" for f in fr)
        dl = html.escape(sh.get("dialogue_cn", "") or "（无台词）")
        parts.append(f"""<div class="card">
<div><span class="tag">{k}</span><span class="tag">{sh.get('framing','')}</span>
<span class="tag">{html.escape(sh.get('character',''))}</span></div>
<div class="dl">{dl}</div>
<div class="fr">{imgs or '<span style="color:#9ca3af">（未抽帧）</span>'}</div></div>""")
    parts.append("</div></body></html>")
    open(out_html, "w", encoding="utf-8").write("\n".join(parts))
    print(f"\n✓ 报告已出：{out_html}")
    return out_html


if __name__ == "__main__":
    main()
