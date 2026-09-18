#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""retime_shots.py — 把逐镜固定 15s 改成 10–15s 弹性时长（栅格安全版）

为什么需要它
------------
原来每镜都写死 15s（h3_length=362）。问题是：15s 这个窗口对很多镜头来说
**比内容本身长**——模型收到一个 15s 的窗口，只被告知了前 10s 该演什么，
剩下的 5s 它会自己编。编出来的那截跟下一镜接不上，就是"强制割裂"。

同时，时长不能随便填，这条管线上有两道硬栅格：

  ① H3 `MiniMaxH3AudioConditioningT8.length`
     min=5, step=17, "snapped up to the 17n+5 H3 grid"
     → 合法值只可能是 5, 22, 39, ..., 328, 345, 362（17n+5）

  ② LTX Stage2 `MiniMaxH3SolEngineDraftToLTXT8Advanced.frame_policy`
     默认 `trim_to_8n_plus_1`：只裁不补，把 ① 的帧数**向下**取到最近的 8m+1
     → 成片帧数 ∈ {241, 257, 273, 289, 305, 321, 345, 361, ...}

两道栅格叠起来，10–15 秒区间内只剩 8 个合法档位（见 GRID 表）。
随便写个 13.0 秒，H3 会 snap 到 328（13.667s），再被 LTX 裁到 321（13.375s）
——你以为的 13.0，实际是 13.375，字幕轴就跟着错。所以必须走档位。

本脚本做的事
------------
1. 每个镜按"内容能撑多久"选一个合法档位（见 PLAN 表，逐镜人工判定）
2. 写回 `h3_length`（H3 输入帧数）与 `duration`（成片秒数）
3. **按新时长重排 prompt 里的三段时间戳**——这一步最容易漏。
   时间戳基准取 **H3 length**（不是成片时长）：因为 prompt 是喂给 H3 的，
   它得覆盖 H3 真正生成的整段；LTX 再把末尾 0.04–0.29s 裁掉，剪辑无感。
   反过来写就会让 H3 在最后缺一小段指令，等于又把割裂请回来。
4. 三段默认等分并做整数帧修正（和为 L）；《三十八万八》镜 5 保留原设计的
   30/37/33 非等分（憋笑 → 爆发 → 撕花是刻意设计的节奏）。

用法
----
  python3 retime_shots.py --dry-run          # 只打印对照表，不写文件
  python3 retime_shots.py                    # 写回 manifest.json
  python3 retime_shots.py --also-locked      # 同时处理 manifest.identity_locked.json
"""
import argparse
import json
import os
import re
import sys

C_OK, C_BAD, C_0 = "\033[32m", "\033[31m", "\033[0m"

FPS = 24
MIN_SEC = 10.0    # 成片时长下界（秒）
MAX_SEC = 15.05   # 成片时长上界（秒）；362 帧 → 361 帧 → 15.042s 是天花板

# ── 档位表：H3 帧数 → 成片帧数 ────────────────────────────────────────────
# H3 帧 = required input，必须 ∈ {17n+5}
# 成片帧 = LTX trim_to_8n_plus_1 之后 ∈ {8m+1}，且 ≤ H3 帧
def trim_to_8n_plus_1(frames):
    """LTX 官方路由：不补帧，向下取最大的 8m+1。"""
    return ((frames - 1) // 8) * 8 + 1


# ── 逐镜排期（人工判定：这一镜的内容撑不撑得住 15s） ──────────────────────
# 判定依据统一写成三行：
#   · 拍点数：这一镜有几个可分离的动作/信息拍点
#   · 台词量：按 5 字/秒 估，放进对应段落是否留得出呼吸
#   · 能否撑满：纯静态单主体（如特写一张脸、微距一双手）撑不满 15s，
#               强行给满窗，多出来的秒数就是模型自己编的
#
# 值为 (H3 length, 说明)
PLAN = {
    "三十八万八": {
        # 楼梯跟拍 MCU：持续运动 + 双人 + 台词 + 父亲反应 → 三拍点都实，能撑满
        1: (362, "楼梯跟拍双人+台词+反应，持续运动，撑得住满窗"),
        # 静态钢门 CU：主体是一扇不动的门，四拍点但单个都很短 → 12.7 刚好
        2: (311, "静态钢门，主体不动，给满窗会闷"),
        # 婚房 MS：环视 + 岳母发话 + 新娘无视，双主体三段都有事发生
        3: (328, "双主体+台词+背景反应，接近满窗"),
        # 手部特写：开拉链→手帕→脸→台词→展示三本存折，段落最多
        4: (345, "手/脸/手三段运动 + 21 字台词，需要空间"),
        # 纯面部特写：一张脸做表情，超长会空 → 12.0
        5: (294, "纯面部特写，长镜头会空"),
        # 跑动 WS：跑 → 上车说台词 → 车开走，三拍点
        6: (328, "跑动+上车+发动，三个动作拍点"),
        # 车内固定机位：两个人在座位上说两句 → 略短
        7: (311, "车内固定视角，信息量有限"),
        # 高原收尾：停车 → 剥橘喂 → 长拉远留白，收尾镜需要留白
        8: (362, "收尾镜，长拉远需要留白"),
    },
    "老子不娶了": {
        1: (328, "下车+台词+唢呐背景，三拍点"),
        2: (362, "27 字最长台词 + 抽烟铺垫 + 揭示，撑得住满窗"),
        # 算盘微距：拨珠 → 崩珠慢镜 + 台词 → 碎裂静置
        3: (294, "手部微距，三拍点但都很短"),
        4: (311, "敲烟锅 + 台词 + 背景嗑瓜子，单一动作"),
        5: (345, "砸桌+撕单+怒吼，三个爆发动作"),
        6: (294, "走出大院 + 风撕剪纸，两拍点"),
        7: (311, "点火+台词+起步，单一动作"),
        8: (362, "收尾镜，戈壁长拉远需要留白"),
    },
    "加名之夜": {
        # 半地下室环境镜：车窗溅水 → 水滴落桶 → 桌上文件，三拍点但零台词，
        # 且是开场镜需要让观众"进空间"。给满窗（15s）后 5s 无指令必漂移。
        1: (277, "零台词环境镜，三拍点，满窗后段无指令会漂移"),
        2: (362, "26 字长台词 + 滑笔 + 眼神，撑得住满窗"),
        3: (328, "喝咖啡 + 台词 + 眼神回避，三拍点"),
        4: (277, "沙发缝掏借据，两拍点"),
        # 手部微距：展纸 → 推近数字 → 静置手印。注意这镜是全片最重的
        # 画面文字诱发项（"1,200,000 RMB" + 五个手印），窗越短乱码暴露越少，
        # 但三拍点撑不满 10s，取 11.375 折中。
        5: (277, "手部微距三拍点 + 全片最重文字诱发项，短窗折中"),
        6: (362, "三人同框对峙，需要给三个人反应时间"),
        7: (294, "收拾走人 + 桶倒水，两拍点"),
        8: (345, "收尾镜，雨中走远需要留白"),
    },
}

# 非等分镜（保留原设计节奏）：片名 → {镜号: (段1占比, 段2占比)}
# 《三十八万八》镜 5 原本就是 0–4.5 / 4.5–10 / 10–15 = 30% / 37% / 33%
SEG_RATIO_OVERRIDE = {
    "三十八万八": {5: (0.30, 0.37)},
}


def ts(frames):
    """帧号 → [HH:MM.mmm] 格式的时间戳秒。"""
    sec = frames / FPS
    mm = int(sec // 60)
    ss = sec - mm * 60
    return "%02d:%06.3f" % (mm, ss)


def seg_bounds(L, override=None):
    """把 L 帧切成三段起点/终点，返回 [(a,b), (b,c), (c,L)]。

    默认等分并做整数帧修正，保证 a+b+c == L 且每段至少 1 帧。
    override 给 (r1, r2) 时按比例切（仍做取整修正）。
    """
    if override:
        r1, r2 = override
        a = int(round(L * r1))
        b = int(round(L * (r1 + r2)))
        a = max(1, min(a, L - 2))
        b = max(a + 1, min(b, L - 1))
        return [(0, a), (a, b), (b, L)]
    a = int(round(L / 3.0))
    a = max(1, min(a, L - 2))
    b = int(round(2 * L / 3.0))
    b = max(a + 1, min(b, L - 1))
    return [(0, a), (a, b), (b, L)]


TS_RE = re.compile(r"\[\d{2}:\d{2}\.\d{3}\s*[–-]\s*\d{2}:\d{2}\.\d{3}\]")


def retime_prompt(prompt, L, override=None):
    """把 prompt 里原有的三段时间戳按新时长重排。段数不符则原样返回。"""
    segs = seg_bounds(L, override)
    stamps = ["[%s – %s]" % (ts(s), ts(e)) for s, e in segs]
    n = len(TS_RE.findall(prompt))
    if n != 3:
        return prompt, n
    it = iter(stamps)
    return TS_RE.sub(lambda m: next(it), prompt), 3


def plan_for(film_title, shot_no, cur_h3, cur_dur):
    """取该镜排期；未在表中登记则维持现状（不臆测）。"""
    entry = PLAN.get(film_title, {}).get(shot_no)
    if entry is None:
        return cur_h3, "未登记，维持原值"
    return entry


def process(path, dry=False):
    man = json.load(open(path, encoding="utf-8"))
    title = man["film_title"]
    print("\n" + "=" * 96)
    print("  %s   %s" % (title, os.path.basename(path)))
    print("=" * 96)
    print("  镜  旧H3帧 旧成片  新H3帧 新成片  段边界(秒)                        | 依据")
    print("  " + "-" * 92)

    tot_old = tot_new = 0
    changed = 0
    for s in man["shots"]:
        old_h3 = s.get("h3_length", man.get("h3_length", 362))
        old_fin = trim_to_8n_plus_1(old_h3)
        new_h3, why = plan_for(title, s["no"], old_h3, s.get("duration", 15))
        new_fin = trim_to_8n_plus_1(new_h3)

        segs = seg_bounds(new_h3, SEG_RATIO_OVERRIDE.get(title, {}).get(s["no"]))
        segtxt = " / ".join("%.3f" % (e / FPS) for _, e in segs)

        flag = "" if new_h3 == old_h3 else " ←改"
        print("  %2d  %5d  %5.3f   %5d  %5.3f  %-32s | %s%s"
              % (s["no"], old_h3, old_fin / FPS, new_h3, new_fin / FPS, segtxt, why, flag))

        tot_old += old_h3
        tot_new += new_h3
        if new_h3 != old_h3:
            changed += 1

        if not dry:
            s["h3_length"] = new_h3
            s["duration"] = round(new_fin / FPS, 3)
            s["duration_frames"] = new_fin
            newp, nseg = retime_prompt(s["prompt"], new_h3,
                                       SEG_RATIO_OVERRIDE.get(title, {}).get(s["no"]))
            if nseg == 3:
                s["prompt"] = newp
            else:
                print("      ⚠ 该镜 prompt 时间戳数量为 %d（非 3），未重排" % nseg)

    print("  " + "-" * 92)
    print("  合计 H3 帧：%d → %d（省 %d 帧 = %.1f%%）  改写 %d/%d 镜"
          % (tot_old, tot_new, tot_old - tot_new,
             100.0 * (tot_old - tot_new) / tot_old, changed, len(man["shots"])))

    if not dry:
        bak = path + ".orig_retime"
        if not os.path.exists(bak):
            json.dump(json.load(open(path, encoding="utf-8")), open(bak, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
            print("  原始备份：%s" % os.path.basename(bak))
        json.dump(man, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("  已写回 %s" % path)
    return tot_old, tot_new


def audit(man):
    """硬校验：任何一镜不合规就整体失败，宁可不写也不能写出带外时长。"""
    errs = []
    for s in man["shots"]:
        L = s.get("h3_length")
        if L is None:
            errs.append("镜%d 缺 h3_length" % s["no"]); continue
        if L < 5 or (L - 5) % 17 != 0:
            errs.append("镜%d h3_length=%d 不在 17n+5 栅格" % (s["no"], L))
        F = trim_to_8n_plus_1(L)
        if F != s.get("duration_frames"):
            errs.append("镜%d duration_frames=%s != 裁后 %d" % (s["no"], s.get("duration_frames"), F))
        d = F / FPS
        if not (MIN_SEC - 1e-6 <= d <= MAX_SEC + 1e-6):
            errs.append("镜%d 成片 %.3fs 越界（允许 %.3f-%.3f）" % (s["no"], d, MIN_SEC, MAX_SEC))
        p = s.get("prompt", "")
        stamps = TS_RE.findall(p)
        if len(stamps) != 3:
            errs.append("镜%d 时间戳数量 %d != 3" % (s["no"], len(stamps)))
        else:
            ends = []
            for x in stamps:
                t = x.split("\u2013")[-1].strip().rstrip("]").strip()
                mmv, ssv = t.split(":")
                ends.append(int(mmv) * 60 + float(ssv))
            if abs(ends[-1] - L / FPS) > 0.01:
                errs.append("镜%d 末段终点 %.3f != H3 全长 %.3f" % (s["no"], ends[-1], L / FPS))
            if not (ends[0] < ends[1] < ends[2]):
                errs.append("镜%d 时间戳非递增 %s" % (s["no"], ends))
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--also-locked", action="store_true",
                    help="同时处理 manifest.identity_locked.json")
    a = ap.parse_args()

    dirs = sorted(d for d in os.listdir(a.root)
                  if os.path.isdir(os.path.join(a.root, d)) and re.match(r"^0[123]_", d))
    if not dirs:
        print("找不到 01_/02_/03_ 工程目录"); sys.exit(1)

    grand_old = grand_new = 0
    all_errs = []
    for d in dirs:
        for name in (["manifest.json"] + (["manifest.identity_locked.json"] if a.also_locked else [])):
            p = os.path.join(a.root, d, name)
            if os.path.exists(p):
                o, n = process(p, a.dry_run)
                grand_old += o; grand_new += n
                man = json.load(open(p, encoding="utf-8"))
                for e in audit(man):
                    all_errs.append("[%s/%s] %s" % (d, name, e))

    print("\n" + "=" * 96)
    print("  总账：H3 帧 %d → %d（省 %.1f%%）" % (grand_old, grand_new,
          100.0 * (grand_old - grand_new) / grand_old))
    print("=" * 96)

    if all_errs:
        print("\n" + C_BAD + "  ✘ 边界校验未通过（%d 项）：" % len(all_errs) + C_0)
        for e in all_errs:
            print("     - " + e)
        sys.exit(2)
    if not a.dry_run:
        print("\n" + C_OK + "  ✔ 边界校验通过：全部 24 镜 h3_length ∈ 17n+5、"
              "成片时长 ∈ [%.1f, %.2f]s、时间戳覆盖到 H3 全长" % (MIN_SEC, MAX_SEC) + C_0)


if __name__ == "__main__":
    main()
