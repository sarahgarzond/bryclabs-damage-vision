# Data

- `images/`: put the images here as `img_001.jpg` ... (not committed: share them via the team drive).
- `images.csv`: one row per image. Created by `python scripts/make_images_csv.py`, then filled in by hand:
  `group` (clear / ambiguous / negative), `origin` (provided / public), `source_url`, `licence`.
  `labellers`, `mode` and `boxed` are assigned by the script.

Never put the gold test images into any training or prompt-tuning set.
