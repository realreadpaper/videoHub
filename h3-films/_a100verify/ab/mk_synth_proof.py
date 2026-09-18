#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""产品袋面合成贴图验证：用参考原图像素替换生成出的模糊袋面。

论证点：扩散模型在 9x9 个 latent 格子里画不出汉字，但参考图有 685x956 的真像素。
把参考图按袋面四角做透视变换贴回去，清晰度 = 参考图缩放后的实际像素。
"""
import os
import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


def pouch_mask(bgr):
    b, g, r = [c.astype(np.int16) for c in cv2.split(bgr)]
    m = (((r > 90) & (r - g > 45) & (r - b > 35)).astype(np.uint8)) * 255
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 21))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k, iterations=3)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    if n > 1:
        i = 1 + int(np.argmax(stats[1:, 4]))
        m = ((lab == i) * 255).astype(np.uint8)
    return m


def order_quad(pts):
    p = np.asarray(pts, dtype=np.float32).reshape(-1, 2)
    s = p.sum(1)
    dd = p[:, 0] - p[:, 1]
    return np.array([p[np.argmin(s)], p[np.argmax(dd)],
                     p[np.argmax(s)], p[np.argmin(dd)]], np.float32)


def quad_of(mask):
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    c = max(cnts, key=cv2.contourArea)
    return order_quad(cv2.boxPoints(cv2.minAreaRect(c)))


def color_match(src, dst, mask):
    """把 src 的亮度/色彩分布对齐到 dst 在 mask 内的分布（保均值保对比）。"""
    idx = mask > 127
    out = src.astype(np.float32)
    for c in range(3):
        s = out[..., c][idx]
        d = dst[..., c][idx]
        if s.std() < 1e-3:
            continue
        out[..., c] = (out[..., c] - s.mean()) / s.std() * d.std() + d.mean()
    return np.clip(out, 0, 255).astype(np.uint8)


def main():
    frame = cv2.imread(os.path.join(HERE, "id_t13.0.jpg"))
    ref = cv2.imread(os.path.join(HERE, "prod_P1_front.png"))
    assert frame is not None and ref is not None

    fq = quad_of(pouch_mask(frame))
    print("目标帧袋面四角:\n", fq.astype(int))
    print("目标帧袋面边长: 上 %.0f 下 %.0f 左 %.0f 右 %.0f" % (
        np.linalg.norm(fq[1] - fq[0]), np.linalg.norm(fq[2] - fq[3]),
        np.linalg.norm(fq[3] - fq[0]), np.linalg.norm(fq[2] - fq[1])))

    m_ref = pouch_mask(ref)
    rq = quad_of(m_ref)
    print("参考图袋面四角:\n", rq.astype(int))

    H, W = ref.shape[:2]
    lw = int(np.linalg.norm(rq[3] - rq[0]))
    lh = int(np.linalg.norm(rq[1] - rq[0]))
    print("参考图袋面: %d x %d px（真像素）" % (lw, lh))

    # 参考图 -> 目标帧 的透视变换
    pad = 14
    src_q = rq - np.array([[pad, pad], [-pad, pad], [-pad, -pad], [pad, -pad]], np.float32)
    M = cv2.getPerspectiveTransform(src_q, fq)
    warped = cv2.warpPerspective(ref, M, (frame.shape[1], frame.shape[0]),
                                 flags=cv2.INTER_LANCZOS4)

    # 目标区域的软 mask（稍缩以避开边缘外溢）
    m_dst = np.zeros(frame.shape[:2], np.uint8)
    cv2.fillConvexPoly(m_dst, fq.astype(np.int32), 255)
    m_dst = cv2.erode(m_dst, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    feather = cv2.GaussianBlur(m_dst, (0, 0), 4).astype(np.float32) / 255.0
    feather = np.clip((feather - 0.25) / 0.5, 0, 1)[..., None]

    warped = color_match(warped, frame, m_dst)
    synth = (warped.astype(np.float32) * feather +
             frame.astype(np.float32) * (1 - feather)).astype(np.uint8)

    def label(img, text, color):
        img = img.copy()
        cv2.rectangle(img, (0, 0), (img.shape[1] - 1, 46), (247, 247, 248), -1)
        cv2.putText(img, text, (12, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.82, color, 2, cv2.LINE_AA)
        return img

    x, y, w, h = cv2.boundingRect(m_dst)
    grow = 30
    x0, y0 = max(0, x - grow), max(0, y - grow)
    x1, y1 = min(frame.shape[1], x + w + grow), min(frame.shape[0], y + h + grow)

    def col(img, text, color):
        full = label(img, text, color)
        crop = img[y0:y1, x0:x1]
        ch, cw = crop.shape[:2]
        tw = 470
        crop = cv2.resize(crop, (tw, int(ch * tw / cw)), interpolation=cv2.INTER_LANCZOS4)
        return full, crop

    f1, c1 = col(frame, "BEFORE  S2 精修（生成）", (60, 60, 200))
    f2, c2 = col(synth, "AFTER  参考图合成贴图", (60, 130, 40))

    hh = max(c1.shape[0], c2.shape[0])
    def padh(a):
        return cv2.copyMakeBorder(a, 0, hh - a.shape[0], 0, 0,
                                  cv2.BORDER_CONSTANT, value=(247, 247, 248))
    c1, c2 = padh(c1), padh(c2)

    gap = np.full((hh, 18, 3), 247, np.uint8)
    row_crop = np.hstack([c1, gap, c2])

    # 全帧行
    fy = 470
    def fscale(a):
        return cv2.resize(a, (int(a.shape[1] * fy / a.shape[0]), fy), interpolation=cv2.INTER_AREA)
    f1s, f2s = fscale(f1), fscale(f2)
    row_full = np.hstack([f1s, gap[:fy], f2s])

    out = np.vstack([row_full, np.full((20, row_full.shape[1], 3), 247, np.uint8),
                     row_crop])
    # 底部补参考图缩略
    rw = 300
    rthumb = cv2.resize(ref, (rw, int(ref.shape[0] * rw / ref.shape[1])), interpolation=cv2.INTER_AREA)
    rthumb = label(rthumb, "ORIGINAL 参考原图", (150, 90, 30))
    out = np.vstack([out, np.full((20, out.shape[1], 3), 247, np.uint8)])
    strip = np.full((rthumb.shape[0], out.shape[1], 3), 247, np.uint8)
    strip[:rthumb.shape[0], :rthumb.shape[1]] = rthumb
    out = np.vstack([out, strip])

    p = os.path.join(HERE, "compare_synth_pouch.png")
    cv2.imwrite(p, out, [cv2.IMWRITE_JPEG_QUALITY, 96])
    print("写出", p, out.shape)


main()
