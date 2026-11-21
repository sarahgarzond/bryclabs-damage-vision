# Who runs what

Full plan and timeline: see the team Google Doc "BrycLabs Hackathon: Team Plan and Task Split".

## Sarah: model pipeline and compute
```bash
# on the GPU (docs/aws_setup.md), or Colab notebook while waiting for AWS
python scripts/run.py --images data/images --out outputs/qwen7b --backend openai --runs 3 --limit 3
python scripts/run.py --images data/images --out outputs/qwen7b --backend openai --runs 3 --cost-per-hour <price>
```
Then tune `src/damagevision/prompt.py`, check the verifier on real images (`src/damagevision/verifier.py` QUERIES and threshold), deliver `outputs/qwen7b` as pre-labels.

## Olivia: labelling lead
```bash
python scripts/make_images_csv.py --images data/images      # assigns labellers, then fill group/origin/licence
python app/label_app.py --labeller olivia --prelabels outputs/qwen7b
python scripts/merge_gold.py                                # after adjudication
```

## Tugce: evaluation and robustness
```bash
python scripts/agreement.py --a labels/olivia --b labels/tugce --out outputs/eval/main/agreement.json
python scripts/evaluate.py --pred outputs/qwen7b --gold labels/gold --images-csv data/images.csv --out outputs/eval/main
python scripts/calibrate.py --pred outputs/qwen7b --gold labels/gold --out outputs/eval/main
python scripts/robustness.py --images data/images --limit 20 --backend openai --out outputs/eval/main
```
Baselines and the comparison table (shown in the website's info drawer):
```bash
python scripts/baseline_clip.py --images data/images --out outputs/baseline_clip
python scripts/run.py --images data/images --out outputs/qwen_1run --runs 1 --no-verify
python scripts/compare.py --gold labels/gold --out outputs/eval/main/comparison.json \
  --setup "CLIP zero-shot=outputs/baseline_clip" --setup "VLM, 1 run, no checks=outputs/qwen_1run" \
  --setup "Full pipeline=outputs/qwen7b"
python scripts/build_site.py --eval outputs/eval/main      # publishes metrics, CIs and comparison to the site
```
`evaluate.py` now writes 95% bootstrap ranges (`ci95`). Fill `docs/report.md` from these files only.
Develop everything now against mock data: `--backend mock`.

## Eva: website, schema, reproducibility
```bash
DV_BACKEND=mock DV_VERIFY=0 python app/app.py          # UI work without GPU
DV_BACKEND=openai DV_BASE_URL=http://localhost:8000/v1 DV_EVAL_DIR=outputs/eval/main python app/app.py
python scripts/export_schema.py && pytest
```
Schema lives in `src/damagevision/schema.py`. Test the README on a clean machine before submitting.
