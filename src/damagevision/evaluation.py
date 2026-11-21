"""Compare pipeline outputs with gold labels, and labellers with each other.

Matching: per image, predicted findings are matched to gold findings with the same damage_type,
greedily by box IoU (component agreement breaks ties when boxes are missing).
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

from .geometry import iou_xywh


def load_dir(d: str | Path) -> dict[str, dict]:
    out = {}
    for p in sorted(Path(d).glob("*.json")):
        try:
            data = json.loads(p.read_text())
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "image_id" in data:
            out[data["image_id"]] = data
    return out


def match_findings(pred: list[dict], gold: list[dict]) -> tuple[list[tuple[int, int, float]], list[int], list[int]]:
    pairs = []
    for i, p in enumerate(pred):
        for j, g in enumerate(gold):
            if p["damage_type"] != g["damage_type"]:
                continue
            iou = iou_xywh(p.get("bbox"), g.get("bbox"))
            score = iou + (0.3 if p.get("component") == g.get("component") else 0.0) + 0.01
            pairs.append((score, i, j, iou))
    pairs.sort(reverse=True)
    used_p, used_g, matches = set(), set(), []
    for score, i, j, iou in pairs:
        if i in used_p or j in used_g:
            continue
        used_p.add(i)
        used_g.add(j)
        matches.append((i, j, iou))
    return matches, [i for i in range(len(pred)) if i not in used_p], [j for j in range(len(gold)) if j not in used_g]


def _safe(a: float, b: float) -> Optional[float]:
    return round(a / b, 4) if b else None


def auroc(scores: list[float], labels: list[int]) -> Optional[float]:
    pos = [s for s, l in zip(scores, labels) if l]
    neg = [s for s, l in zip(scores, labels) if not l]
    if not pos or not neg:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return round(wins / (len(pos) * len(neg)), 4)


def evaluate(preds: dict[str, dict], golds: dict[str, dict], groups: dict[str, str] | None = None) -> dict:
    groups = groups or {}
    ids = sorted(set(preds) & set(golds))
    tp = fp = fn = 0
    field_hits: dict[str, list[int]] = defaultdict(list)
    image_hits: dict[str, list[int]] = defaultdict(list)
    ious, conf_scores, conf_labels = [], [], []
    unc_tp, unc_fp = [], []
    neg_images = neg_with_pred = 0
    per_image, by_group = [], defaultdict(lambda: Counter())
    errors = 0

    for iid in ids:
        p, g = preds[iid], golds[iid]
        if p.get("status") == "error":
            errors += 1
        for k in ("damage_present", "image_quality", "scene"):
            image_hits[k].append(int(p.get(k) == g.get(k)))
        pf, gf = p.get("findings", []), g.get("findings", [])
        matches, un_p, un_g = match_findings(pf, gf)
        tp += len(matches)
        fp += len(un_p)
        fn += len(un_g)
        for i, j, iou in matches:
            for k in ("component", "material", "status", "extent"):
                field_hits[k].append(int(pf[i].get(k) == gf[j].get(k)))
            if pf[i].get("bbox") and gf[j].get("bbox"):
                ious.append(iou)
            unc_tp.append(int(bool(pf[i].get("uncertain"))))
        for i in un_p:
            unc_fp.append(int(bool(pf[i].get("uncertain"))))
        matched_p = {i for i, _, _ in matches}
        for i, f in enumerate(pf):
            if f.get("confidence") is not None:
                conf_scores.append(float(f["confidence"]))
                conf_labels.append(int(i in matched_p))
        if g.get("damage_present") == "no":
            neg_images += 1
            neg_with_pred += int(len(pf) > 0)
        grp = groups.get(iid, "all")
        by_group[grp].update(tp=len(matches), fp=len(un_p), fn=len(un_g), n=1)
        per_image.append({
            "image_id": iid, "group": grp, "tp": len(matches), "fp": len(un_p), "fn": len(un_g),
            "false_positives": [pf[i]["damage_type"] for i in un_p],
            "missed": [gf[j]["damage_type"] for j in un_g],
            "damage_present": [p.get("damage_present"), g.get("damage_present")],
            "runtime_s": (p.get("meta") or {}).get("runtime_s"),
        })

    precision, recall = _safe(tp, tp + fp), _safe(tp, tp + fn)
    f1 = round(2 * precision * recall / (precision + recall), 4) if precision and recall else None
    runtimes = [r["runtime_s"] for r in per_image if r["runtime_s"] is not None]
    groups_out = {}
    for grp, c in by_group.items():
        pr, rc = _safe(c["tp"], c["tp"] + c["fp"]), _safe(c["tp"], c["tp"] + c["fn"])
        groups_out[grp] = {"images": c["n"], "precision": pr, "recall": rc}

    return {
        "images_evaluated": len(ids),
        "images_missing_prediction": sorted(set(golds) - set(preds)),
        "extraction_errors": errors,
        "findings": {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1},
        "unsupported_finding_rate": _safe(fp, tp + fp),
        "negatives": {"images": neg_images, "with_any_finding": neg_with_pred,
                      "hallucination_rate": _safe(neg_with_pred, neg_images)},
        "image_fields_accuracy": {k: _safe(sum(v), len(v)) for k, v in image_hits.items()},
        "matched_fields_accuracy": {k: _safe(sum(v), len(v)) for k, v in field_hits.items()},
        "boxes": {"pairs": len(ious), "mean_iou": _safe(sum(ious), len(ious)),
                  "iou_ge_0_5": _safe(sum(i >= 0.5 for i in ious), len(ious))},
        "uncertainty": {
            "flagged_share_correct": _safe(sum(unc_tp), len(unc_tp)),
            "flagged_share_wrong": _safe(sum(unc_fp), len(unc_fp)),
            "note": "useful uncertainty flags wrong findings more often than correct ones",
        },
        "confidence_auroc": auroc(conf_scores, conf_labels),
        "runtime_s_per_image": {"mean": _safe(sum(runtimes), len(runtimes)),
                                "max": max(runtimes) if runtimes else None},
        "by_group": groups_out,
        "per_image": per_image,
    }


# --------------------------------------------------------------------------- labeller agreement


def cohen_kappa(a: list, b: list) -> Optional[float]:
    if not a or len(a) != len(b):
        return None
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    if pe == 1:
        return 1.0
    return round((po - pe) / (1 - pe), 4)


def labeller_agreement(a: dict[str, dict], b: dict[str, dict]) -> dict:
    ids = sorted(set(a) & set(b))
    out: dict = {"images": len(ids)}
    for k in ("damage_present", "image_quality", "scene"):
        out[f"kappa_{k}"] = cohen_kappa([a[i].get(k) for i in ids], [b[i].get(k) for i in ids])
    # finding level: presence of each damage type per image (binary), then matched fields
    types = sorted({f["damage_type"] for d in (a, b) for i in ids for f in d[i].get("findings", [])})
    pa, pb = [], []
    for i in ids:
        ta = {f["damage_type"] for f in a[i].get("findings", [])}
        tb = {f["damage_type"] for f in b[i].get("findings", [])}
        for t in types:
            pa.append(t in ta)
            pb.append(t in tb)
    out["kappa_damage_type_presence"] = cohen_kappa(pa, pb)
    fields = defaultdict(lambda: ([], []))
    ious = []
    for i in ids:
        fa, fb = a[i].get("findings", []), b[i].get("findings", [])
        matches, _, _ = match_findings(fa, fb)
        for x, y, iou in matches:
            for k in ("component", "material", "status"):
                fields[k][0].append(fa[x].get(k))
                fields[k][1].append(fb[y].get(k))
            if fa[x].get("bbox") and fb[y].get("bbox"):
                ious.append(iou)
    for k, (xa, xb) in fields.items():
        out[f"kappa_{k}"] = cohen_kappa(xa, xb)
    out["mean_iou"] = _safe(sum(ious), len(ious))
    out["disagreements"] = [
        {"image_id": i,
         "a": sorted(f["damage_type"] for f in a[i].get("findings", [])),
         "b": sorted(f["damage_type"] for f in b[i].get("findings", []))}
        for i in ids
        if sorted(f["damage_type"] for f in a[i].get("findings", [])) != sorted(f["damage_type"] for f in b[i].get("findings", []))
        or a[i].get("damage_present") != b[i].get("damage_present")
    ]
    return out


def set_jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)
