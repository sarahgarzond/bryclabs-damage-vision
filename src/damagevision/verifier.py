"""Open-vocabulary detector that checks each claimed finding.

Default: OWLv2 via the transformers zero-shot-object-detection pipeline.
Alternative: Grounding DINO (DV_VERIFIER_MODEL=IDEA-Research/grounding-dino-tiny).

A finding counts as verified when the detector finds its damage type with score >= threshold
and (if the model gave a box) the detection overlaps it (IoU >= iou_min or one box contains the
other's centre). The verifier never invents findings, it only confirms or fails to confirm.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from PIL import Image

from .geometry import center_inside, iou_xywh

# Text queries per damage type. Detectors respond better to concrete phrases.
QUERIES: dict[str, list[str]] = {
    "crack": ["a crack in a wall", "a crack"],
    "water_stain": ["a water stain", "a brown stain on a ceiling"],
    "mould": ["black mould", "mold spots"],
    "flaking_paint": ["peeling paint", "flaking paint"],
    "plaster_loss": ["missing plaster", "crumbling plaster"],
    "hole": ["a hole in a wall"],
    "swelling": ["swollen wood", "bulging surface"],
    "rot": ["rotten wood"],
    "rust": ["rust"],
    "scorch": ["burn marks", "soot"],
    "broken_glass": ["broken glass", "cracked window"],
    "detachment": ["detached tiles", "loose cladding"],
    "other": ["damage"],
}


@dataclass
class Verification:
    verified: bool
    score: float
    box: Optional[list[float]] = None


class Verifier:
    def __init__(self, model: str | None = None, threshold: float = 0.15, iou_min: float = 0.1, device=None):
        from transformers import pipeline

        self.model = model or os.getenv("DV_VERIFIER_MODEL", "google/owlv2-base-patch16-ensemble")
        if device is None:
            try:
                import torch

                device = 0 if torch.cuda.is_available() else -1
            except ImportError:
                device = -1
        self.pipe = pipeline("zero-shot-object-detection", model=self.model, device=device)
        self.threshold = threshold
        self.iou_min = iou_min

    def detect(self, img: Image.Image, damage_types: list[str]) -> dict[str, list[tuple[float, list[float]]]]:
        """Run once per image with all needed queries. Returns type -> [(score, xywh box)]."""
        labels, owner = [], []
        for t in sorted(set(damage_types)):
            for q in QUERIES.get(t, ["damage"]):
                labels.append(q)
                owner.append(t)
        if not labels:
            return {}
        dets = self.pipe(img.convert("RGB"), candidate_labels=labels, threshold=0.05)
        out: dict[str, list[tuple[float, list[float]]]] = {t: [] for t in set(damage_types)}
        for d in dets:
            t = owner[labels.index(d["label"])]
            b = d["box"]
            out[t].append((float(d["score"]), [b["xmin"], b["ymin"], b["xmax"] - b["xmin"], b["ymax"] - b["ymin"]]))
        return out

    def check(self, dets: dict, damage_type: str, box_xywh: Optional[list[float]]) -> Verification:
        def located(dbox):
            return (box_xywh is None or iou_xywh(box_xywh, dbox) >= self.iou_min
                    or center_inside(dbox, box_xywh) or center_inside(box_xywh, dbox))

        candidates = [(s, b) for s, b in dets.get(damage_type, []) if located(b)]
        if not candidates:
            return Verification(False, 0.0, None)
        score, dbox = max(candidates, key=lambda c: c[0])
        return Verification(score >= self.threshold, round(score, 3), dbox)
