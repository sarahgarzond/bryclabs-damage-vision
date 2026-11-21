"""Build labels/gold/ from individual labeller folders.

Own images: copied as is. Shared images: taken from labels/adjudicated/ if present (the agreed
label after discussion), otherwise flagged so nobody forgets to adjudicate.

  python scripts/merge_gold.py --labels labels --out labels/gold
"""
import argparse
import csv
import json
import shutil
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", default="labels")
    ap.add_argument("--images-csv", default="data/images.csv")
    ap.add_argument("--out", default="labels/gold")
    a = ap.parse_args()
    root, out = Path(a.labels), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    with open(a.images_csv) as f:
        meta = {r["image_id"]: r for r in csv.DictReader(f)}
    missing, todo = [], []
    for iid, r in meta.items():
        if r["mode"] == "calibration":
            continue
        if r["mode"] == "shared_blind":
            src = root / "adjudicated" / f"{iid}.json"
            if not src.exists():
                todo.append(iid)
                continue
        else:
            src = root / r["labellers"] / f"{iid}.json"
        if not src.exists():
            missing.append(f"{iid} ({r['labellers']})")
            continue
        shutil.copy(src, out / f"{iid}.json")
    print(f"gold labels: {len(list(out.glob('*.json')))}")
    if todo:
        print(f"NOT ADJUDICATED yet ({len(todo)}): {', '.join(todo)}")
    if missing:
        print(f"MISSING labels ({len(missing)}): {', '.join(missing)}")


if __name__ == "__main__":
    main()
