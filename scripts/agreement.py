"""Inter-labeller agreement (Cohen's kappa) on the shared blind images.

  python scripts/agreement.py --a labels/olivia --b labels/tugce --out outputs/eval/agreement_pair1.json
"""
import argparse
import json
from pathlib import Path

import _path  # noqa: F401
from damagevision.evaluation import labeller_agreement, load_dir


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    res = labeller_agreement(load_dir(a.a), load_dir(a.b))
    print(json.dumps(res, indent=2))
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
