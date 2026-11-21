"""Box helpers. Final boxes are pixels [x, y, w, h]."""
from __future__ import annotations

from typing import Optional


def box1000_to_xywh(b: Optional[list[int]], width: int, height: int) -> Optional[list[float]]:
    if not b:
        return None
    x1, y1, x2, y2 = b
    return [round(x1 / 1000 * width, 1), round(y1 / 1000 * height, 1),
            round((x2 - x1) / 1000 * width, 1), round((y2 - y1) / 1000 * height, 1)]


def iou_xywh(a: Optional[list[float]], b: Optional[list[float]]) -> float:
    if not a or not b:
        return 0.0
    ax2, ay2, bx2, by2 = a[0] + a[2], a[1] + a[3], b[0] + b[2], b[1] + b[3]
    iw = max(0.0, min(ax2, bx2) - max(a[0], b[0]))
    ih = max(0.0, min(ay2, by2) - max(a[1], b[1]))
    inter = iw * ih
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


def center_inside(inner: Optional[list[float]], outer: Optional[list[float]]) -> bool:
    if not inner or not outer:
        return False
    cx, cy = inner[0] + inner[2] / 2, inner[1] + inner[3] / 2
    return outer[0] <= cx <= outer[0] + outer[2] and outer[1] <= cy <= outer[1] + outer[3]


def mean_box(boxes: list[list[float]]) -> Optional[list[float]]:
    boxes = [b for b in boxes if b]
    if not boxes:
        return None
    return [round(sum(b[i] for b in boxes) / len(boxes), 1) for i in range(4)]
