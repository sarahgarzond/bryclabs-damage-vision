"""Merge several model runs on one image into one result with agreement scores."""
from __future__ import annotations

from collections import Counter

from .geometry import box1000_to_xywh, iou_xywh, mean_box
from .schema import Finding, ModelFinding, ModelOutput


def _majority(values, default=None):
    values = [v for v in values if v is not None]
    if not values:
        return default
    return Counter(values).most_common(1)[0][0]


def _cluster(run_findings: list[list[tuple[ModelFinding, list | None]]], iou_min: float = 0.2):
    """Group findings across runs: same damage_type and (overlapping boxes or no boxes).

    Each cluster takes at most one finding per run. Returns list of clusters, each a list of
    (run_index, finding, box_xywh).
    """
    clusters: list[list[tuple[int, ModelFinding, list | None]]] = []
    for r, findings in enumerate(run_findings):
        for f, box in findings:
            best, best_score = None, -1.0
            for c in clusters:
                if any(m[0] == r for m in c) or c[0][1].damage_type != f.damage_type:
                    continue
                boxes = [m[2] for m in c if m[2]]
                if box and boxes:
                    score = max(iou_xywh(box, b) for b in boxes)
                    if score < iou_min:
                        continue
                else:
                    score = 0.5 if c[0][1].component == f.component else 0.1
                if score > best_score:
                    best, best_score = c, score
            if best is None:
                clusters.append([(r, f, box)])
            else:
                best.append((r, f, box))
    return clusters


def merge_runs(outputs: list[ModelOutput], width: int, height: int) -> dict:
    """Return dict with image-level fields (majority vote) and merged findings with agreement."""
    n = len(outputs)
    run_findings = [[(f, box1000_to_xywh(f.bbox_1000, width, height)) for f in o.findings] for o in outputs]
    merged: list[Finding] = []
    for c in _cluster(run_findings):
        fs = [m[1] for m in c]
        traits: list[str] = []
        for f in fs:
            for t in f.visible_traits:
                if t not in traits:
                    traits.append(t)
        ages = Counter(a for f in fs for a in set(f.age_indicators))
        merged.append(Finding(
            damage_type=fs[0].damage_type,
            component=_majority([f.component for f in fs]),
            material=_majority([f.material for f in fs]),
            location=_majority([f.location for f in fs]),
            visible_traits=traits[:6],
            extent=_majority([f.extent for f in fs]),
            age_indicators=[a for a, k in ages.items() if k / len(fs) >= 0.5],
            status=_majority([f.status for f in fs]),
            uncertain=any(f.uncertain for f in fs) or len(fs) < n,
            bbox=mean_box([m[2] for m in c]),
            notes=_majority([f.notes for f in fs]),
            agreement=round(len(c) / n, 3),
        ))
    merged.sort(key=lambda f: -(f.agreement or 0))
    limitations: list[str] = []
    for o in outputs:
        for lim in o.limitations:
            if lim not in limitations:
                limitations.append(lim)
    issues = Counter(q for o in outputs for q in set(o.quality_issues))
    return {
        "damage_present": _majority([o.damage_present for o in outputs]),
        "image_quality": _majority([o.image_quality for o in outputs]),
        "quality_issues": [q for q, k in issues.items() if k / n >= 0.5],
        "scene": _majority([o.scene for o in outputs]),
        "findings": merged,
        "limitations": limitations,
    }
