"""Labelling app: one image at a time, JSON prefilled from the model (or blank for blind images).

  python app/label_app.py --labeller olivia --prelabels outputs/qwen7b
Saves to labels/<labeller>/<image_id>.json. Images and assignments come from data/images.csv.
Click two corners on the image (top left, then bottom right) to get a bbox to paste in.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import gradio as gr  # noqa: E402
from PIL import Image, ImageOps  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from damagevision.schema import GoldLabel, blank_label, result_to_label  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--labeller", required=True)
ap.add_argument("--images", default=str(ROOT / "data" / "images"))
ap.add_argument("--images-csv", default=str(ROOT / "data" / "images.csv"))
ap.add_argument("--prelabels", default=None, help="folder with model outputs used to prefill own images")
ap.add_argument("--port", type=int, default=7861)
ARGS = ap.parse_args()

OUT = ROOT / "labels" / ARGS.labeller
OUT.mkdir(parents=True, exist_ok=True)


def my_images() -> list[dict]:
    rows = []
    with open(ARGS.images_csv) as f:
        for r in csv.DictReader(f):
            who = r.get("labellers", "")
            if ARGS.labeller in who.split("+") or who == ARGS.labeller or r.get("mode") == "calibration":
                rows.append(r)
    # blind shared images first so model pre-labels cannot anchor judgement
    order = {"calibration": 0, "shared_blind": 1, "own_prelabelled": 2}
    return sorted(rows, key=lambda r: (order.get(r.get("mode"), 3), r["image_id"]))


ROWS = my_images()
GUIDE = (ROOT / "docs" / "labelling_guide.md").read_text() if (ROOT / "docs" / "labelling_guide.md").exists() else ""


def initial_json(r: dict) -> str:
    iid = r["image_id"]
    saved = OUT / f"{iid}.json"
    if saved.exists():
        return saved.read_text()
    if r.get("mode") == "own_prelabelled" and ARGS.prelabels:
        p = Path(ARGS.prelabels) / f"{iid}.json"
        if p.exists():
            return json.dumps(result_to_label(json.loads(p.read_text()), ARGS.labeller), indent=2)
    return json.dumps(blank_label(iid, ARGS.labeller), indent=2)


def show(idx: int):
    idx = max(0, min(idx, len(ROWS) - 1))
    r = ROWS[idx]
    img = ImageOps.exif_transpose(Image.open(Path(ARGS.images) / r["file"])).convert("RGB")
    done = sum((OUT / f"{x['image_id']}.json").exists() for x in ROWS)
    boxed = " · **draw boxes on this image**" if r.get("boxed") == "yes" else ""
    info = (f"**{r['image_id']}** ({idx + 1}/{len(ROWS)}) · mode **{r.get('mode')}**{boxed} · "
            f"size {img.width}×{img.height} · saved {done}/{len(ROWS)}")
    return idx, img, info, initial_json(r), "", ""


def save(idx: int, text: str):
    try:
        data = json.loads(text)
        data["labeller"] = ARGS.labeller
        label = GoldLabel.model_validate(data)
    except json.JSONDecodeError as e:
        return f"❌ Invalid JSON: {e}"
    except ValidationError as e:
        return "❌ Not saved. Fix these fields:\n" + "\n".join(
            f"- {'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors())
    if label.image_id != ROWS[idx]["image_id"]:
        return "❌ image_id does not match the current image"
    (OUT / f"{label.image_id}.json").write_text(label.model_dump_json(indent=2, exclude_none=False))
    return f"✅ Saved {label.image_id}"


def click(evt: gr.SelectData, first: str):
    x, y = evt.index
    if not first:
        return f"{x},{y}", f"Top left at ({x}, {y}). Now click the bottom right corner."
    x0, y0 = map(int, first.split(","))
    box = [min(x0, x), min(y0, y), abs(x - x0), abs(y - y0)]
    return "", f'"bbox": {json.dumps(box)}'


with gr.Blocks(title=f"Labelling: {ARGS.labeller}") as demo:
    idx = gr.State(0)
    first_click = gr.State("")
    info = gr.Markdown()
    with gr.Row():
        with gr.Column(scale=3):
            img = gr.Image(type="pil", interactive=False, label="Click two corners for a bbox")
            bbox_out = gr.Textbox(label="Box helper (copy into the finding)")
        with gr.Column(scale=2):
            editor = gr.Code(language="json", label="Label (gold label schema)", lines=28)
            with gr.Row():
                prev_b = gr.Button("◀ Previous")
                save_b = gr.Button("Save", variant="primary")
                next_b = gr.Button("Save and next ▶")
            status = gr.Markdown()
    with gr.Accordion("Labelling guide", open=False):
        gr.Markdown(GUIDE)

    demo.load(show, idx, [idx, img, info, editor, status, bbox_out])
    prev_b.click(lambda i: show(i - 1), idx, [idx, img, info, editor, status, bbox_out])
    save_b.click(save, [idx, editor], status)

    def save_next(i, text):
        msg = save(i, text)
        if msg.startswith("✅"):
            return show(i + 1)[:4] + (msg, "")
        return i, gr.update(), gr.update(), text, msg, gr.update()

    next_b.click(save_next, [idx, editor], [idx, img, info, editor, status, bbox_out])
    img.select(click, first_click, [first_click, bbox_out])

if __name__ == "__main__":
    if not ROWS:
        sys.exit(f"No images assigned to {ARGS.labeller} in {ARGS.images_csv}. Run scripts/make_images_csv.py first.")
    demo.launch(server_name="0.0.0.0", server_port=ARGS.port)
