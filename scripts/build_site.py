"""Copy real results into the static site before publishing.

  python scripts/build_site.py --results outputs/final --images data/images --eval outputs/eval/main --pick img_004 img_017 img_052

- Picked images and their result JSON go to site/examples/ (replacing the illustrative ones
  unless --keep-illustrative). Only use images you are allowed to publish.
- metrics.json, agreement.json, robustness.png and calibration.png go to site/data/.
"""
import argparse
import json
import shutil
from pathlib import Path

SITE = Path(__file__).resolve().parents[1] / "site"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", help="folder with pipeline output JSON")
    ap.add_argument("--images", help="folder with the original images")
    ap.add_argument("--pick", nargs="*", default=[], help="image ids to show as examples (3 to 6 is ideal)")
    ap.add_argument("--titles", nargs="*", default=[], help="optional titles, same order as --pick")
    ap.add_argument("--eval", help="folder written by evaluate.py / calibrate.py / robustness.py")
    ap.add_argument("--keep-illustrative", action="store_true")
    a = ap.parse_args()

    ex_dir = SITE / "examples"
    index_path = ex_dir / "index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else []
    if a.pick and not a.keep_illustrative:
        index = [e for e in index if not e.get("illustrative")]
    for k, iid in enumerate(a.pick):
        res = Path(a.results) / f"{iid}.json"
        imgs = [p for p in Path(a.images).glob(f"{iid}.*")]
        if not res.exists() or not imgs:
            print(f"skip {iid}: missing result or image")
            continue
        shutil.copy(res, ex_dir / res.name)
        shutil.copy(imgs[0], ex_dir / imgs[0].name)
        title = a.titles[k] if k < len(a.titles) else iid
        index = [e for e in index if e["result"] != f"examples/{res.name}"]
        index.append({"title": title, "image": f"examples/{imgs[0].name}", "result": f"examples/{res.name}"})
        print(f"example: {iid}")
    index_path.write_text(json.dumps(index, indent=2))

    if a.eval:
        data = SITE / "data"
        data.mkdir(exist_ok=True)
        for name in ["metrics.json", "agreement.json", "comparison.json", "robustness.png", "calibration.png"]:
            src = Path(a.eval) / name
            if src.exists():
                shutil.copy(src, data / name)
                print(f"data: {name}")


if __name__ == "__main__":
    main()
