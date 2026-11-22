"""Combine pipeline outputs into one CSV (same columns as the website's Download CSV).

  python scripts/export_csv.py --results outputs/final --out outputs/final/results.csv
One row per finding, image fields repeated. Images without findings get one row.
"""
import argparse
import csv
import json
from pathlib import Path

COLS = ["image_id", "damage_present", "image_quality", "quality_issues", "scene", "finding_no", "damage_type", "component",
        "material", "location", "extent", "status", "uncertain", "confidence", "agreement", "verified", "bbox_x", "bbox_y",
        "bbox_w", "bbox_h", "visible_traits", "age_indicators", "notes", "limitations", "missing_information"]


def rows(res):
    j = lambda a: " | ".join(a or [])
    base = {"image_id": res["image_id"], "damage_present": res["damage_present"], "image_quality": res["image_quality"],
            "quality_issues": j(res.get("quality_issues")), "scene": res["scene"], "limitations": j(res.get("limitations")),
            "missing_information": j(res.get("missing_information"))}
    fs = res.get("findings") or []
    if not fs:
        return [base]
    out = []
    for i, f in enumerate(fs, 1):
        b = f.get("bbox") or [None] * 4
        out.append({**base, "finding_no": i, **{k: f.get(k) for k in ("damage_type", "component", "material", "location", "extent",
                    "status", "uncertain", "confidence", "agreement", "verified", "notes")},
                    "bbox_x": b[0], "bbox_y": b[1], "bbox_w": b[2], "bbox_h": b[3],
                    "visible_traits": j(f.get("visible_traits")), "age_indicators": j(f.get("age_indicators"))})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    n = 0
    with open(a.out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for p in sorted(Path(a.results).glob("*.json")):
            try:
                res = json.loads(p.read_text())
            except json.JSONDecodeError:
                continue
            if isinstance(res, dict) and "findings" in res:
                w.writerows(rows(res))
                n += 1
    print(f"wrote {a.out} from {n} images")


if __name__ == "__main__":
    main()
