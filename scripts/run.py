"""Run the extraction pipeline on a folder of images.

Examples:
  python scripts/run.py --images data/images --out outputs/run1 --backend mock --no-verify
  python scripts/run.py --images data/images --out outputs/qwen7b --backend openai --runs 3
  python scripts/run.py --images data/images --out outputs/qwen7b_hf --backend hf --load-4bit
"""
import argparse
import csv
import json
import time
from pathlib import Path

import _path  # noqa: F401
from damagevision.backends import get_backend
from damagevision.pipeline import Pipeline, PipelineConfig
from damagevision.readiness import assess

EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".heic"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--backend", default=None, help="openai | hf | mock (default: $DV_BACKEND or mock)")
    ap.add_argument("--model", default=None)
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--temperature", type=float, default=0.4)
    ap.add_argument("--no-verify", action="store_true")
    ap.add_argument("--no-guided", action="store_true", help="openai backend: disable JSON-schema decoding")
    ap.add_argument("--load-4bit", action="store_true")
    ap.add_argument("--cost-per-hour", type=float, default=None, help="GPU price in USD/h for cost per image")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--skip-existing", action="store_true")
    a = ap.parse_args()

    kwargs = {}
    if a.backend in (None, "openai") and (a.model or a.base_url or a.no_guided):
        kwargs = {k: v for k, v in {"model": a.model, "base_url": a.base_url}.items() if v}
        if a.no_guided:
            kwargs["guided"] = False
    elif a.backend == "hf":
        kwargs = {"model": a.model, "load_4bit": a.load_4bit or None}
    backend = get_backend(a.backend, **kwargs)
    pipe = Pipeline(backend, PipelineConfig(runs=a.runs, temperature=a.temperature, verify=not a.no_verify,
                                            cost_per_hour_usd=a.cost_per_hour))

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    paths = sorted(p for p in Path(a.images).iterdir() if p.suffix.lower() in EXTS)[: a.limit]
    rows, t_all = [], time.perf_counter()
    for k, p in enumerate(paths, 1):
        target = out / f"{p.stem}.json"
        if a.skip_existing and target.exists():
            continue
        res = pipe.run_path(p)
        data = res.model_dump(mode="json")
        data["readiness"] = assess(res)
        target.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        m = res.meta
        rows.append({"image_id": res.image_id, "status": res.status, "findings": len(res.findings),
                     "dropped": len(res.dropped_findings), "runtime_s": m.runtime_s if m else None,
                     "tokens": m.tokens if m else None, "cost_usd": m.est_cost_usd if m else None,
                     "device": m.device if m else None, "errors": " | ".join(m.errors) if m else ""})
        print(f"[{k}/{len(paths)}] {res.image_id}: {res.status}, {len(res.findings)} findings, "
              f"{m.runtime_s if m else '?'} s")

    with open(out / "runtime_log.csv", "w", newline="") as f:
        if rows:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    total = time.perf_counter() - t_all
    summary = {"images": len(rows), "total_s": round(total, 2),
               "s_per_image": round(total / len(rows), 3) if rows else None,
               "backend": backend.name, "model": backend.model, "runs": a.runs,
               "verifier": pipe.verifier.model if pipe.cfg.verify and pipe.verifier else None,
               "errors": sum(r["status"] == "error" for r in rows)}
    (out / "run_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    if backend.name == "mock":
        print("NOTE: mock backend output is fake. Never report it as a result.")


if __name__ == "__main__":
    main()
