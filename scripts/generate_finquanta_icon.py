"""One-shot: build desktop/resources/finquanta.ico (requires PyQt6)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QColor,
    QFont,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PyQt6.QtWidgets import QApplication


def _draw(size: int) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))

    m = max(2, size // 14)
    inner = QRectF(m, m, size - 2 * m, size - 2 * m)
    r = size * 0.18

    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    g = QLinearGradient(0, 0, float(size), float(size))
    g.setColorAt(0.0, QColor(18, 32, 68))
    g.setColorAt(0.55, QColor(12, 72, 118))
    g.setColorAt(1.0, QColor(8, 110, 108))
    p.setBrush(g)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(inner, r, r)

    # Uptrend spark (cyan)
    p.setPen(QPen(QColor(0, 214, 193), max(2, size // 32), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    pad = size * 0.22
    yb = size - pad
    yt = pad + size * 0.28
    pts = [
        QPointF(pad, yb - size * 0.05),
        QPointF(pad + size * 0.18, yb - size * 0.18),
        QPointF(pad + size * 0.38, yt + size * 0.12),
        QPointF(pad + size * 0.58, yt),
        QPointF(size - pad, yt + size * 0.08),
    ]
    path = QPainterPath(pts[0])
    for q in pts[1:]:
        path.lineTo(q)
    p.drawPath(path)

    # Monogram F
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(245, 248, 255))
    fw = size * 0.42
    fx = (size - fw) / 2 + size * 0.02
    fy = size * 0.18
    bar = size * 0.09
    p.drawRoundedRect(QRectF(fx, fy, bar, size * 0.52), bar * 0.35, bar * 0.35)
    p.drawRoundedRect(QRectF(fx, fy, fw * 0.85, bar), bar * 0.35, bar * 0.35)
    p.drawRoundedRect(QRectF(fx, fy + size * 0.18, fw * 0.62, bar), bar * 0.35, bar * 0.35)

    p.end()
    return img


def main() -> None:
    _ = QApplication([])
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = os.path.join(root, "desktop", "resources")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "finquanta.ico")
    img = _draw(256)
    if not img.save(out, "ICO"):
        raise SystemExit(f"failed to write {out}")
    print(out)


if __name__ == "__main__":
    main()
