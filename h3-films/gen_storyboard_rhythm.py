#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
由 _lines_rhythm/filmN_shot_lines.json + manifest_v2.json 生成 v2 STORYBOARD.md。
写盘模式（路径为字面量并经 safe() 白名单校验）：
  python3 gen_storyboard_rhythm.py --film film1 --write
"""
import argparse, json, os
from pathlib import Path

ROOT = "/Users/hejianglong/Desktop/videoHub"
H3 = ROOT + "/h3-films"
ALLOWED = os.path.realpath(ROOT)

META = {
    "film1": {
        "dir": "film1-office",
        "ref_stats": "94 镜 · 平均 3.04s · 19.5 切/分（reelbench 实测）",
        "old": "20 镜 × 15s 均分（4.1 切/分）",
    },
    "film2": {
        "dir": "film2-blinddate",
        "ref_stats": "103 镜 · 平均 2.88s · 20.6 切/分（reelbench 实测）",
        "old": "20 镜 × 15s 均分（4.0 切/分）",
    },
}
TAG = {("ref2va", "direct768"): "I2V·直出768", ("t2va", "direct768"): "T2V·直出768",
       ("ref2va", "draft_refine"): "I2V·草稿→精修", ("t2va", "draft_refine"): "T2V·草稿→精修"}


def safe(path):
    rp = os.path.realpath(path)
    if not (rp == ALLOWED or rp.startswith(ALLOWED + os.sep)):
        raise ValueError("path outside workspace: " + path)
    return rp


def main(film):
    cfg = META[film]
    d = json.load(open(safe(H3 + "/_lines_rhythm/" + film + "_shot_lines.json"), encoding="utf-8"))
    mv = json.load(open(safe(H3 + "/" + cfg["dir"] + "/manifest_v2.json"), encoding="utf-8"))
    tag_of = {s["no"]: TAG[(s["task_type"], s["exec_tier"])] for s in mv["shots"]}
    shots = d["shots"]
    n = len(shots)
    cuts_min = (n - 1) / (d["src_duration"] / 60)
    avg = sum(w["seconds"] for w in shots) / n
    parts = sum(len(w["dialogue"]) for w in shots)
    chars = sum(len("".join(ch for ch in t if ch not in "，。？！、：；「」『』（）…—·,.?!:;()\"'“”‘’~% "))
                for w in shots for _, t in w["dialogue"])
    static = sum(1 for w in shots if w["camera"] == "固定机位")
    n_prod = sum(1 for t in tag_of.values() if t.startswith("I2V"))
    n_t2v = n - n_prod
    ref_img = mv["i2v"]["ref_image"]
    # 成本（A100 实测 09-17 深夜：实测口径：T2V 热 640s/镜、I2V 热 650s/镜，批首含权重装卸 ~820s；×1.15 留 OCR 重抽余量）
    b_t2v = (800 + max(n_t2v - 1, 0) * 700) / 3600 if n_t2v else 0
    b_i2v = (850 + max(n_prod - 1, 0) * 700) / 3600 if n_prod else 0
    total_h = b_t2v + b_i2v

    segs = []
    for w in shots:
        if segs and segs[-1][0] == w["segment"]:
            segs[-1][2] = w["no"]
            segs[-1][4] = w["t1"]
        else:
            segs.append([w["segment"], w["no"], w["no"], w["t0"], w["t1"]])

    L = []
    A = L.append
    A("# 分镜表 · %s · 整窗对齐版 v3" % d["title"])
    A("")
    A("> 镜长回到 **10–15.083s**（贴近 362 帧整窗，一次生成质量优先）；镜界**只落在原片实测切点**，"
      "换段处为硬边界（reelbench `video-shots` 实测 + 运动尖峰优选）。")
    A("> 生成模式：一镜一次生成（单条连续 take），单镜上限 **15.083s**（362 帧@24fps）；**成片一律 768×1344**。")
    A("")
    A("- 镜数：**%d 镜 · 镜长 %.1f–%.1fs**（一次生成整窗，贴近 362 帧栅格）" % (
        n, min(w["seconds"] for w in shots), max(w["seconds"] for w in shots)))
    A("- **镜界规则**：%s" % d.get("mode_note", "实测切点对齐"))
    A("- 节奏说明：本表 %.1f 切/分（原片 %s）。快切节奏的还原交给**后期二剪**——镜界已落在原片实测切点上，"
      "每镜整窗素材内可按细切点（`rebreak_shots.py --min 2.0` 可复现细拆表）再剪" % (cuts_min, cfg["ref_stats"]))
    A("- 台词：**逐字照抄不变**（%d 无标点字符），按新镜界重新切分为 %d 段；中句切断与原片切点一致" % (chars, parts))
    A("- **产品镜（I2V-Ref2VA）%d 镜**：参考图 `%s`，prompt 以 `<Picture 1>` 认领（Ref2VA，产品任意时段"
      "出现均锁外观；首帧出现可改 FL2VA 备选）" % (n_prod, ref_img))
    A("- **成片一律 768×1344，一律 H3 直出、不走精修**（2026-09-17 实测定案：LTX 精修会把 H3 草稿的"
      "伪字幕高清描清，**严禁**）。**T2V 直出 %d 镜 ＋ I2V 产品镜 %d 镜**（Ref2VA 参考图）。"
      "每镜产出必过抽帧 OCR 验字门（`check_no_text.py`），FAIL 换 seed 重抽" % (n_t2v, n_prod))
    A("- 实测运动：**%d 镜固定机位（motion ≤ 1.5）**，逐镜 motion 值见下表（运镜措辞以此为准，防幻觉）" % static)
    A("- 生成帧率 `24 fps`；成片 `30 fps` 本地转换；**语音 = 参考片原声锁音轨**（`_audio_orig/`，禁 TTS/生成声）；"
      "**字幕 0 生成**（后期人工外挂 `.srt`）；seed `%d`" % d["seed"])
    A("- 机读源：`_lines_rhythm/%s_shot_lines.json`（镜界）＋ `%s/manifest_v2.json`（方式/档位/prompt）＋ "
      "`%s/PROMPTS_v2.md`（逐镜 prompt）" % (film, cfg["dir"], cfg["dir"]))
    A("")
    A("## 段落总览")
    A("")
    A("| 段落 | 新镜号 | 原片时间 |")
    A("| --- | --- | --- |")
    for name, a_no, b_no, t0, t1 in segs:
        A("| %s | %d–%d | %s – %s |" % (name, a_no, b_no,
          "%d:%04.1f" % (int(t0 // 60), t0 % 60), "%d:%04.1f" % (int(t1 // 60), t1 % 60)))
    A("")
    A("## 逐镜明细")
    A("")
    A("生成方式标识：`I2V·直出768` = 产品镜·Ref2VA·H3 一次生成 768×1344　"
      "`T2V·直出768` = 纯文生·audio-lock·H3 一次生成 768×1344（无精修路线）")
    A("")
    A("| # | 原片时间 | 秒/帧 | 方式·档位 | 实测motion | 场景 · 角色（承自 v1）| 台词（逐字）|")
    A("| --- | --- | --- | --- | --- | --- | --- |")
    for w in shots:
        dlg = "／".join("%s：%s" % (sp, t) for sp, t in w["dialogue"]) if w["dialogue"] else "（无台词）"
        A("| %d | %.2f–%.2f | %.2f / %df | **%s** | %.1f %s | %s · %s | %s |" % (
            w["no"], w["t0"], w["t1"], w["seconds"], w["frames"], tag_of.get(w["no"], "?"),
            w["motion"], w["camera"], w["scene"], w["base_characters"], dlg.replace("|", "｜")))
    A("")
    A("## 执行注意（v2 相对 v1 的变化）")
    A("")
    A("1. **执行排产（全直出，无精修）**：① T2V 直出批（%d 镜 · fl2va@768 连跑）→ ② I2V 直出批"
      "（%d 镜 · ref2va@768 连跑）。**两批各自连跑、绝不交替**。估算：① %.1f h + ② %.1f h "
      "×1.15（OCR 重抽余量）≈ **%.1f h GPU**（A100 实测口径）。"
      % (n_t2v, n_prod, b_t2v, b_i2v, total_h))
    A("2. **产品镜（I2V·直出768）走 Ref2VA 参考图**：`build_voice_workflow.py --ref-images %s`，"
      "prompt 已带 `<Picture 1>` 认领与 SP_REF 锚定块、禁字条款为实物印刷豁免版（STYLE_REF）。"
      "参考图与工作流投送沿用 `deploy_refs.sh`；先跑 1 镜验证槽位再批量。" % ref_img)
    A("3. **一次性生成**：不设验字门与重抽循环（省时定案）；禁字条款已写死在每镜 prompt，"
      "伪字幕残余后期人工处理（字幕本就人工外挂）。")
    A("4. **帧数栅格**：362 帧（15.083s）是唯一验证过的栅格。Mode A = 每镜整窗生成后裁（现在就能跑，"
      "成本每镜全价）；Mode B = `h3_length` 按镜帧数（成本近似线性降）**需先单镜验证**，验证前不得按此排期。")
    A("5. **声音 = 原声**（2026-09-18 定案）：每镜取参考片 [t0,t1] 原声（对白/环境/配乐）补静音到 15.0833s "
      "整窗，32kHz 立体声 → `_audio_orig/%s/shotNN.wav`（远端 `input/orig_audio/%s/`）。"
      "工作流 LoadAudio 指原声文件；`make_tts.py`/TTS 全链路废弃。" % (film, film))
    A("6. **字幕 0 生成**：画面严禁任何文字（OCR 验字门拦截），成片不带字幕，后期人工外挂 `.srt`。")
    A("6. **无台词镜**：干声用等长静音垫；本表 %d 镜无台词。" % (
        1 if any(not w["dialogue"] for w in shots) else 0))
    A("7. **prompt 已生成**：`%s/PROMPTS_v2.md`（逐镜单段连续 take；运镜措辞跟实测 motion）。"
      "上机前建议人工过一遍 I2V 镜的 beat 细节。" % cfg["dir"])
    A("8. v1 留档：20 镜 × 15s 版数据完整保留于 `manifest.json` 与 `PROMPTS.md`（均未改动）。")
    A("")
    return "\n".join(L)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--film", choices=["film1", "film2"], required=True)
    ap.add_argument("--write", action="store_true", help="写入对应 STORYBOARD.md（路径为字面量）")
    a = ap.parse_args()
    out = main(a.film)
    if a.write:
        from pathlib import Path
        target = ("/Users/hejianglong/Desktop/videoHub/h3-films/film1-office/STORYBOARD.md"
                  if a.film == "film1"
                  else "/Users/hejianglong/Desktop/videoHub/h3-films/film2-blinddate/STORYBOARD.md")
        Path(safe(target)).write_text(out + "\n", encoding="utf-8")
    else:
        print(out)
