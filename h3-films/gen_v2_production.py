#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按 v2 分镜（_lines_rhythm）+ v1 素材（pN_data）生成 v2 生产文件：

  1. 逐镜分类：产品镜（beat 含 pouch/packet/sachet 或 v1 已标 ref/anchored）→ I2V-Ref2VA
     （ref_images = _refs/prod_P2_white.png，prompt 用 <Picture 1> 认领）；其余 → T2V。
  2. 混合执行档：产品镜 + 开场镜 + 揭示/反转关键镜 + 收尾末镜 → 草稿→精修（two_stage）；
     其余 → 一次成型（oneshot，384×672 单次直出）。
  3. 逐镜 prompt：单一连续镜头（v2 一镜=一次生成=一条连续 take），
     beat 取 v1 对应时间段的动作描述，运镜措辞跟实测 motion，产品镜带 SP_REF 锚定块。
  4. 产出 film{1,2}-office|blinddate/manifest_v2.json + PROMPTS_v2.md。

生成后由 gen_storyboard_rhythm.py 把方式/档位列合并回 STORYBOARD.md。
"""
import importlib, json, os, re, sys
from pathlib import Path

H3 = "/Users/hejianglong/Desktop/videoHub/h3-films"
ALLOWED = os.path.realpath("/Users/hejianglong/Desktop/videoHub")

OUT = {
    ("film1", "manifest"): H3 + "/film1-office/manifest_v2.json",
    ("film1", "prompts"): H3 + "/film1-office/PROMPTS_v2.md",
    ("film2", "manifest"): H3 + "/film2-blinddate/manifest_v2.json",
    ("film2", "prompts"): H3 + "/film2-blinddate/PROMPTS_v2.md",
}
REF_IMG = "_refs/prod_P2_white.png"  # 主推参考图（图生视频方案文档选定）
PROD_RE = re.compile(r"\b(pouch|packet|sachet)\b", re.I)

CFG = {
    "film1": {
        "mod": "p1_data", "lines": H3 + "/_lines_rhythm/film1_shot_lines.json",
        "key_units": [1, 9, 10, 20],  # 开场假摔 / 身份揭示 / 收尾点题 → 精修
        "key_note": "开场假摔（镜1）· 身份揭示（承自 v1 镜9/10）· 收尾点题（末镜）",
    },
    "film2": {
        "mod": "p2_data", "lines": H3 + "/_lines_rhythm/film2_shot_lines.json",
        "key_units": [1, 15, 16, 20],  # 开场父子 / 反转揭示 / 收尾点题 → 精修
        "key_note": "开场父子（镜1）· 反转揭示（承自 v1 镜15/16）· 收尾点题（末镜）",
    },
}

# p2_data 尚未升级的片无关常量（SP_REF/_REF_NOTE/STYLE_REF/NO_TEXT_CLAUSE_ANCHORED）
# 统一从 p1_data 取，保证两片产品镜口径一字不差。
_SHARED_FROM_P1 = ("SP_REF", "_REF_NOTE", "STYLE_REF", "NO_TEXT_CLAUSE_ANCHORED")

CAMERA_EN = {
    "固定机位": "Locked-off static camera, steady framing for the whole take.",
    "缓动/主体运动": "Gentle handheld feel or slow drift, subtle motion only.",
    "强运动": "Visible camera or subject movement carries through the take.",
}


def safe(p):
    rp = os.path.realpath(p)
    if not (rp == ALLOWED or rp.startswith(ALLOWED + os.sep)):
        raise ValueError("path outside workspace: " + p)
    return rp


def fmt_ts(t):
    m = int(t // 60)
    return "%02d:%06.3f" % (m, t - m * 60)


def build_film(film):
    cfg = CFG[film]
    mod = importlib.import_module(cfg["mod"])
    if cfg["mod"] != "p1_data":
        p1 = importlib.import_module("p1_data")
        for k in _SHARED_FROM_P1:
            if k not in vars(mod):
                setattr(mod, k, getattr(p1, k))
    lines = json.load(open(safe(cfg["lines"]), encoding="utf-8"))
    dur = lines["src_duration"]
    unit_span = dur / 20.0
    v1 = {s["no"]: s for s in mod.SHOTS}
    by_file = {s["file"]: s for s in mod.SHOTS}

    shots_out = []
    n_shots = len(lines["shots"])
    for w in lines["shots"]:
        u = by_file[w["src_unit"]]
        u_no, beats = u["no"], u["beats"]
        # v3 镜（10–15s）会跨多个 v1 单元：聚合所有重叠单元的 beats，按时间序拼接
        sel, overl = [], []
        for u2 in mod.SHOTS:
            ut0 = (u2["no"] - 1) * unit_span
            if w["t1"] <= ut0 or w["t0"] >= ut0 + unit_span:
                continue
            overl.append(u2)
            beats2 = u2["beats"]
            step2 = 15.0 / len(beats2)
            r0 = max((w["t0"] - ut0) / unit_span, 0.0)
            r1 = min((w["t1"] - ut0) / unit_span, 1.0)
            for i, b in enumerate(beats2):
                if (i + 1) * step2 > r0 * 15 and i * step2 < r1 * 15:
                    sel.append(b)
        if not sel:
            sel = [u["beats"][-1]]
            overl = [u]
        beat = sel[0].rstrip(". ") + "."
        for kx, b in enumerate(sel[1:]):
            bb = b.strip()
            if not bb:
                continue
            lead = (" Then, still in the same continuous take, "
                    if kx == 0 else " The take then continues with ")
            beat += lead + (bb[0].lower() + bb[1:] if bb else "")

        is_product = bool(PROD_RE.search(beat) or
                          any(PROD_RE.search(x.get("sound", "")) or x.get("ref") or x.get("anchored")
                              for x in overl))
        task = "ref2va" if is_product else "t2va"
        is_key = (w["no"] == 1 or w["no"] == n_shots or u_no in cfg["key_units"])
        # 成片一律 768×1344，且【不走精修】（2026-09-17 实测定案）：
        #   LTX 精修会把 H3 草稿画的伪字幕高清描清，严禁；唯一路线 = H3 直出 768×1344。
        # 伪字幕是 H3 生成阶段的顽固模式（换 seed/强化措辞都压不干净），
        # 生产上必须走机器门：每镜抽帧 OCR 验字（check_no_text.py），FAIL 自动换 seed 重抽。
        tier = "direct768"

        # ── prompt 组装（复用 pN_data 常量，口径与 _prompt() 一致：ref > anchored > 严格版）
        speakers = []
        for sp, _ in w["dialogue"]:
            if sp not in speakers:
                speakers.append(sp)
        keys = [k for k in mod._CAST_ORDER
                if k in speakers or (k in vars(mod) and k not in ("SP",) and
                                     re.search(r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])" % k, beat))]
        if "SP" not in keys and PROD_RE.search(beat):
            keys.append("SP")
        keys = [k for k in mod._CAST_ORDER if k in keys]
        g = vars(mod)
        cast_parts = []
        for k in keys:
            cast_parts.append(g["SP_REF"] if (task == "ref2va" and k == "SP") else g[k])
        pre = ""
        if cast_parts:
            pre += mod._CAST_BLOCK % "; ".join(cast_parts)
        sc = mod.SCENE_EN.get(u["scene"])
        if sc:
            pre += mod._SCENE_BLOCK % sc
        if task == "ref2va":
            pre += mod._REF_NOTE
        cont = ("One single continuous take, no cuts; the shot runs about %.1f seconds. %s "
                % (w["seconds"], CAMERA_EN[w["camera"]]))
        style = mod.STYLE_REF if task == "ref2va" else mod.STYLE
        body = "[%s – %s] %s %s%s" % (fmt_ts(0), fmt_ts(w["seconds"]), beat, cont, style)
        # 原声锁：v1 遗留的 "No speech, no voices." 与 <Audio 1> 原声矛盾，统一改口径
        sound = u["sound"].replace("No speech, no voices.",
                                   "All voices, ambience and music are carried by <Audio 1>.")
        prompt = ("integrated_multimodal_description:\n" + pre + body +
                  "\n\noverall_soundscape:\n%s\n\nnon_diegetic_music:\n%s"
                  % (sound, u["music"]))

        shots_out.append({
            "no": w["no"], "file": w["file"], "t0": w["t0"], "t1": w["t1"],
            "seconds": w["seconds"], "frames": w["frames"],
            "motion": w["motion"], "camera": w["camera"], "segment": w["segment"],
            "scene": u["scene"], "framing": w["base_framing"],
            "characters": sorted(set(speakers), key=lambda s: mod._CAST_ORDER.index(s)
                                 if s in mod._CAST_ORDER else 99),
            "dialogue": w["dialogue"],
            "task_type": task,
            "ref_images": [REF_IMG] if task == "ref2va" else [],
            "exec_tier": tier,
            "resolution_final": "768x1344",
            "is_key": is_key,
            "audio_file": "orig_audio/%s/shot%02d.wav" % (film, w["no"]),
            "audio_source": "参考片原声 [%.2f, %.2f]（补静音到 15.0833s 整窗）" % (w["t0"], w["t1"]),
            "src_unit": w["src_unit"], "src_beats_used": len(sel),
            "prompt": prompt,
        })

    n_prod = sum(1 for s in shots_out if s["task_type"] == "ref2va")
    n_t2v = n_shots - n_prod
    film_meta = dict(mod.FILM)
    film_meta.update({
        "version": "v3-cut-aligned-units", "n_shots": n_shots,
        "shot_duration_sec": "units 10-15.08s (per-shot seconds/frames; 镜界对齐实测切点/换段硬边界)",
        "resolution_final": "768x1344",  # 成片一律 768×1344（本地再转 720×1280 抖音标准）
        "exec": {
            "requirement": "成片全部 768x1344；一律 H3 直出（【不走精修】）",
            "direct768_t2v": "H3 直出 768x1344（fl2va + audio-lock；实测热跑 611–780s/镜）",
            "direct768_i2v": "H3 Ref2VA 直出 768x1344（产品镜带参考图；实测 651–851s/镜）",
            "banned": "LTX 精修（draft_refine）严禁：2026-09-17 实测证实它会把 H3 草稿的伪字幕高清描清",
            "one_shot": "一次性生成为准（2026-09-18 定案）：不设 OCR 验字门、不做重抽循环；"
                            "禁字条款已写死在每镜 prompt 里（零时间成本），伪字幕残余后期人工处理",
            "batch_order": "① T2V 直出批（fl2va 连跑）→ ② I2V 直出批（ref2va 连跑，产品镜）。"
                           "两批各自连跑绝不交替；批次内同进程省权重装卸",
        },
        "audio": {
            "mode": "original_audio_lock（原声锁音轨，2026-09-18 定案）",
            "source": "参考片对应 [t0,t1] 时段原声（对白/环境/配乐全保），补静音到 15.0833s 整窗；"
                      "成片音轨 = 原声，口型随原声",
            "spec": "32kHz 立体声 PCM；本地 _audio_orig/<film>/shotNN.wav；远端 ComfyUI input/orig_audio/<film>/",
            "preamble": "<Audio 1> carries the original soundtrack of this scene: the actors' real "
                        "voices, ambience and music. Keep the visual timing, phrasing, lip movement "
                        "and performance locked to <Audio 1> exactly. Follow the shot description "
                        "below exactly.\n\n",
            "banned": "TTS / 任何生成声音（edge-tts 干声方案已废弃）",
        },
        "subtitles": {
            "policy": "0 生成。画面严禁任何字幕/文字（禁字铁律 + OCR 验字门拦截伪字幕），"
                      "字幕后期人工外挂 .srt（不烧入）",
        },
        "i2v": {
            "route": "Ref2VA 参考图（产品任意时段出现均可锁外观），一次直出 768x1344",
            "ref_image": REF_IMG, "ref2va_count": n_prod,
            "claim_tag": "<Picture 1>（prompt 内认领，strict_prompt_tags 校验编号）",
            "fl2va_note": "产品恰在镜头首帧出现时可改 FL2VA 首帧锚定（备选，需 make_first_frame 透视合成）",
        },
    })
    manifest = {"film": film, **film_meta, "shots": shots_out}

    # ── PROMPTS_v2.md
    P = []
    P.append("# H3 生产 Prompt · %s · v2 节奏重排版" % film_meta["film_title"])
    P.append("")
    P.append("> 镜界 = 参考片实测切点（%d 镜 · 变长）；一镜 = 一次生成 = 一条连续 take。" % n_shots)
    P.append("> **成片一律 768×1344，一律 H3 直出，不走精修**（LTX 精修会把伪字幕描清，已严禁）。")
    P.append("> **产品镜（I2V-Ref2VA）%d 镜**：参考图 `%s`，prompt 以 `<Picture 1>` 认领，"
             "SP_REF 锚定块 + STYLE_REF 禁字豁免版；产品出现在任意时段均锁外观。"
             % (n_prod, REF_IMG))
    P.append("> **一次性生成为准**：不设验字门/重抽循环；禁字条款已写死在每镜 prompt（零成本），"
             "伪字幕残余后期人工处理。")
    P.append("> **声音 = 参考片原声**（原声锁音轨，禁 TTS/生成声）：每镜取参考片 [t0,t1] 原声补静音到整窗，"
             "`_audio_orig/<film>/shotNN.wav`，工作流 LoadAudio 指 `orig_audio/<film>/shotNN.wav`。")
    P.append("> **字幕 0 生成**：成片不带任何字幕，后期人工外挂 `.srt`。")
    P.append("> 机读源：`manifest_v2.json`；镜界数据：`_lines_rhythm/%s_shot_lines.json`。" % film)
    P.append("")
    P.append("## 图例")
    P.append("")
    P.append("| 标识 | 含义 |")
    P.append("| --- | --- |")
    P.append("| `I2V·直出768` | 产品镜 · Ref2VA 参考图 · H3 一次生成 768×1344 |")
    P.append("| `T2V·直出768` | 纯文生 · audio-lock · H3 一次生成 768×1344 |")
    P.append("")
    for s in shots_out:
        tag = ("I2V" if s["task_type"] == "ref2va" else "T2V") + "·直出768"
        P.append("---")
        P.append("")
        P.append("### 镜 %02d · `%s` ｜ `%s` ｜ %.2fs / %df ｜ %s" % (
            s["no"], s["file"], tag, s["seconds"], s["frames"], s["segment"]))
        P.append("")
        if s["ref_images"]:
            P.append("**参考图**：`%s`（Ref2VA，`<Picture 1>` 认领）" % s["ref_images"][0])
            P.append("")
        if s["dialogue"]:
            for sp, tx in s["dialogue"]:
                P.append("- `%s` %s" % (sp, tx))
        else:
            P.append("- （无台词 · 插入/空镜，干声用等长静音垫）")
        P.append("")
        P.append("**Prompt**")
        P.append("")
        P.append("```text")
        P.append(s["prompt"])
        P.append("```")
        P.append("")
    prompts_md = "\n".join(P)

    Path(safe(OUT[(film, "manifest")])).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    Path(safe(OUT[(film, "prompts")])).write_text(prompts_md + "\n", encoding="utf-8")

    # 成本（A100 实测 2026-09-17 深夜：T2V 直出热跑实测 611–651s/镜取 640；Ref2VA 直出实测 651s/镜取 650；
    #       批首含权重装卸。取中位估算，另加 OCR 验字 FAIL 重抽余量 ~15%）
    b_t2v = (820 + max(n_t2v - 1, 0) * 640) if n_t2v else 0
    b_i2v = (830 + max(n_prod - 1, 0) * 650) if n_prod else 0
    total = b_t2v + b_i2v
    print("[%s] %d 镜：I2V-Ref2VA %d ｜ T2V %d ｜ 全部直出 768×1344（无精修）" %
          (film, n_shots, n_prod, n_t2v))
    print("       ①T2V 直出批 %.1f h + ②I2V 直出批 %.1f h ≈ %.1f h GPU（一次性生成，无重抽余量）"
          % (b_t2v / 3600, b_i2v / 3600, total / 3600))
    return manifest


if __name__ == "__main__":
    sys.path.insert(0, H3)
    for f in ("film1", "film2"):
        build_film(f)
