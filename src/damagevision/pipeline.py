"""End-to-end extraction for one image: N runs -> merge -> verify -> confidence -> ImageResult."""
from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from PIL import Image, ImageOps

from .augment import photometric_variants
from .backends import Backend
from .consistency import merge_runs
from .schema import DamagePresent, Finding, ImageQuality, ImageResult, RunMeta, Scene


@dataclass
class PipelineConfig:
    runs: int = 3
    temperature: float = 0.4          # first run is always greedy (0.0), later runs sample
    verify: bool = True
    keep_min_agreement: float = 0.34  # below this AND unverified -> dropped (kept in dropped_findings)
    confident_agreement: float = 0.67
    cost_per_hour_usd: Optional[float] = None
    calibration_path: Optional[str] = "outputs/eval/calibration.json"
    extra: dict = field(default_factory=dict)


def _device_name() -> Optional[str]:
    try:
        import torch

        if torch.cuda.is_available():
            return torch.cuda.get_device_name(0)
    except ImportError:
        pass
    return None


def load_calibration(path: Optional[str]) -> Optional[dict]:
    if path and os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


def confidence_score(f: Finding, verify_on: bool, calib: Optional[dict]) -> float:
    """Heuristic until calibrated: 0.6 * agreement + 0.4 * verifier evidence, minus uncertainty.

    scripts/calibrate.py fits a logistic regression on gold labels and writes coefficients that
    replace the heuristic.
    """
    feats = {
        "agreement": f.agreement or 0.0,
        "verified": 1.0 if f.verified else 0.0,
        "verifier_score": f.verifier_score or 0.0,
        "uncertain": 1.0 if f.uncertain else 0.0,
        "inferred": 1.0 if f.status.value == "inferred" else 0.0,
    }
    if calib:
        z = calib["intercept"] + sum(calib["coef"].get(k, 0.0) * v for k, v in feats.items())
        return round(1 / (1 + math.exp(-z)), 3)
    ver = (0.5 * feats["verified"] + 0.5 * min(1.0, feats["verifier_score"] * 2)) if verify_on else feats["agreement"]
    s = 0.6 * feats["agreement"] + 0.4 * ver - 0.1 * feats["uncertain"] - 0.05 * feats["inferred"]
    return round(max(0.0, min(1.0, s)), 3)


def load_image(path: str | Path) -> Image.Image:
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)  # phone photos: respect orientation
    return img.convert("RGB")


def error_result(image_id: str, msg: str, meta: Optional[RunMeta] = None) -> ImageResult:
    return ImageResult(
        image_id=image_id, damage_present=DamagePresent.unclear, image_quality=ImageQuality.poor,
        scene=Scene.interior, findings=[], limitations=[f"Extraction failed: {msg}"], meta=meta, status="error")


class Pipeline:
    def __init__(self, backend: Backend, config: PipelineConfig | None = None, verifier=None):
        self.backend = backend
        self.cfg = config or PipelineConfig()
        self.verifier = verifier
        if self.cfg.verify and self.verifier is None:
            try:
                from .verifier import Verifier

                self.verifier = Verifier()
            except Exception as e:  # transformers/torch missing or download blocked
                print(f"[pipeline] verifier disabled: {e}")
                self.cfg.verify = False
        self.calib = load_calibration(self.cfg.calibration_path)

    def run(self, img: Image.Image, image_id: str) -> ImageResult:
        t0 = time.perf_counter()
        w, h = img.size
        outputs, per_run, errors, tokens = [], [], [], 0
        for i, (vname, vimg) in enumerate(photometric_variants(img, self.cfg.runs)):
            t = time.perf_counter()
            gen = self.backend.generate_validated(vimg, temperature=0.0 if i == 0 else self.cfg.temperature, seed=i)
            per_run.append(round(time.perf_counter() - t, 3))
            if gen.output is None:
                errors.append(f"run {i} ({vname}): {gen.error}")
            else:
                outputs.append(gen.output)
            tokens += gen.tokens or 0

        meta = RunMeta(model=self.backend.model, backend=self.backend.name, runs=self.cfg.runs,
                       runtime_s=0.0, seconds_per_run=per_run, device=_device_name(),
                       tokens=tokens or None, errors=errors, calibrated=self.calib is not None)
        if not outputs:
            meta.runtime_s = round(time.perf_counter() - t0, 3)
            return error_result(image_id, "; ".join(errors) or "no valid output", meta)

        merged = merge_runs(outputs, w, h)
        findings: list[Finding] = merged.pop("findings")

        if self.cfg.verify and self.verifier is not None and findings:
            tv = time.perf_counter()
            try:
                dets = self.verifier.detect(img, [f.damage_type.value for f in findings])
                for f in findings:
                    v = self.verifier.check(dets, f.damage_type.value, f.bbox)
                    f.verified, f.verifier_score = v.verified, v.score
                meta.verifier = self.verifier.model
            except Exception as e:
                errors.append(f"verifier: {type(e).__name__}: {e}")
            meta.verifier_s = round(time.perf_counter() - tv, 3)

        kept, dropped = [], []
        verify_on = meta.verifier is not None
        for f in findings:
            unsupported = (f.agreement or 0) < self.cfg.keep_min_agreement and not (verify_on and f.verified)
            if unsupported and self.cfg.runs > 1:
                dropped.append(f)
                continue
            if (f.agreement or 0) < self.cfg.confident_agreement or (verify_on and not f.verified):
                f.uncertain = True
            f.confidence = confidence_score(f, verify_on, self.calib)
            kept.append(f)

        if not kept and merged["damage_present"] == DamagePresent.yes:
            merged["damage_present"] = DamagePresent.unclear
            merged["limitations"].append("Reported damage could not be confirmed consistently")

        meta.runtime_s = round(time.perf_counter() - t0, 3)
        if self.cfg.cost_per_hour_usd:
            meta.est_cost_usd = round(self.cfg.cost_per_hour_usd * meta.runtime_s / 3600, 6)
        return ImageResult(image_id=image_id, width=w, height=h, findings=kept, dropped_findings=dropped,
                           meta=meta, **merged)

    def run_path(self, path: str | Path) -> ImageResult:
        image_id = Path(path).stem
        try:
            img = load_image(path)
        except Exception as e:
            return error_result(image_id, f"cannot open image: {e}")
        return self.run(img, image_id)
