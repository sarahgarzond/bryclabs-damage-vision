"""Score pipeline outputs against gold labels.

  python scripts/evaluate.py --pred outputs/qwen7b --gold labels/gold --images-csv data/images.csv --out outputs/eval/qwen7b
"""
import argparse
import csv
import json
from pathlib import Path

import _path  # noqa: F401
from damagevision.evaluation import evaluate, load_dir


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", required=True)
    ap.add_argument("--gold", required=True)
    ap.add_argument("--images-csv", default=None, help="optional: image_id,group,... for per-group metrics")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    groups = {}
    if a.images_csv and Path(a.images_csv).exists():
        with open(a.images_csv) as f:
            for r in csv.DictReader(f):
                groups[r["image_id"]] = r.get("group", "all")
    res = evaluate(load_dir(a.pred), load_dir(a.gold), groups)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    per_image = res.pop("per_image")
    (out / "metrics.json").write_text(json.dumps(res, indent=2))
    with open(out / "per_image.csv", "w", newline="") as f:
        if per_image:
            w = csv.DictWriter(f, fieldnames=list(per_image[0]))
            w.writeheader()
            w.writerows(per_image)
    worst = sorted(per_image, key=lambda r: -(r["fp"] + r["fn"]))[:10]
    (out / "failure_candidates.json").write_text(json.dumps(worst, indent=2))
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
