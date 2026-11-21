# Labels

- `labels/<name>/`: each labeller's own labels, written by `python app/label_app.py --labeller <name>`.
- `labels/adjudicated/`: agreed labels for the 20 shared blind images after discussion.
- `labels/disagreements.md`: one line per disagreement and why.
- `labels/gold/`: final test set, built by `python scripts/merge_gold.py`. Commit it before comparing any model result.
