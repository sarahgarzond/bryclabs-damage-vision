from damagevision.evaluation import cohen_kappa, evaluate, labeller_agreement


def f(t, comp="wall", box=None, **kw):
    return {"damage_type": t, "component": comp, "material": "unknown", "status": "visible",
            "uncertain": False, "extent": "small", "bbox": box, **kw}


def img(iid, present, findings):
    return {"image_id": iid, "damage_present": present, "image_quality": "good", "scene": "interior",
            "findings": findings}


def test_evaluate_counts():
    gold = {"a": img("a", "yes", [f("crack", box=[0, 0, 10, 10])]), "n": img("n", "no", [])}
    pred = {"a": img("a", "yes", [f("crack", box=[1, 1, 10, 10], confidence=0.9),
                                   f("mould", confidence=0.2, uncertain=True)]),
            "n": img("n", "no", [f("water_stain", confidence=0.3)])}
    m = evaluate(pred, gold)
    assert m["findings"]["tp"] == 1 and m["findings"]["fp"] == 2 and m["findings"]["fn"] == 0
    assert m["negatives"]["hallucination_rate"] == 1.0
    assert m["confidence_auroc"] == 1.0
    assert m["boxes"]["mean_iou"] > 0.6


def test_kappa():
    assert cohen_kappa(["a", "b", "a", "b"], ["a", "b", "a", "b"]) == 1.0
    assert cohen_kappa(["a", "a", "b", "b"], ["a", "b", "a", "b"]) == 0.0


def test_agreement_lists_disagreements():
    a = {"x": img("x", "yes", [f("crack")])}
    b = {"x": img("x", "yes", [f("mould")])}
    assert labeller_agreement(a, b)["disagreements"][0]["image_id"] == "x"
