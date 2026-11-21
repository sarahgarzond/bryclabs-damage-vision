## Method

**Task.** Turn one unannotated property damage photo into structured, machine-readable evidence that a policy check can use. We extract evidence and its uncertainty. We do not decide coverage.

### Pipeline

```
photo ──► vision-language model (Qwen-VL, schema-constrained JSON) × N runs on light photometric variants
                │
                ▼
      merge runs: cluster findings by type + box overlap ─► agreement = share of runs that found it
                │
                ▼
      open-vocabulary detector (OWLv2 / Grounding DINO) checks each claimed finding at its box
                │
                ▼
      rules: low agreement + not confirmed ─► dropped (kept in dropped_findings)
             not confirmed or agreement < 0.67 ─► uncertain = true
      confidence = calibrated logistic model (fallback heuristic: 0.6 agreement + 0.4 verifier)
                │
                ▼
      final JSON (schema/image_result.schema.json) + claim readiness summary
```

### Why this design
- **Schema-constrained decoding** (vLLM `response_format: json_schema`): the model cannot emit invalid JSON or values outside the vocabulary. Remaining failures are retried and reported as `status: "error"`, never silently dropped.
- **Invented features** are the main risk named in the brief. Two independent checks address it: self-consistency across runs and a separate detector.
- **Status and uncertainty are separate**: `status` says where evidence comes from (visible, inferred, not assessable), `uncertain` and `confidence` say how sure we are.
- **Claimant text is not given to the model**, so the extraction reflects the photo only. It is used afterwards for a transparent keyword consistency check.

### Evaluation (no labels supplied)
- 100 hand-labelled images (60 clear, 25 ambiguous, 15 negatives), labelling guide in `docs/labelling_guide.md`.
- Label reliability: Cohen's kappa on 20 images labelled blind by two people.
- Finding precision, recall, unsupported finding rate, hallucination rate on negatives, field accuracy, box IoU.
- Robustness: blur, dark, bright, JPEG 20, crop, rotation, flip, low resolution, repeated runs (Jaccard vs original).
- Calibration: cross-validated reliability curve and AUROC of confidence.
- Baselines: CLIP zero-shot, off-the-shelf model without verification, frontier API model.

### Limitations
- One photo cannot show cause, wetness, depth or hidden damage. These go to `limitations`.
- Gold labels come from non-experts, so kappa is the ceiling for meaningful accuracy.
- Public images used to reach 100 may differ from real claim photos.
- Detector confirmation is weak for thin cracks, so unconfirmed findings are flagged, not deleted.
