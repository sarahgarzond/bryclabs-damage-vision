import sys
from pathlib import Path

from damagevision.evaluation import bootstrap_ci

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from baseline_clip import NEGATIVE, PROMPTS, to_result  # noqa: E402


def test_clip_baseline_output_is_schema_valid(img):
    scores = {p: 0.01 for p in PROMPTS.values()} | {PROMPTS["water_stain"]: 0.6} | {n: 0.05 for n in NEGATIVE}
    r = to_result("x", img, scores, 0.15, "clip", 0.1)
    assert r["damage_present"] == "yes" and r["findings"][0]["damage_type"] == "water_stain"
    assert r["findings"][0]["bbox"] is None and r["findings"][0]["uncertain"] is True


def test_bootstrap_ci_brackets_point_estimate():
    f = lambda t: {"damage_type": t, "component": "wall", "bbox": None}
    golds, preds = {}, {}
    for i in range(30):
        golds[str(i)] = {"damage_present": "yes", "findings": [f("crack")]}
        preds[str(i)] = {"findings": [f("crack")] + ([f("mould")] if i % 3 == 0 else [])}
    ci = bootstrap_ci(preds, golds, n=300)
    lo, hi = ci["precision"]
    assert lo <= 30 / 40 <= hi and ci["recall"] == [1.0, 1.0]
