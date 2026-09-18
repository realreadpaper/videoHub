#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""H3 两阶段管线 · 硬件兼容性自检 —— 换卡/换实例前先跑这个。

为什么需要：MiniMax H3 的两条主力量化路径都不是「显存够就能跑」：
  · UNET  minimax_h3_fl2va_pruned_int8_convrot  → 走 comfy-kitchen 的 convrot/int8 kernel
  · CLIP  qwen3vl_32b_..._nvfp4_awq             → 走 comfy-kitchen 的 NVFP4 layout
而 comfy-kitchen 的 CUDA 后端是**架构门控**的（默认编译 arch：75-real;80-real;89;
90a-real;100f;120f），且预编译 wheel 要求 CUDA Runtime >= 13.0；CUDA 13.0 本身
又移除了 Volta(7.0)。所以「V100 32G 显存比 4090 大」并不构成能跑 —— 是架构世代的
问题，不是容量的问题。

本脚本不占 GPU 算力（只做能力查询），跑完 5 秒出结论。可在任何机器上执行。

用法：
  python3 check_gpu_compat.py                # 本机自检
  python3 check_gpu_compat.py --json         # 机器可读输出（给脚本消费）
  python3 check_gpu_compat.py --quiet        # 只打印结论行

退出码：0 = 可跑（原生） / 2 = 可跑但需换权重 / 3 = 不可行
"""
import argparse
import json
import os
import platform
import shutil
import subprocess
import sys

# ── 架构能力表 ───────────────────────────────────────────────────────────────
# 依据：NVIDIA CUDA 13.0 支持 Turing(7.5)~Grace Blackwell；comfy-kitchen CUDA
# backend 的 SM 门控（SM7.5 int8/int4 kernel、SM8.9 FP8、SM10.0 FP4）。
#   bf16   : 原生 bfloat16（Ampere 8.0 起；Volta/Turing 无）
#   fp8    : E4M3/E5M2 tensor core（Ada 8.9 起；A100 无）
#   fp4    : NVFP4 E2M1（Blackwell 10.0 起）
#   int8tc : INT8 tensor core（Turing 7.5 起；Volta 只有 DP4A）
#   fa2    : FlashAttention-2（Ampere 8.0 起）
#   cuda13 : CUDA 13.x 工具链/库是否覆盖（Volta 及更早被移除）
ARCH = {
    50: ("Maxwell",  dict(bf16=False, fp8=False, fp4=False, int8tc=False, fa2=False, cuda13=False)),
    60: ("Pascal",   dict(bf16=False, fp8=False, fp4=False, int8tc=False, fa2=False, cuda13=False)),
    61: ("Pascal",   dict(bf16=False, fp8=False, fp4=False, int8tc=False, fa2=False, cuda13=False)),
    70: ("Volta",    dict(bf16=False, fp8=False, fp4=False, int8tc=False, fa2=False, cuda13=False)),
    75: ("Turing",   dict(bf16=False, fp8=False, fp4=False, int8tc=True,  fa2=False, cuda13=True)),
    80: ("Ampere",   dict(bf16=True,  fp8=False, fp4=False, int8tc=True,  fa2=True,  cuda13=True)),
    86: ("Ampere",   dict(bf16=True,  fp8=False, fp4=False, int8tc=True,  fa2=True,  cuda13=True)),
    87: ("Ampere",   dict(bf16=True,  fp8=False, fp4=False, int8tc=True,  fa2=True,  cuda13=True)),
    89: ("Ada",      dict(bf16=True,  fp8=True,  fp4=False, int8tc=True,  fa2=True,  cuda13=True)),
    90: ("Hopper",   dict(bf16=True,  fp8=True,  fp4=False, int8tc=True,  fa2=True,  cuda13=True)),
    100: ("Blackwell", dict(bf16=True, fp8=True, fp4=True,  int8tc=True,  fa2=True,  cuda13=True)),
    103: ("Blackwell", dict(bf16=True, fp8=True, fp4=True,  int8tc=True,  fa2=True,  cuda13=True)),
    110: ("Blackwell", dict(bf16=True, fp8=True, fp4=True,  int8tc=True,  fa2=True,  cuda13=True)),
    120: ("Blackwell", dict(bf16=True, fp8=True, fp4=True,  int8tc=True,  fa2=True,  cuda13=True)),
    121: ("Blackwell", dict(bf16=True, fp8=True, fp4=True,  int8tc=True,  fa2=True,  cuda13=True)),
}

# comfy-kitchen 预编译 wheel 的默认 CUDA arch 列表（Linux）
KITCHEN_DEFAULT_ARCHS = [75, 80, 89, 90, 100, 120]

C_OK, C_BAD, C_WARN, C_DIM, C_0 = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


def sh(cmd, timeout=20):
    """跑一条命令，返回 stdout（失败返回 None）。"""
    try:
        p = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True,
                           text=True, timeout=timeout)
        return (p.stdout or "").strip() if p.returncode == 0 else None
    except Exception:
        return None


def probe_gpu():
    """nvidia-smi → (name, cc, vram_gb, driver, n_gpu)"""
    if not shutil.which("nvidia-smi"):
        return None
    out = sh(["nvidia-smi", "--query-gpu=name,compute_cap,memory.total,driver_version",
              "--format=csv,noheader,nounits"])
    if not out:
        return None
    gpus = []
    for line in out.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            continue
        name, cc, vram, drv = parts[0], parts[1], parts[2], parts[3]
        try:
            cc_i = int(round(float(cc) * 10))
        except ValueError:
            cc_i = 0
        try:
            vram_gb = float(vram) / 1024.0
        except ValueError:
            vram_gb = 0.0
        gpus.append({"name": name, "cc": cc_i, "cc_raw": cc,
                     "vram_gb": round(vram_gb, 1), "driver": drv})
    return gpus or None


def probe_python_env():
    """torch / comfy-kitchen 能力探测（不导入就尽量不导入，避免占显存）。"""
    info = {"torch": None, "torch_cuda": None, "torch_archs": None,
            "kitchen": None, "kitchen_backends": None, "kitchen_err": None,
            "device_count": None}
    try:
        import torch  # noqa
        info["torch"] = getattr(torch, "__version__", "?")
        info["torch_cuda"] = getattr(torch.version, "cuda", None)
        try:
            info["device_count"] = torch.cuda.device_count()
        except Exception:
            pass
        try:
            info["torch_archs"] = list(torch.cuda.get_arch_list())
        except Exception:
            pass
    except Exception as e:
        info["torch"] = "未安装（%s）" % type(e).__name__
        return info
    # comfy-kitchen：在 ComfyUI 环境里才是真判据
    try:
        import comfy_kitchen as ck  # noqa
        info["kitchen"] = getattr(ck, "__version__", "已安装")
        try:
            info["kitchen_backends"] = list(ck.list_backends())
        except Exception as e:
            info["kitchen_backends"] = "list_backends 失败: %s" % e
    except Exception as e:
        info["kitchen"] = None
        info["kitchen_err"] = "%s: %s" % (type(e).__name__, e)
    return info


def probe_host():
    mem = None
    try:
        if sys.platform == "darwin":
            mem = int(sh("sysctl -n hw.memsize")) // 1024 ** 3
        else:
            with open("/proc/meminfo") as fh:
                for ln in fh:
                    if ln.startswith("MemTotal"):
                        mem = int(ln.split()[1]) // 1024 ** 2
                        break
    except Exception:
        pass
    disk = None
    try:
        t, u, f = shutil.disk_usage(os.path.expanduser("~"))
        disk = round(f / 1024 ** 3, 1)
    except Exception:
        pass


    return {
        "os": "%s %s" % (platform.system(), platform.release()),
        "py": sys.version.split()[0],
        "mem_gb": mem,
        "free_disk_gb": disk,
        "cpu": platform.processor() or "?",
    }


def evaluate(gpus, env, host):
    """核心判决：逐条检查 H3 的四条权重路径。"""
    R = {"checks": [], "verdict": None, "notes": []}

    def add(item, need, have, ok, note=""):
        R["checks"].append({"item": item, "need": need, "have": have,
                            "ok": ok, "note": note})

    if not gpus:
        R["verdict"] = "不可行"
        R["notes"].append("未检测到 NVIDIA GPU（nvidia-smi 不存在或无输出）。"
                          "H3 的 CUDA kernel 路径全部需要 NVIDIA 卡。")
        return R

    g = gpus[0]
    cc = g["cc"]
    cap = ARCH.get(cc)
    if cap is None:
        # 找最近的已知档位做保守推断
        lower = [k for k in ARCH if k <= cc]
        cap = ARCH[max(lower)] if lower else ARCH[50]
        R["notes"].append("compute capability %.1f 不在已知表内，"
                          "按最接近的 %s 档位保守推断。" % (cc / 10.0, cap[0]))
    arch_name, C = cap

    # 1. 架构是否被 CUDA 13 工具链覆盖（comfy-kitchen wheel 的前置）
    add("CUDA 13 工具链覆盖", "SM ≥ 7.5", "SM %.1f (%s)" % (cc / 10.0, arch_name),
        C["cuda13"], "Volta(7.0) 及更早在 CUDA 13.0 中被移除离线编译与库支持" if not C["cuda13"] else "")

    # 2. comfy-kitchen 默认编译 arch 是否含本卡
    add("comfy-kitchen 默认 arch", "在 %s 内" % KITCHEN_DEFAULT_ARCHS,
        "SM %.1f" % (cc / 10.0), cc in KITCHEN_DEFAULT_ARCHS,
        "不在列表时需从源码用 --cuda-archs 自行编译" if cc not in KITCHEN_DEFAULT_ARCHS else "")

    # 3. UNET 主力权重 int8_convrot（SM7.5 起有 turing_int8 kernel）
    add("UNET int8_convrot", "SM ≥ 7.5", "SM %.1f" % (cc / 10.0), C["int8tc"],
        "Volta 只有 DP4A，无 INT8 tensor core" if not C["int8tc"] else "")

    # 4. CLIP nvfp4_awq
    add("CLIP nvfp4_awq 原生", "SM ≥ 10.0 (Blackwell)", "SM %.1f" % (cc / 10.0), C["fp4"],
        "无原生 FP4，走 comfy-kitchen eager fallback（可跑但无加速）；"
        "建议换 int8_convrot 版文本编码器" if not C["fp4"] else "")

    # 5. FP8 快路
    add("FP8 原生加速", "SM ≥ 8.9 (Ada)", "SM %.1f" % (cc / 10.0), C["fp8"],
        "A100 无 FP8 tensor core；若工作流含 fp8 快路会退化" if not C["fp8"] else "")

    # 6. bf16（LTX-2.5 VAE 是 conv-bf16）
    add("bf16 原生（LTX VAE）", "SM ≥ 8.0 (Ampere)", "SM %.1f" % (cc / 10.0), C["bf16"],
        "Volta/Turing 无原生 bf16，bf16 权重会走模拟，显著变慢" if not C["bf16"] else "")

    # 7. FlashAttention-2
    add("FlashAttention-2", "SM ≥ 8.0", "SM %.1f" % (cc / 10.0), C["fa2"],
        "需回退 xformers / SDPA-math，注意力段变慢" if not C["fa2"] else "")

    # 8. 显存容量（硬项：UNET pruned_int8 21GB 必须能驻留）
    need_vram = 21.0
    vram_ok = g["vram_gb"] >= need_vram
    vram_note = ""
    if not vram_ok:
        vram_note = "低于 21GB，UNET 无法驻留，必须全程强 offload —— 不作为生产卡"
    elif g["vram_gb"] < 32:
        vram_note = "24GB 档：可跑，但需 layer-wise offload（当前 4090 基线即此档，已验证可用）"
    else:
        vram_note = "≥32GB：UNET + VAE 可常驻，offload 需求大减"
    add("显存（UNET 21GB 驻留）", "≥ 24 GB（硬性 ≥ 21）",
        "%.1f GB" % g["vram_gb"], vram_ok, vram_note)

    # 9. 系统内存（CPU offload 中转）
    mem = host.get("mem_gb")
    if mem:
        add("系统内存（offload 中转）", "≥ 64 GB 推荐", "%d GB" % mem, mem >= 64,
            "offload 模式 32GB 偏紧、64GB 顺畅" if mem < 64 else "")

    # 10. comfy-kitchen 实际可用性
    kb = env.get("kitchen_backends")
    add("comfy-kitchen 后端", "cuda 或 triton 可用",
        ("已装 %s → %s" % (env.get("kitchen"), kb)) if env.get("kitchen") else "未安装",
        bool(kb) and ("cuda" in str(kb) or "triton" in str(kb)),
        "" if env.get("kitchen") else "本机未装 comfy-kitchen（非 ComfyUI 环境属正常），以架构表为准")

    # ── 终判：分「硬阻断」（真的跑不了）与「软降级」（能跑但有损失） ──
    hard = []   # (原因, 说明)
    if not C["cuda13"]:
        hard.append(("CUDA 13 不支持此架构",
                     "%s (SM %.1f) 在 CUDA 13.0 中被移除离线编译与库支持；"
                     "comfy-kitchen 预编译 wheel 要求 CUDA Runtime ≥ 13.0。"
                     % (arch_name, cc / 10.0)))
    if not C["int8tc"]:
        hard.append(("无 INT8 tensor core",
                     "UNET 主力权重 int8_convrot 依赖 SM≥7.5 的 int8 kernel，"
                     "本卡只有 DP4A，该路径无法启用。"))
    if not C["bf16"]:
        hard.append(("无原生 bf16",
                     "Stage2 的 LTX-2.5 VAE 是 conv-bf16，本卡需模拟计算，"
                     "且同时缺 FlashAttention-2，速度会低到不可用。"))
    if not vram_ok:
        hard.append(("显存不足", "%.1f GB < 21 GB，UNET 无法驻留。" % g["vram_gb"]))

    soft = []
    if not C["fp4"]:
        soft.append("NVFP4 非原生（走 eager fallback）—— 文本编码器建议换 int8_convrot 版")
    if not C["fp8"]:
        soft.append("无 FP8 原生加速 —— 若工作流含 fp8 快路会退化")

    if hard:
        R["verdict"] = "不可行"
        for r, d in hard:
            R["notes"].append("%s：%s" % (r, d))
        R["notes"].append(
            "**显存再大也解决不了** —— 这是架构世代/CUDA 工具链的问题，不是容量问题。")
    elif soft:
        R["verdict"] = "可跑（有降级）"
        for s in soft:
            R["notes"].append(s)
        R["notes"].append(
            "硬性条件（CUDA 13 覆盖 / INT8 kernel / 原生 bf16 / 显存 ≥21GB）全部通过，"
            "本卡可以作为生产卡；降级项只影响文本编码器加载速度与部分快路。")
        R["notes"].append(
            "注：RTX 4090(SM8.9) 同样无 NVFP4 原生支持，当前 20 镜基线就是在该降级下"
            "跑通的 —— 所以此项不影响出片。")
    else:
        R["verdict"] = "可跑（原生）"
        R["notes"].append("全部路径原生支持，无需改任何权重文件。")

    return R


def _exit_code(verdict):
    return {"可跑（原生）": 0, "可跑（有降级）": 2, "不可行": 3}.get(verdict, 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--quiet", action="store_true", help="只输出结论行")
    a = ap.parse_args()

    gpus = probe_gpu()
    env = probe_python_env()
    host = probe_host()
    R = evaluate(gpus, env, host)
    R["gpu"] = gpus
    R["env"] = env
    R["host"] = host

    if a.json:
        print(json.dumps(R, ensure_ascii=False, indent=2))
        return _exit_code(R["verdict"])

    if not a.quiet:
        print("═" * 78)
        print("  H3 两阶段管线 · 硬件兼容性自检")
        print("═" * 78)
        if gpus:
            for i, g in enumerate(gpus):
                print("  GPU%d: %-28s SM %-4s  %6.1f GB  驱动 %s"
                      % (i, g["name"], g["cc_raw"], g["vram_gb"], g["driver"]))
        else:
            print("  GPU : 未检测到 NVIDIA 设备")
        h = host
        print("  主机: %s | Py %s | 内存 %s | 可用磁盘 %s"
              % (h["os"], h["py"],
                 ("%d GB" % h["mem_gb"]) if h["mem_gb"] else "?", 
                 ("%.0f GB" % h["free_disk_gb"]) if h["free_disk_gb"] else "?"))
        e = env
        print("  环境: torch %s (cu %s) | comfy-kitchen %s"
              % (e.get("torch"), e.get("torch_cuda"),
                 e.get("kitchen") or "未安装"))
        if e.get("torch_archs"):
            print("        torch 已编译 arch: %s" % ",".join(e["torch_archs"][:12]))
        print("─" * 78)

        for c in R["checks"]:
            mark = (C_OK + "✔" + C_0) if c["ok"] else (C_WARN + "!" + C_0)
            print("  %s %-22s 需要 %-24s 实际 %s"
                  % (mark, c["item"], c["need"], c["have"]))
            if c["note"]:
                print("    %s%s%s" % (C_DIM, c["note"], C_0))
        print("─" * 78)

    col = {"可跑（原生）": C_OK, "可跑（有降级）": C_WARN,
           "不可行": C_BAD}[R["verdict"]]
    print("  结论：%s%s%s" % (col, R["verdict"], C_0))
    for n in R["notes"]:
        print("  · %s" % n)

    if R["verdict"] != "不可行" and gpus and not ARCH.get(gpus[0]["cc"], (None, {}))[1].get("fp4"):
        print()
        print("  可选优化（把 CLIP 换成 int8 版，绕开 NVFP4 fallback）：")
        print("    hf download Comfy-Org/MiniMax-H3 \\")
        print("      text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors \\")
        print("      --local-dir ComfyUI/models")
        print("    然后把工作流里 CLIPLoader 的 clip_name 换成该文件，先跑一镜验证。")

    return _exit_code(R["verdict"])


if __name__ == "__main__":
    sys.exit(main())
