"""Fit a calibrated confidence model on the gold labels.

Features per predicted finding: agreement, verified, verifier_score, uncertain, inferred.
Target: was the finding matched to a gold finding? Writes calibration.json (used by the
pipeline on the next run) and a reliability plot.

Use cross-validation numbers in the report, never the in-sample fit.

  python scripts/calibrate.py --pred outputs/qwen7b --gold labels/gold --out outputs/eval
"""
import argparse
import json
from pathlib import Path

import _path  # noqa: F401
from damagevision.evaluation import load_dir, match_findings

FEATS = ["agreement", "verified", "verifier_score", "uncertain", "inferred"]


def rows(preds, golds):
    X, y, raw = [], [], []
    for iid in sorted(set(preds) & set(golds)):
        pf, gf = preds[iid].get("findings", []), golds[iid].get("findings", [])
        matches, _, _ = match_findings(pf, gf)
        hit = {i for i, _, _ in matches}
        for i, f in enumerate(pf):
            X.append([f.get("agreement") or 0.0, float(bool(f.get("verified"))), f.get("verifier_score") or 0.0,
                      float(bool(f.get("uncertain"))), float(f.get("status") == "inferred")])
            y.append(int(i in hit))
            raw.append(f.get("confidence") or 0.0)
    return X, y, raw


def reliability(probs, y, bins=5):
    out = []
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [i for i, p in enumerate(probs) if lo <= p < hi or (b == bins - 1 and p == 1.0)]
        if idx:
            out.append({"bin": f"{lo:.1f}-{hi:.1f}", "n": len(idx),
                        "mean_pred": round(sum(probs[i] for i in idx) / len(idx), 3),
                        "accuracy": round(sum(y[i] for i in idx) / len(idx), 3)})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", required=True)
    ap.add_argument("--gold", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import brier_score_loss, roc_auc_score
    from sklearn.model_selection import cross_val_predict

    X, y, raw = rows(load_dir(a.pred), load_dir(a.gold))
    if len(set(y)) < 2 or len(y) < 10:
        raise SystemExit(f"need >=10 findings with both correct and wrong ones (got {len(y)})")
    clf = LogisticRegression(max_iter=1000)
    cv = cross_val_predict(clf, X, y, cv=min(5, sum(y), len(y) - sum(y)), method="predict_proba")[:, 1]
    clf.fit(X, y)
    report = {
        "findings": len(y), "correct_share": round(sum(y) / len(y), 3),
        "heuristic": {"auroc": round(roc_auc_score(y, raw), 3), "brier": round(brier_score_loss(y, raw), 3),
                      "reliability": reliability(raw, y)},
        "calibrated_cv": {"auroc": round(roc_auc_score(y, cv), 3), "brier": round(brier_score_loss(y, cv), 3),
                          "reliability": reliability(list(cv), y)},
    }
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "calibration.json").write_text(json.dumps(
        {"intercept": float(clf.intercept_[0]), "coef": dict(zip(FEATS, map(float, clf.coef_[0])))}, indent=2))
    (out / "calibration_report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plt.figure(figsize=(4.5, 4.5))
        plt.plot([0, 1], [0, 1], "--", color="grey", label="perfect")
        for name, rel in [("heuristic", report["heuristic"]["reliability"]),
                          ("calibrated (CV)", report["calibrated_cv"]["reliability"])]:
            plt.plot([r["mean_pred"] for r in rel], [r["accuracy"] for r in rel], "o-", label=name)
        plt.xlabel("Predicted confidence")
        plt.ylabel("Share actually correct")
        plt.title("Confidence calibration")
        plt.legend()
        plt.tight_layout()
        plt.savefig(out / "calibration.png", dpi=160)
    except ImportError:
        pass


if __name__ == "__main__":
    main()
