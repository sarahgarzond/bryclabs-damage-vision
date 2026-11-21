"""CLIP zero-shot baseline: the simplest thing that could work, so the pipeline has to beat it.

For each image, CLIP scores one text prompt per damage type plus "no damage" prompts.
Damage types above a threshold become findings. CLIP gives no boxes, no component, no material:
those fields stay unknown, every finding is marked inferred and uncertain. Output uses the same
ImageResult schema, so evaluate.py scores it exactly like the pipeline.

  python scripts/baseline_clip.py --images data/images --out outputs/baseline_clip
"""
import argparse
import json
import time
from pathlib import Path

import _path  # noqa: F401
from damagevision.pipeline import load_image
from damagevision.schema import ImageResult, RunMeta

PROMPTS = {
    "crack": "a photo of a crack in a wall or ceiling",
    "water_stain": "a photo of a water stain on a ceiling or wall",
    "mould": "a photo of black mould on a wall",
    "flaking_paint": "a photo of peeling or flaking paint",
    "plaster_loss": "a photo of missing or crumbling plaster",
    "hole": "a photo of a hole in a wall",
    "rot": "a photo of rotten wood",
    "rust": "a photo of rusted metal",
    "scorch": "a photo of fire or soot damage",
    "broken_glass": "a photo of a broken window",
}
NEGATIVE = ["a photo of a clean undamaged wall", "a photo of an undamaged room", "a photo that does not show a building"]
EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def classify_fn(model_id):
    from transformers import pipeline

    try:
        import torch
        device = 0 if torch.cuda.is_available() else -1
    except ImportError:
        device = -1
    pipe = pipeline("zero-shot-image-classification", model=model_id, device=device)
    labels = list(PROMPTS.values()) + NEGATIVE

    def run(img):
        return {d["label"]: float(d["score"]) for d in pipe(img, candidate_labels=labels)}
    return run


def to_result(image_id, img, scores, threshold, model_id, runtime):
    neg = max(scores.get(n, 0.0) for n in NEGATIVE)
    not_building = scores.get(NEGATIVE[2], 0.0) > 0.5
    findings = []
    for dtype, prompt in PROMPTS.items():
        s = scores.get(prompt, 0.0)
        if s >= threshold and s > neg * 0.5:
            findings.append({"damage_type": dtype, "component": "unknown", "material": "unknown", "extent": "unknown",
                             "status": "inferred", "uncertain": True, "bbox": None, "confidence": round(s, 3),
                             "notes": "CLIP zero-shot score, no localisation"})
    findings.sort(key=lambda f: -f["confidence"])
    present = "yes" if findings else ("no" if neg >= 0.5 else "unclear")
    res = ImageResult(
        image_id=image_id, width=img.width, height=img.height, damage_present=present, image_quality="good",
        scene="not_a_building" if not_building else "interior", findings=findings,
        limitations=["Baseline: no boxes, component, material or quality assessment"],
        meta=RunMeta(model=model_id, backend="clip-baseline", runs=1, runtime_s=round(runtime, 3)))
    return res.model_dump(mode="json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="openai/clip-vit-base-patch32")
    ap.add_argument("--threshold", type=float, default=0.15)
    a = ap.parse_args()
    run = classify_fn(a.model)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    paths = sorted(p for p in Path(a.images).iterdir() if p.suffix.lower() in EXTS)
    for p in paths:
        img = load_image(p)
        t = time.perf_counter()
        scores = run(img)
        data = to_result(p.stem, img, scores, a.threshold, a.model, time.perf_counter() - t)
        (out / f"{p.stem}.json").write_text(json.dumps(data, indent=2))
        print(p.stem, [f["damage_type"] for f in data["findings"]])


if __name__ == "__main__":
    main()
