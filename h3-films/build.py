#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 p1_data / p2_data 构建成可投产的三件套：
   manifest.json   H3 管线直接消费（字段对齐远端 10_run_film.py）
   STORYBOARD.md   人可读分镜表（逐镜：画面要点 + 原文台词）
   SCRIPT.md       配音稿（原文逐字，按段汇总，可直接喂 TTS）

口径：台词 = 参考视频转写原文逐字，画面 = 按原片接触表逐拍重建。
语音不依赖生成模型 —— 由 TTS 合成原文后走 audio-lock 工作流驱动口型。

用法： python3 build.py
"""
import json
import os
import importlib.util

ROOT = os.path.dirname(os.path.abspath(__file__))

SEGS_P1 = [
    ("剧情 A · 假摔测试", 1, 5, "0:00–1:15", "顾董在后门假摔，男面试者与白西装女先后冷漠离去"),
    ("剧情 B · 扶人与分饭", 6, 8, "1:15–2:00", "林晚晴蹲下查看、递出午饭，吃完后进楼帮老人找人"),
    ("剧情 C · 身份揭示", 9, 12, "2:00–2:52", "会议室揭示董事长身份，两位候选人出局，林晚晴人品过关"),
    ("桥 · 进厨房", 13, 13, "2:52–3:06", "顾董命她去食堂厨房现场完整做一次"),
    ("卖货 · 口播带货", 14, 19, "3:06–4:32", "86 秒口播：痛点链 → 承诺 → 排除旧方案 → 五步演示 → 省事/好吃举证 → 价格 → CTA"),
    ("收尾 · 结论", 20, 20, "4:32–4:46", "顾董给出结论：「良心不能没有」"),
]

SEGS_P2 = [
    ("短剧 A · 父子试探", 1, 2, "0:00–0:30", "父亲坐轮椅装残，先问孩子谁能真心待他"),
    ("短剧 A · 相亲嫌弃", 3, 6, "0:30–1:29", "相亲女见轮椅上的孩子后态度骤转，找借口离场"),
    ("铰链 · 进店", 7, 7, "1:29–1:44", "阿姨招呼孩子，孩子说想吃红烧排骨——剧情转广告的铰链"),
    ("卖货 · 口播带货", 8, 14, "1:44–3:28", "104 秒口播：痛点链 → 承诺 → 五步演示 → 省事举证 → 价格 → CTA"),
    ("短剧 B · 反转", 15, 18, "3:28–4:27", "孩子站起来，父亲揭示这是一场试探；相亲女在门口失色"),
    ("收尾 · 结论", 19, 20, "4:27–4:57", "「钱能试出贪心，落魄能试出真心」"),
]


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ── 禁字铁律的终检锚点 ────────────────────────────────────────────────
# 任一锚点缺失 = 这镜会长出乱码字幕 → 拒绝出片。锚点与 p1_data/p2_data 的
# NO_TEXT_CLAUSE、check_no_text.py 的判据三处口径必须一致。
NO_TEXT_ANCHORS = ("no subtitles", "no captions", "no on-screen text",
                   "never imitate or reproduce a subtitle strip")


def with_style(prompt, style, shot_no=None):
    """把风格尾巴追加到最后一个时间切片的末尾，并执行禁字铁律终检。

    H3 只在 prompt 末尾读风格与负向约束（no subtitles / no watermark …），
    漏了它就会生成带烧死字幕的画面，后期没法干净叠图形层。

    ★ 铁律：追加后仍缺任一禁字锚点 → 直接报错拒绝生成，不做静默放行。
    """
    marker = "\n\noverall_soundscape:"
    if marker not in prompt:
        raise SystemExit("✘ 镜%s 的 prompt 没有 overall_soundscape 段，无法追加风格 —— 拒绝生成"
                         % shot_no)
    head, tail = prompt.split(marker, 1)
    lines = head.rstrip().split("\n")
    last = lines[-1].rstrip()
    if "no subtitles" not in last:
        if last.endswith("."):
            last = last[:-1]
        lines[-1] = last + ", " + style + "."
    out = "\n".join(lines) + marker + tail

    low = out.lower()
    missing = [k for k in NO_TEXT_ANCHORS if k not in low]
    if missing:
        raise SystemExit(
            "✘ 禁字铁律未通过 —— 镜%s 的 prompt 缺少 %s\n"
            "  多半是 STYLE / NO_TEXT_CLAUSE 被改动或未被引用。\n"
            "  这镜一旦生成就会长出乱码字幕，因此拒绝出片。" % (shot_no, missing))
    return out


def sec_of(no, segs):
    for label, a, b, span, desc in segs:
        if a <= no <= b:
            return label, span, desc
    return "—", "—", "—"


def build(mod, slug, segs, title_cn):
    d = os.path.join(ROOT, slug)
    os.makedirs(d, exist_ok=True)

    man = dict(mod.FILM)
    shots = []
    for s in mod.SHOTS:
        s2 = dict(s)
        s2["duration"] = man["shot_duration_sec"]
        # 三种禁字口径对应三种图条件路线（都保留终检锚点，见 with_style）：
        #   ref      → STYLE_REF      参考图 Ref2VA：豁免「实物包装必须空白」，仍禁叠加层
        #   anchored → STYLE_ANCHORED 关键帧 FL2VA：同上
        #   else     → STYLE          严格版：画面里任何印刷面都必须空白
        if s.get("ref"):
            style = getattr(mod, "STYLE_REF", mod.STYLE)
        elif s.get("anchored"):
            style = getattr(mod, "STYLE_ANCHORED", mod.STYLE)
        else:
            style = mod.STYLE
        s2["prompt"] = with_style(s["prompt"], style, s["no"])
        # Ref2VA 认领校验：标了 ref=True 就必须真的引用 <Picture 1>，
        # 否则参考图接上了也**不会被点名认领**（节点 strict_prompt_tags=true 会校验编号连续性）。
        if s.get("ref") and "<picture 1>" not in s2["prompt"].lower():
            raise SystemExit(
                "✘ 镜%s 标了 ref=True（走 Ref2VA 参考图），但 prompt 里没有 <Picture 1> 引用。\n"
                "  参考图不会被认领，等于白接。请检查 SP_REF 是否被 _prompt 正确注入。"
                % s["no"])
        shots.append(s2)
    man["shots"] = shots
    with open(os.path.join(d, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=2)

    total = len(shots) * man["shot_duration_sec"]
    n_line = sum(len(s["dialogue"]) for s in shots)
    n_char = sum(len(tx) for s in shots for _, tx in s["dialogue"])

    L = []
    L.append("# 分镜表 · %s" % title_cn)
    L.append("")
    L.append("- 片名：`%s`" % man["film_title"])
    L.append("- 镜数：**%d 镜** × %d 秒 = **%d 秒素材**" % (len(shots), man["shot_duration_sec"], total))
    L.append("- 台词：**%d 句 / %d 字**（参考视频转写原文，逐字照抄）" % (n_line, n_char))
    L.append("- 分辨率：stage1 `%s` → stage2 `%s`（9:16 竖版）" % (
        man["resolution_stage1"], man["resolution_stage2"]))
    L.append("- 生成帧率：`%d fps`（帧数栅格 h3_length `%d` / refined_frames `%d`）" % (
        man["fps"], man["h3_length"], man["refined_frames"]))
    L.append("- 成片帧率：`%d fps`（本地转换，见 `PIPELINE.md` 第 4 步）" % man["target_fps"])
    L.append("- 语音：`audio-lock`（TTS 原文驱动口型）　seed：`%d`" % man["seed"])
    L.append("")
    L.append("## 段落总览")
    L.append("")
    L.append("| 段落 | 镜号 | 原片时间 | 内容 |")
    L.append("| --- | --- | --- | --- |")
    for label, a, b, span, desc in segs:
        L.append("| %s | %d–%d | %s | %s |" % (label, a, b, span, desc))
    L.append("")
    L.append("## 逐镜明细")
    L.append("")
    L.append("| # | 文件 | 景别 | 角色 | 场景 | 原片台词（逐字） | 段落 |")
    L.append("| --- | --- | --- | --- | --- | --- | --- |")
    for s in shots:
        label, _, _ = sec_of(s["no"], segs)
        dlg = "／".join("%s：%s" % (sp, tx) for sp, tx in s["dialogue"]) or "—"
        L.append("| %d | `%s` | %s | %s | %s | %s | %s |" % (
            s["no"], s["file"], s["framing"], s["character"], s.get("scene", "—"),
            dlg.replace("|", "｜"), label))
    L.append("")
    L.append("## 分段明细")
    L.append("")
    for label, a, b, span, desc in segs:
        L.append("### %s（镜 %d–%d · 原片 %s）" % (label, a, b, span))
        L.append("")
        L.append(desc)
        L.append("")
        for s in shots:
            if a <= s["no"] <= b:
                L.append("- **镜 %d** `%s`（%s · %s）" % (
                    s["no"], s["file"], s["framing"], s.get("scene", "")))
                for sp, tx in s["dialogue"]:
                    L.append("  - %s：%s" % (sp, tx))
        L.append("")
    L.append("## 禁字铁律（交付前必查）")
    L.append("")
    L.append("H3 是临摹型生成器，会把源片烧死的字幕当画面元素复刻出来（实测镜3 t≈38s、镜12 t≈173s）。")
    L.append("纯负向 prompt 压不住，因此本片有**两道机器门**，缺一不可：")
    L.append("")
    L.append("1. **生成前 · 终检**：`build.py` 强制校验每镜 prompt 含禁字条款，缺任一锚点直接报错拒绝生成。")
    L.append("2. **生成后 · 检测**：`python3 check_no_text.py --shots _deliver/shots_film1`")
    L.append("   逐镜抽帧 OCR 验字，任何一镜检出「成行文字」即 FAIL。")
    L.append("   **建议 stage1 草稿出来就先查一次** —— 早发现早重跑，省掉一半 GPU。")
    L.append("")
    L.append("验收标准：`check_no_text.py` 退出码为 0 且输出「全部通过」。退出码 1 不得交付。")
    L.append("")
    with open(os.path.join(d, "STORYBOARD.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))

    # 配音稿：原文逐字，按段汇总，可直接喂 TTS
    S = []
    S.append("# 配音稿 · %s" % title_cn)
    S.append("")
    S.append("> **全部台词为参考视频转写原文，逐字照抄，未做任何改写。**")
    S.append("> 合成：Edge TTS（中文）逐句生成 → 按镜拼成 15s 干声 → 走 `stage1_audio_lock` 驱动口型。")
    S.append("")
    for label, a, b, span, desc in segs:
        S.append("## %s（原片 %s）" % (label, span))
        S.append("")
        for s in shots:
            if a <= s["no"] <= b and s["dialogue"]:
                S.append("**镜 %d**" % s["no"])
                S.append("")
                for sp, tx in s["dialogue"]:
                    S.append("- `%s` %s" % (sp, tx))
                S.append("")
    with open(os.path.join(d, "SCRIPT.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(S))

    print("✓ %-22s %d 镜 / %d 秒 / 台词 %d 句 %d 字 -> %s" % (
        slug, len(shots), total, n_line, n_char, d))


if __name__ == "__main__":
    build(load("p1_data"), "film1-office", SEGS_P1, "片 1 · 良心面试 × 食堂红烧")
    build(load("p2_data"), "film2-blinddate", SEGS_P2, "片 2 · 相亲这场 × 一包搞定")
    print("\n三件套：manifest.json / STORYBOARD.md / SCRIPT.md")
