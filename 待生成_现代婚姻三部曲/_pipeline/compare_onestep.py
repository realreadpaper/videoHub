#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一步直出 vs 两阶段精修 · 对比复盘
1) 体检：时长/帧数/分辨率/音轨 是否命中 manifest（一步口径 = H3 帧数）
2) 抽帧：两版同相对位置抽 4 帧，并列拼图
3) 出 HTML 报告（浅色主题）
"""
import json, os, re, subprocess, sys

FFPROBE = "/opt/homebrew/bin/ffprobe"
FFMPEG = "/opt/homebrew/bin/ffmpeg"
ROOT = "/Users/hejianglong/Desktop/videoHub/待生成_现代婚姻三部曲"
ONE = os.path.join(ROOT, "_deliver/onestep_20260918")
TWO = os.path.join(ROOT, "_deliver/pilot_20260918")
OUT_HTML = os.path.join(ONE, "对比_一步直出vs两阶段_20260918.html")

KEYS = ["f1s02", "f2s05", "f3s06"]
LABEL = {"f1s02": "产品/道具", "f2s05": "情绪", "f3s06": "三人对话"}


def probe(path):
    if not os.path.exists(path):
        return None
    try:
        out = subprocess.run(
            [FFPROBE, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height,nb_frames,r_frame_rate,codec_name",
             "-show_entries", "format=duration", "-of", "json", path],
            capture_output=True, text=True, timeout=60).stdout
        d = json.loads(out)
        st = d["streams"][0]
        nb = st.get("nb_frames")
        fps = st.get("r_frame_rate", "24/1")
        fpsv = eval(fps) if "/" in fps else float(fps)
        dur = float(d["format"]["duration"])
        nbf = int(nb) if nb and nb.isdigit() else round(dur * fpsv)
        a = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "a:0",
                            "-show_entries", "stream=codec_name,channels",
                            "-of", "csv=p=0", path],
                           capture_output=True, text=True, timeout=60).stdout.strip()
        return dict(w=st["width"], h=st["height"], frames=nbf, dur=dur,
                    codec=st["codec_name"], audio=a or "—")
    except Exception as e:
        return dict(err=str(e)[:60])


def manifest_expect():
    """读一步口径 manifest：duration = h3_length/24, frames = h3_length"""
    exp = {}
    for i, d in enumerate(sorted(os.listdir(ROOT))):
        mp = os.path.join(ROOT, d, "manifest.json")
        if not (d[:2].isdigit() and os.path.exists(mp)):
            continue
        fi = int(d[:2])
        m = json.load(open(mp, encoding="utf-8"))
        for s in m["shots"]:
            exp[f"f{fi}s{s['no']:02d}"] = dict(
                frames=s["h3_length"], dur=s["duration"],
                h3=s["h3_length"], mode=m.get("generation_mode", "?"))
    return exp


def grab(src, dst, frac, scale=520):
    """按相对位置抽帧；先用 -ss 精确定位"""
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", str(frac),
                    "-i", src, "-frames:v", "1",
                    "-vf", f"scale={scale}:-1", dst],
                   capture_output=True, timeout=120)
    return os.path.exists(dst)


def main():
    exp = manifest_expect()
    fr_dir = os.path.join(ONE, "cmp_frames")
    os.makedirs(fr_dir, exist_ok=True)

    rows = []
    for k in KEYS:
        p_one = os.path.join(ONE, "refined", f"{k}.mp4")
        p_two = os.path.join(TWO, "refined", f"{k}.mp4")
        i1, i2 = probe(p_one), probe(p_two)
        e = exp.get(k, {})
        ok = []
        if i1 and e:
            if i1.get("frames") == e["frames"]:
                ok.append("帧数✓")
            else:
                ok.append(f"帧数✗({i1.get('frames')}≠{e['frames']})")
            if abs(i1.get("dur", 0) - e["dur"]) < 0.05:
                ok.append("时长✓")
            else:
                ok.append(f"时长✗({i1.get('dur'):.2f}≠{e['dur']:.2f})")
            if (i1.get("w"), i1.get("h")) == (768, 1344):
                ok.append("分辨率✓")
            else:
                ok.append(f"分辨率✗{i1.get('w')}x{i1.get('h')}")
            if i1.get("audio") and i1["audio"] != "—":
                ok.append("音轨✓")
            else:
                ok.append("音轨✗")
        rows.append(dict(k=k, label=LABEL.get(k, ""), one=i1, two=i2, exp=e,
                         checks=ok))

        # 抽帧：两版各 3 个相对位置
        if i1:
            for n, f in enumerate([0.15, 0.45, 0.80]):
                grab(p_one, os.path.join(fr_dir, f"{k}_one_{n}.jpg"), i1["dur"] * f)
        if i2:
            for n, f in enumerate([0.15, 0.45, 0.80]):
                grab(p_two, os.path.join(fr_dir, f"{k}_two_{n}.jpg"), i2["dur"] * f)

    # ---- HTML ----
    P = []
    P.append("""<meta charset="utf-8"><title>一步直出 vs 两阶段精修</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;
background:#f7f7f5;color:#222;margin:0;padding:32px;line-height:1.6}
h1{font-size:22px;margin:0 0 4px}
h2{font-size:17px;margin:30px 0 10px;padding-bottom:6px;border-bottom:2px solid #e2e2de}
.sub{color:#777;font-size:13px;margin-bottom:20px}
table{border-collapse:collapse;width:100%;background:#fff;font-size:13px;
border:1px solid #e2e2de;border-radius:6px;overflow:hidden}
th,td{padding:8px 10px;text-align:left;border-bottom:1px solid #eee}
th{background:#f0f0ec;font-weight:600}
tr:last-child td{border-bottom:none}
.ok{color:#1a8a4a;font-weight:600}.bad{color:#c0392b;font-weight:600}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:8px}
.card{background:#fff;border:1px solid #e2e2de;border-radius:8px;padding:10px}
.card .t{font-size:12px;color:#777;margin-bottom:6px;font-weight:600}
.card img{width:100%;border-radius:4px;display:block}
.tag{display:inline-block;background:#eef4ff;color:#2b5cd9;font-size:11px;
padding:2px 7px;border-radius:10px;margin-left:6px}
.tag.g{background:#eaf6ee;color:#1a8a4a}
.mono{font-family:"SF Mono",Menlo,monospace;font-size:12px}
.note{background:#fffbe9;border-left:3px solid #e0b400;padding:10px 14px;
font-size:13px;margin:14px 0;border-radius:0 4px 4px 0}
</style>""")
    P.append("<h1>一步直出 768×1344 vs 两阶段精修</h1>")
    P.append("<div class='sub'>现代婚姻三部曲 · 每片一镜对比 · "
             f"{__import__('time').strftime('%Y-%m-%d %H:%M')}</div>")

    P.append("<h2>一、体检（一步直出）</h2><table>")
    P.append("<tr><th>镜</th><th>类型</th><th>期望帧/秒</th><th>实际帧/秒</th>"
             "<th>分辨率</th><th>音轨</th><th>判定</th></tr>")
    for r in rows:
        i1, e = r["one"], r["exp"]
        if not i1:
            P.append(f"<tr><td class='mono'>{r['k']}</td><td>{r['label']}</td>"
                     "<td colspan='5'>未生成</td></tr>")
            continue
        chk = " ".join(
            f"<span class='{'ok' if '✓' in c else 'bad'}'>{c}</span>"
            for c in r["checks"])
        P.append(f"<tr><td class='mono'>{r['k']}</td><td>{r['label']}</td>"
                 f"<td class='mono'>{e.get('frames','?')} / {e.get('dur',0):.3f}s</td>"
                 f"<td class='mono'>{i1.get('frames')} / {i1.get('dur',0):.3f}s</td>"
                 f"<td class='mono'>{i1.get('w')}×{i1.get('h')}</td>"
                 f"<td class='mono'>{i1.get('audio')}</td><td>{chk}</td></tr>")
    P.append("</table>")

    # 耗时对比
    logf = os.path.join(ONE, "logs/run_one.log")
    if os.path.exists(logf):
        txt = open(logf, encoding="utf-8", errors="ignore").read()
        times = re.findall(r"\[✓\] (\w+) OK\s+用时 (\d+) s", txt)
        if times:
            P.append("<h2>二、实测耗时</h2><table><tr><th>镜</th>"
                     "<th>一步直出</th><th>两阶段（历史）</th><th>倍数</th></tr>")
            old = {"f1s02": 140.0, "f2s05": 143.1, "f3s06": 144.5}
            for k, t in times:
                t = int(t)
                o = old.get(k)
                P.append(f"<tr><td class='mono'>{k}</td><td>{t} s "
                         f"({t/60:.1f} min)</td>"
                         f"<td>{o:.0f} s</td><td>{t/o:.2f}×</td></tr>"
                         if o else f"<tr><td class='mono'>{k}</td>"
                         f"<td>{t} s</td><td>—</td><td>—</td></tr>")
            avg = sum(int(t) for _, t in times) / len(times)
            P.append(f"<tr><td><b>均值</b></td><td><b>{avg:.0f} s "
                     f"({avg/60:.1f} min)</b></td><td><b>≈143 s</b></td>"
                     f"<td><b>{avg/143:.2f}×</b></td></tr>")
            P.append("</table>")

    P.append("<h2>三、逐镜画质对比（左：一步直出 / 右：两阶段精修）</h2>")
    for r in rows:
        k = r["k"]
        P.append(f"<div class='card' style='margin-bottom:18px'>"
                 f"<div class='t'>{k} · {r['label']}"
                 f"<span class='tag'>相对位置 15% / 45% / 80%</span></div>")
        for n in range(3):
            a = f"cmp_frames/{k}_one_{n}.jpg"
            b = f"cmp_frames/{k}_two_{n}.jpg"
            if not (os.path.exists(os.path.join(ONE, a))
                    or os.path.exists(os.path.join(ONE, b))):
                continue
            P.append("<div class='grid'>")
            P.append(f"<div class='card'><div class='t'>一步直出 768</div>"
                     f"<img src='{a}' onerror='this.style.display=\"none\"'></div>")
            P.append(f"<div class='card'><div class='t'>两阶段精修</div>"
                     f"<img src='{b}' onerror='this.style.display=\"none\"'></div>")
            P.append("</div>")
        P.append("</div>")

    P.append("<div class='note'><b>怎么看</b>：重点看面部皮肤纹理、发丝边缘、"
             "文字/图案锐度、暗部噪点。一步直出理论上细节更硬、边缘更锐；"
             "两阶段因从 384 草稿上采样，容易发糊、涂抹感重。</div>")

    open(OUT_HTML, "w", encoding="utf-8").write("\n".join(P))

    # ---- stdout 摘要 ----
    print("一步直出体检：\n")
    print(f"{'镜':<8}{'类型':<10}{'期望':>16}{'实际':>16}{'分辨率':>12}{'判定'}")
    for r in rows:
        i1, e = r["one"], r["exp"]
        if not i1:
            print(f"{r['k']:<8}{r['label']:<10}  未生成")
            continue
        st = "✓" if all("✓" in c for c in r["checks"]) else "✗"
        print(f"{r['k']:<8}{r['label']:<10}"
              f"{str(e.get('frames')) + '帧/' + format(e.get('dur',0),'.3f') + 's':>16}"
              f"{str(i1.get('frames')) + '帧/' + format(i1.get('dur',0),'.3f') + 's':>16}"
              f"{str(i1.get('w')) + '×' + str(i1.get('h')):>12}   {st}")
    print(f"\n报告：{OUT_HTML}")


if __name__ == "__main__":
    main()
