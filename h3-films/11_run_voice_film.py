#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
11_run_voice_film.py —— 「中文干声锁音轨」版双阶段驱动（远端执行）

与 10_run_film.py 的区别：
  · Stage1 不再让 H3 自己说中文（T2VA 台词不稳），改用 audio-lock 工作流
    （stage1_voice_<film>_sNN.json，内含 lock_source + 中文 TTS 干声路径），
    成片音轨 = TTS 干声，语音 100% 中文且音色可控。
  · Stage2 精修沿用 A1 补丁版（完整 VAE 解码），保留 Stage1 音轨。

用法:
  python3 11_run_voice_film.py --film film1 --list
  python3 11_run_voice_film.py --film film1 --shots 5              # 草稿+精修
  python3 11_run_voice_film.py --film film1 --shots 1-20 --stage draft
  python3 11_run_voice_film.py --film film1 --shots 1-20 --stage refine
  python3 11_run_voice_film.py --film film1 --concat
"""
import json, os, re, shutil, subprocess, sys, time

COMFY = "/workspace/ComfyUI"
RUNNER = "/workspace/h3scripts/80_run_workflow_remote.py"
PY = "/workspace/venv/bin/python"
INDIR = COMFY + "/input"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

SLUG = {"film1": "douyin-office", "film2": "douyin-blinddate"}
WORK = {"film1": "/workspace/films/douyin-office", "film2": "/workspace/films/douyin-blinddate"}

C_OK, C_BAD, C_DIM, C_0 = "\033[32m", "\033[31m", "\033[2m", "\033[0m"
def ok(s):  print(C_OK  + "  ✔ " + C_0 + s, flush=True)
def bad(s): print(C_BAD + "  ✘ " + C_0 + s, flush=True)
def dim(s): print(C_DIM + "    "   + C_0 + s, flush=True)
def hdr(s): print("\n" + "═" * 96 + "\n  " + s + "\n" + "═" * 96, flush=True)


def run_workflow(workflow, sets, tag, work):
    cmd = [PY, RUNNER, workflow]
    for k, v in sets:
        cmd += ["--set", "%s=%s" % (k, v)]
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=COMFY)
    el = time.time() - t0
    out = (p.stdout or "") + (p.stderr or "")
    log = os.path.join(work, "logs", "%s.log" % tag)
    os.makedirs(os.path.dirname(log), exist_ok=True)
    open(log, "w", encoding="utf-8").write(out)
    vram = re.search(r"峰值显存[:：]?\s*([\d.]+)", out)
    prod = re.findall(r"->\s*(\S+\.mp4)", out)
    success = p.returncode == 0 and bool(prod)
    return success, (vram.group(1) if vram else "?"), el, (prod[-1] if prod else ""), out


def find_draft(film, no):
    """在 output 里找该镜最新的锁音轨草稿（ComfyUI 每跑一次序号 +1，不能写死 _00001_）"""
    outdir = os.path.join(COMFY, "output/MiniMaxH3", SLUG[film])
    if not os.path.isdir(outdir):
        return None
    cand = [f for f in os.listdir(outdir)
            if re.fullmatch(r"voice_shot%02d_\d+_\.mp4" % no, f)]
    if not cand:
        return None
    cand.sort(key=lambda f: int(re.search(r"_(\d+)_\.mp4", f).group(1)))
    return os.path.join(outdir, cand[-1])


def stage1_voice(film, shot, work, force=False):
    slug = SLUG[film]
    tag = "voice_s%02d" % shot["no"]
    old = find_draft(film, shot["no"])
    if old and not force:
        ok("镜%02d 锁音轨草稿已存在，跳过 -> %s" % (shot["no"], os.path.basename(old)))
        return old
    wf = os.path.join(work, "workflows", "stage1_voice_%s_s%02d.json" % (film, shot["no"]))
    if not os.path.exists(wf):
        bad("镜%02d 缺工作流 %s" % (shot["no"], wf)); return None
    hdr("阶段1·锁音轨草稿 · 镜%02d · %s · 384x672 x 362帧(15s)" % (shot["no"], shot["framing"]))
    good, vram, el, prod, out = run_workflow(wf, [], tag, work)
    if not good:
        bad("镜%02d 草稿失败，日志 %s/logs/%s.log" % (shot["no"], work, tag))
        print("\n".join(out.splitlines()[-25:]))
        return None
    dest = os.path.join(COMFY, "output", prod) if prod else find_draft(film, shot["no"])
    if not dest or not os.path.exists(dest):
        dest = find_draft(film, shot["no"])
    ok("镜%02d 草稿 %.1fs | 峰值显存 %s GiB | %s" % (shot["no"], el, vram, prod))
    return dest


def stage2_refine(film, shot, draft_path, work, force=False):
    slug = SLUG[film]
    fin_dir = os.path.join(work, "final")
    final = os.path.join(fin_dir, "shot%02d.mp4" % shot["no"])
    if os.path.exists(final) and not force:
        ok("镜%02d 精修已存在，跳过" % shot["no"]); return final
    if not draft_path or not os.path.exists(draft_path):
        bad("镜%02d 找不到草稿" % shot["no"]); return None
    inname = "draft_voice_s%02d.mp4" % shot["no"]
    shutil.copyfile(draft_path, os.path.join(INDIR, inname))
    wf2 = os.path.join(work, "workflows", "stage2_vaedecode.json")
    hdr("阶段2·LTX 精修 · 镜%02d -> 768x1344" % shot["no"])
    sets = [
        ("1.file", inname),
        ("3.target_width", 768), ("3.target_height", 1344),
        ("12.text", shot["prompt"]),
        ("20.filename_prefix", "MiniMaxH3/%s/ref_shot%02d" % (slug, shot["no"])),
    ]
    good, vram, el, prod, out = run_workflow(wf2, sets, "ref_shot%02d" % shot["no"], work)
    if not good:
        bad("镜%02d 精修失败，日志 %s/logs/ref_shot%02d.log" % (shot["no"], work, shot["no"]))
        print("\n".join(out.splitlines()[-25:]))
        return None
    src = os.path.join(COMFY, "output", prod) if prod else ""
    if not src or not os.path.exists(src):
        cand = [f for f in os.listdir(os.path.join(COMFY, "output/MiniMaxH3", slug))
                if f.startswith("ref_shot%02d_" % shot["no"]) and f.endswith(".mp4")]
        if not cand:
            bad("镜%02d 精修产物未找到" % shot["no"]); return None
        src = os.path.join(COMFY, "output/MiniMaxH3", slug, sorted(cand)[-1])
    os.makedirs(fin_dir, exist_ok=True)
    shutil.copyfile(src, final)
    ok("镜%02d 精修 %.1fs | 峰值显存 %s GiB -> %s" % (shot["no"], el, vram, final))
    return final


def concat(film, work, man):
    hdr("合成全片 · %s" % film)
    fin_dir = os.path.join(work, "final")
    order = sorted([f for f in os.listdir(fin_dir) if re.match(r"shot\d+\.mp4$", f)],
                   key=lambda x: int(re.search(r"\d+", x).group()))
    if not order:
        bad("没有精修片段可合成"); return None
    lst = os.path.join(work, "concat.txt")
    with open(lst, "w") as fh:
        for f in order:
            fh.write("file '%s'\n" % os.path.join(fin_dir, f))
    out = os.path.join(work, man.get("film_title", film).replace(" · ", "_") + "_全片.mp4")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst,
                    "-c:v", "libx264", "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p",
                    "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                    "-c:a", "aac", "-b:a", "192k", out],
                   capture_output=True, text=True)
    if os.path.exists(out):
        ok("合成 %d 镜 -> %s (%.1f MB)" % (len(order), out, os.path.getsize(out) / 1048576))
    else:
        bad("ffmpeg 合成失败")
    return out


def main():
    args = sys.argv[1:]
    film = "film1"
    if "--film" in args:
        film = args[args.index("--film") + 1]
    work = WORK[film]
    man = json.load(open(os.path.join(work, "manifest.json"), encoding="utf-8"))
    shots = man["shots"]

    if "--list" in args:
        for s in shots:
            print("%02d | %-28s | %ds | %s" % (s["no"], s["framing"], s["duration"],
                                               s.get("dialogue_cn") or "—"))
        return
    if "--concat" in args:
        concat(film, work, man); return

    stage, force, rng = "both", "--force" in args, None
    if "--stage" in args:
        stage = args[args.index("--stage") + 1]
    if "--shots" in args:
        v = args[args.index("--shots") + 1]
        if "-" in v:
            a, b = v.split("-"); rng = set(range(int(a), int(b) + 1))
        else:
            rng = {int(v)}
    sel = [s for s in shots if rng is None or s["no"] in rng]

    os.makedirs(os.path.join(work, "logs"), exist_ok=True)
    os.makedirs(os.path.join(work, "final"), exist_ok=True)

    hdr("%s | %d 镜 | 阶段=%s | 锁音轨(audio-lock)" % (film, len(sel), stage))
    report = []
    for s in sel:
        t0 = time.time()
        draft = None
        if stage in ("both", "draft"):
            draft = stage1_voice(film, s, work, force)
            if draft is None:
                report.append((s["no"], "草稿失败", "")); continue
        if stage in ("both", "refine"):
            if draft is None:
                draft = find_draft(film, s["no"])
            fin = stage2_refine(film, s, draft, work, force)
            report.append((s["no"], "完成" if fin else "精修失败", "%.0fs" % (time.time() - t0)))
        else:
            report.append((s["no"], "草稿完成", "%.0fs" % (time.time() - t0)))

    hdr("汇总")
    for no, st, el in report:
        mark = C_OK + "✔" + C_0 if "完成" in st else C_BAD + "✘" + C_0
        print("  %s 镜 %02d  %s  %s" % (mark, no, st, el))


if __name__ == "__main__":
    main()
