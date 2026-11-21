"""Create data/images.csv from a folder, ready for Olivia to fill in group and origin.

Also assigns labellers: 20 shared blind images (two pairs) + the rest split evenly.
  python scripts/make_images_csv.py --images data/images --labellers olivia tugce eva sarah
"""
import argparse
import csv
import random
from pathlib import Path

EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", default="data/images")
    ap.add_argument("--out", default="data/images.csv")
    ap.add_argument("--labellers", nargs=4, default=["olivia", "tugce", "eva", "sarah"])
    ap.add_argument("--shared", type=int, default=20)
    ap.add_argument("--calibration", type=int, default=5)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()

    ids = sorted(p.stem for p in Path(a.images).iterdir() if p.suffix.lower() in EXTS)
    existing = {}
    if Path(a.out).exists():
        with open(a.out) as f:
            existing = {r["image_id"]: r for r in csv.DictReader(f)}
    rng = random.Random(a.seed)
    order = ids[:]
    rng.shuffle(order)
    calib = set(order[: a.calibration])
    shared = order[a.calibration : a.calibration + a.shared]
    rest = order[a.calibration + a.shared :]
    l1, l2, l3, l4 = a.labellers
    assign = {i: ("all (calibration, excluded from test)", "calibration") for i in calib}
    for k, i in enumerate(shared):
        assign[i] = (f"{l1}+{l2}" if k % 2 == 0 else f"{l3}+{l4}", "shared_blind")
    for k, i in enumerate(rest):
        assign[i] = (a.labellers[k % 4], "own_prelabelled")

    fields = ["image_id", "file", "group", "origin", "source_url", "licence", "labellers", "mode", "boxed"]
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        files = {p.stem: p.name for p in Path(a.images).iterdir() if p.suffix.lower() in EXTS}
        for i in ids:
            old = existing.get(i, {})
            lab, mode = assign[i]
            w.writerow({"image_id": i, "file": files[i], "group": old.get("group", ""),
                        "origin": old.get("origin", ""), "source_url": old.get("source_url", ""),
                        "licence": old.get("licence", ""), "labellers": lab, "mode": mode,
                        "boxed": "yes" if mode == "shared_blind" else old.get("boxed", "")})
    print(f"wrote {a.out}: {len(ids)} images, {len(calib)} calibration, {len(shared)} shared, {len(rest)} own")
    print("Fill in: group (clear / ambiguous / negative), origin (provided / public), source_url, licence")


if __name__ == "__main__":
    main()
