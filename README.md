# bryclabs-damage-vision

Property damage photo in, **verified, structured evidence** out. Built for the BrycLabs challenge at the Campus Founders Hackathon (20 to 22 Nov 2026).

We extract policy-relevant evidence from a photo, check it, say how confident we are and list what is missing. We do not decide coverage. That is the job of the policy check and human review downstream.

## Quick start (no GPU, 2 minutes)

```bash
pip install -r requirements.txt
pytest                                                    # 11 tests
python scripts/export_schema.py                           # writes schema/*.schema.json
python scripts/run.py --images data/images --out outputs/demo --backend mock --no-verify
DV_BACKEND=mock DV_VERIFY=0 python app/app.py             # website on http://localhost:7860
```

The `mock` backend returns fake but valid output. Use it to develop the UI and the evaluation code before the GPU is ready. Its output is marked and must never be reported as a result.

## Real run (GPU)

See [docs/aws_setup.md](docs/aws_setup.md) for the full steps. In short:

```bash
vllm serve Qwen/Qwen2.5-VL-7B-Instruct --max-model-len 16384 --limit-mm-per-prompt '{"image": 1}'
export DV_BACKEND=openai DV_BASE_URL=http://localhost:8000/v1
python scripts/run.py --images data/images --out outputs/qwen7b --runs 3 --cost-per-hour <usd>
```

No AWS yet? Use [notebooks/colab_quickstart.ipynb](notebooks/colab_quickstart.ipynb), which runs the model in 4-bit on a free GPU.

## How it works

1. **Extractor:** Qwen-VL with schema-constrained JSON output (`src/damagevision/backends.py`, `prompt.py`).
2. **Self-consistency:** N runs on light photometric variants, merged into one result. Each finding gets an `agreement` score, the share of runs that found it (`consistency.py`).
3. **Verifier:** OWLv2 or Grounding DINO checks each finding at its claimed box (`verifier.py`).
4. **Rules and confidence:** unsupported findings are dropped but kept in `dropped_findings`, unconfirmed ones are flagged `uncertain`, and confidence comes from a calibrated logistic model (`pipeline.py`).
5. **Claim readiness:** lists what is established, what is only indicated, what is missing, and which follow-up photos to request (`readiness.py`).

Details and design choices are in [docs/method.md](docs/method.md).

## Output schema

`src/damagevision/schema.py` is the contract. Exported versions are in `schema/`:

| File | Used for |
|---|---|
| `model_output.schema.json` | What the model must emit. Boxes are normalised 0..1000 `[x1, y1, x2, y2]` |
| `image_result.schema.json` | Final output per image. Boxes are pixels `[x, y, w, h]`, plus confidence, agreement, verified and meta (runtime, device, tokens, cost, errors) |
| `gold_label.schema.json` | Human labels, with the same field names as the final output |

## Evaluation

Without supplied labels, we build our own gold set. The labelling instructions are in [docs/labelling_guide.md](docs/labelling_guide.md).

| Script | Measures |
|---|---|
| `scripts/evaluate.py` | Finding precision, recall and F1, unsupported finding rate, hallucination on negatives, field accuracy, box IoU, confidence AUROC, runtime, per-group results, failure candidates |
| `scripts/agreement.py` | Cohen's kappa between labellers on the shared blind images |
| `scripts/robustness.py` | Stability under blur, dark, bright, JPEG, crop, rotation, flip, low resolution and repeated runs |
| `scripts/calibrate.py` | Cross-validated reliability curve, and fits the confidence model that the pipeline then uses |

## Repo layout

```
src/damagevision/   schema, prompt, backends, pipeline, verifier, consistency, readiness, evaluation
scripts/            run, evaluate, agreement, robustness, calibrate, make_images_csv, merge_gold, export_schema
app/                app.py (demo website), label_app.py (labelling tool)
docs/               method, labelling guide, AWS setup, team tasks
data/               images (not committed) + images.csv
labels/             per-labeller labels, adjudicated, gold
outputs/            run outputs and evaluation (commit only final/ and eval/)
notebooks/          Colab quickstart
tests/              unit tests with mock backend
```

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `DV_BACKEND` | `mock` | `openai`, `hf` or `mock` |
| `DV_BASE_URL` | `http://localhost:8000/v1` | OpenAI-compatible server (vLLM) |
| `DV_MODEL` | `Qwen/Qwen2.5-VL-7B-Instruct` | Model name |
| `DV_API_KEY` | `EMPTY` | API key for hosted baselines |
| `DV_VERIFIER_MODEL` | `google/owlv2-base-patch16-ensemble` | Detector |
| `DV_RUNS`, `DV_VERIFY`, `DV_EVAL_DIR` | `3`, `1`, `outputs/eval/main` | Website settings |
