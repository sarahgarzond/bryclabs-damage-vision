# Damage Evidence Extractor: short explanation

> Template. Replace every `TODO` with numbers from `outputs/eval/main/` (`metrics.json`, `comparison.json`,
> `agreement.json`, `robustness_summary.json`, `calibration_report.json`, `runtime_log.csv`). Never type a number that
> is not in those files.

## 1. Task and scope
We turn one unannotated property damage photo into structured, machine-readable evidence (JSON, CSV) for the policy check.
We extract what is visible and how sure we are. We do not decide cause, liability or coverage.

## 2. Method and architecture
1. **Extractor:** TODO model name (e.g. Qwen2.5-VL-7B-Instruct), served with vLLM, schema-constrained JSON with a fixed vocabulary.
2. **Self-consistency:** TODO N runs on light photometric variants. Agreement is the share of runs that report a finding.
3. **Verifier:** OWLv2 open-vocabulary detector checks each finding at its box.
4. **Rules:** low agreement and unconfirmed means dropped (kept in `dropped_findings`). Unconfirmed or agreement below 0.67 means `uncertain`.
5. **Confidence:** logistic regression on agreement, verifier score and flags, fitted on gold labels (cross-validated). TODO calibrated yes/no.
6. **Claim readiness:** rule-based summary of established, indicated and missing evidence plus follow-up photo requests.

Schema: `schema/image_result.schema.json`. Diagram: `docs/method.md`.

## 3. Evaluation design (no labels were supplied)
- **Gold set:** TODO 100 images: TODO 60 clear, TODO 25 ambiguous or poor quality, TODO 15 without damage. Written labelling guide (`docs/labelling_guide.md`).
- **Label reliability:** 20 images labelled blind by two people. Cohen's kappa for damage types: TODO. Disagreements adjudicated and logged.
- **Why these metrics:**

| Metric | Risk it measures |
|---|---|
| Precision, unsupported finding rate | Invented findings distort the downstream assessment (the brief's main risk) |
| Recall | Missed damage gives an incomplete claim |
| Hallucination rate on undamaged photos | Direct test of invention |
| Field accuracy (component, material, status, extent) | Each field feeds the policy check |
| Box IoU | Evidence is located where claimed |
| Uncertainty usefulness, calibration | The system knows when it may be wrong |

## 4. Results (documented run on the provided images)

| Setup | Precision | Recall | F1 | Hallucination on clean photos | Mean IoU | s / image |
|---|---|---|---|---|---|---|
| CLIP zero-shot baseline | TODO | TODO | TODO | TODO | n/a (no boxes) | TODO |
| VLM, 1 run, no checks | TODO | TODO | TODO | TODO | TODO | TODO |
| **Full pipeline** | TODO (95% CI TODO to TODO) | TODO (CI) | TODO | TODO (CI) | TODO | TODO |
| Frontier API reference | TODO | TODO | TODO | TODO | TODO | TODO |

95% confidence intervals: percentile bootstrap over images, 1000 resamples (`metrics.json` → `ci95`).

**Uncertainty:** flagged findings are wrong TODO% of the time, unflagged TODO%. Confidence AUROC TODO. Calibration plot: `calibration.png`.

**Robustness** (mean Jaccard of findings vs original): blur TODO, dark TODO, JPEG 20 TODO, crop TODO, rotation TODO, repeated runs TODO.

**Successes:** TODO 3 image ids with one line each. **Failures:** TODO 8 to 10 cases, each with cause and likely fix.

## 5. Efficiency (test conditions)
GPU TODO, precision TODO (bf16 / 4-bit), vLLM TODO version, TODO runs, verifier on. Mean TODO s per image, TODO tokens, about TODO USD per image at TODO USD/h.
Variants: 1 run TODO s, without verifier TODO s.

## 6. Limitations: what our checks cannot establish
- Labels come from non-experts, so kappa (TODO) bounds what accuracy can mean.
- 100 images is a small sample: the confidence intervals above show the spread, and real claim photos may differ from our public images.
- One photo cannot show cause, wetness, depth or hidden damage. These are listed as limitations, never as findings.
- Thin cracks and faint stains are hard for the detector, so unconfirmed findings are flagged, not deleted.
- We evaluate evidence extraction, not claim validity: there is no ground truth for coverage.

## 7. Reproduce
`pip install -r requirements-gpu.txt`, start vLLM (`docs/aws_setup.md`), then
`python scripts/run.py --images data/images --out outputs/final --runs 3` and the evaluation commands in `docs/team_tasks.md`.
