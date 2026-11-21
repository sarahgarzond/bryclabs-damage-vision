"""Robustness: how stable is the extraction under image degradations and repeated runs?

For each image: run on the original and on each degraded copy, compare the set of
(damage_type, component) pairs with Jaccard similarity. Also repeat the original k times.

  python scripts/robustness.py --images data/images --limit 20 --backend openai --out outputs/eval/robustness
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

import _path  # noqa: F401
from damagevision.augment import ROBUSTNESS
from damagevision.backends import get_backend
from damagevision.evaluation import set_jaccard
from damagevision.pipeline import Pipeline, PipelineConfig, load_image

EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def key_set(res):
    return {(f.damage_type.value, f.component.value) for f in res.findings}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--backend", default=None)
    ap.add_argument("--runs", type=int, default=1, help="pipeline runs per call (1 = raw model stability)")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()

    pipe = Pipeline(get_backend(a.backend), PipelineConfig(runs=a.runs, verify=a.verify, temperature=0.4))
    paths = sorted(p for p in Path(a.images).iterdir() if p.suffix.lower() in EXTS)[: a.limit]
    scores, presence_flips, rows = defaultdict(list), defaultdict(int), []
    for p in paths:
        img = load_image(p)
        base = pipe.run(img, p.stem)
        base_keys = key_set(base)
        # repeated runs: sampling noise (temperature > 0 from 2nd run inside pipeline)
        for r in range(a.repeats - 1):
            pipe.cfg.temperature = 0.7
            rep = pipe.run(img, p.stem)
            scores["repeat"].append(set_jaccard(base_keys, key_set(rep)))
        pipe.cfg.temperature = 0.4
        for name, fn in ROBUSTNESS.items():
            res = pipe.run(fn(img), f"{p.stem}_{name}")
            j = set_jaccard(base_keys, key_set(res))
            scores[name].append(j)
            flipped = res.damage_present != base.damage_present
            presence_flips[name] += int(flipped)
            rows.append({"image_id": p.stem, "variant": name, "jaccard": round(j, 3),
                         "damage_present": [base.damage_present.value, res.damage_present.value],
                         "uncertain_share": round(sum(f.uncertain for f in res.findings) / max(1, len(res.findings)), 3)})
        print(f"{p.stem}: done")

    summary = {k: {"mean_jaccard": round(sum(v) / len(v), 3), "n": len(v),
                   "damage_present_flips": presence_flips.get(k)} for k, v in scores.items()}
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "robustness_summary.json").write_text(json.dumps(summary, indent=2))
    (out / "robustness_rows.json").write_text(json.dumps(rows, indent=2))
    print(json.dumps(summary, indent=2))
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        names = list(summary)
        plt.figure(figsize=(7, 3.5))
        plt.bar(names, [summary[n]["mean_jaccard"] for n in names], color="#4C78A8")
        plt.ylim(0, 1)
        plt.ylabel("Mean Jaccard vs original")
        plt.title("Stability of extracted findings")
        plt.xticks(rotation=30, ha="right")
        plt.tight_layout()
        plt.savefig(out / "robustness.png", dpi=160)
    except ImportError:
        pass


if __name__ == "__main__":
    main()
