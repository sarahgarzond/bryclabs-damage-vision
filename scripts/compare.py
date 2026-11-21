"""Score several setups on the same gold labels and write one comparison table.

  python scripts/compare.py --gold labels/gold --out outputs/eval/main/comparison.json \
      --setup "CLIP zero-shot=outputs/baseline_clip" \
      --setup "Qwen-VL, 1 run, no checks=outputs/qwen_1run" \
      --setup "Full pipeline=outputs/qwen7b" \
      --setup "Frontier API=outputs/frontier"
"""
import argparse
import json
from pathlib import Path

import _path  # noqa: F401
from damagevision.evaluation import evaluate, load_dir


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", required=True)
    ap.add_argument("--setup", action="append", required=True, help="'Name=folder', repeat per setup")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    golds = load_dir(a.gold)
    rows = []
    for spec in a.setup:
        name, folder = spec.split("=", 1)
        m = evaluate(load_dir(folder), golds)
        rows.append({
            "setup": name, "images": m["images_evaluated"],
            "precision": m["findings"]["precision"], "recall": m["findings"]["recall"], "f1": m["findings"]["f1"],
            "hallucination_rate": m["negatives"]["hallucination_rate"], "mean_iou": m["boxes"]["mean_iou"],
            "s_per_image": m["runtime_s_per_image"]["mean"], "ci95": m.get("ci95", {}),
        })
        print(f"{name}: P={rows[-1]['precision']} R={rows[-1]['recall']} halluc={rows[-1]['hallucination_rate']}")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps({"gold_images": len(golds), "setups": rows}, indent=2))


if __name__ == "__main__":
    main()
