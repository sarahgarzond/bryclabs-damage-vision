"""Demo website: Analyse, Claim readiness, Evaluation, Method.

  DV_BACKEND=openai DV_BASE_URL=http://<aws-ip>:8000/v1 python app/app.py
  DV_BACKEND=mock python app/app.py          # UI work without a GPU (fake output, labelled as such)

Set DV_EVAL_DIR to the folder written by scripts/evaluate.py (default outputs/eval/main).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import gradio as gr  # noqa: E402
from PIL import Image, ImageDraw, ImageFont, ImageOps  # noqa: E402

from damagevision.backends import get_backend  # noqa: E402
from damagevision.pipeline import Pipeline, PipelineConfig  # noqa: E402
from damagevision.readiness import assess  # noqa: E402

STATUS_COLOURS = {"visible": "#1a9850", "inferred": "#f39c12", "not_assessable": "#7f8c8d"}
UNCERTAIN_COLOUR = "#d35400"

_backend = get_backend()
PIPE = Pipeline(_backend, PipelineConfig(runs=int(os.getenv("DV_RUNS", "3")),
                                          verify=os.getenv("DV_VERIFY", "1") == "1"))
EVAL_DIR = Path(os.getenv("DV_EVAL_DIR", ROOT / "outputs" / "eval" / "main"))


def draw_boxes(img: Image.Image, findings) -> Image.Image:
    img = img.copy()
    d = ImageDraw.Draw(img)
    lw = max(2, img.width // 300)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", max(14, img.width // 50))
    except OSError:
        font = ImageFont.load_default()
    for k, f in enumerate(findings, 1):
        if not f.bbox:
            continue
        x, y, w, h = f.bbox
        colour = UNCERTAIN_COLOUR if f.uncertain else STATUS_COLOURS[f.status.value]
        d.rectangle([x, y, x + w, y + h], outline=colour, width=lw)
        label = f"{k} {f.damage_type.value} {f.confidence or 0:.2f}"
        tb = d.textbbox((x, y), label, font=font)
        d.rectangle([tb[0] - 2, tb[1] - 2, tb[2] + 2, tb[3] + 2], fill=colour)
        d.text((x, y), label, fill="white", font=font)
    return img


def chips_html(res) -> str:
    if not res.findings:
        return "<p><b>No damage findings.</b></p>"
    parts = []
    for k, f in enumerate(res.findings, 1):
        colour = UNCERTAIN_COLOUR if f.uncertain else STATUS_COLOURS[f.status.value]
        ver = "verified by detector" if f.verified else ("not confirmed by detector" if f.verified is False else "")
        parts.append(
            f"<div style='border-left:6px solid {colour};padding:6px 10px;margin:6px 0;background:rgba(127,127,127,.08)'>"
            f"<b>{k}. {f.damage_type.value.replace('_', ' ')}</b> on {f.component.value} "
            f"({f.material.value}, {f.extent.value})<br>"
            f"<small>status <b>{f.status.value}</b>{' · uncertain' if f.uncertain else ''} · confidence "
            f"<b>{f.confidence or 0:.2f}</b> · agreement {f.agreement or 0:.2f} {('· ' + ver) if ver else ''}<br>"
            f"{f.location or ''}{' · ' + ', '.join(f.visible_traits) if f.visible_traits else ''}</small></div>")
    if res.dropped_findings:
        dropped = ", ".join(f.damage_type.value for f in res.dropped_findings)
        parts.append(f"<p><small>Dropped as unsupported (seen in too few runs, not confirmed): {dropped}</small></p>")
    return "".join(parts)


def readiness_md(r: dict) -> str:
    def section(title, items, empty):
        body = "\n".join(f"- {x}" for x in items) if items else f"- _{empty}_"
        return f"### {title}\n{body}\n"

    md = section("Established", r["established"], "nothing established with high confidence")
    md += section("Indicated (needs confirmation)", r["indicated"], "none")
    md += section("Missing or not assessable", r["missing"], "none")
    md += section("Follow-up photo requests", r["follow_up_requests"], "none")
    if r["claim_text_consistency"]:
        md += section("Claimant text vs photo", r["claim_text_consistency"], "")
    md += f"\n> {r['note']}"
    return md


def analyse(image, claimant_text):
    if image is None:
        raise gr.Error("Upload a photo first.")
    img = ImageOps.exif_transpose(image).convert("RGB")
    res = PIPE.run(img, "upload")
    data = res.model_dump(mode="json")
    r = assess(res, claimant_text)
    data["readiness"] = r
    m = res.meta
    meta = f"{m.backend} · {m.model} · {m.runs} runs · {m.runtime_s:.1f} s" + (f" · {m.device}" if m.device else "")
    if m.backend == "mock":
        meta += " · ⚠ MOCK OUTPUT, NOT A REAL MODEL"
    summary = (f"**Damage present:** {res.damage_present.value} · **Image quality:** {res.image_quality.value}"
               f"{' (' + ', '.join(q.value for q in res.quality_issues) + ')' if res.quality_issues else ''}"
               f" · **Scene:** {res.scene.value}\n\n<small>{meta}</small>")
    return draw_boxes(img, res.findings), summary, chips_html(res), json.dumps(data, indent=2), readiness_md(r)


def eval_tab_content():
    metrics_path = EVAL_DIR / "metrics.json"
    if not metrics_path.exists():
        return f"_No evaluation yet. Run scripts/evaluate.py with --out {EVAL_DIR}._", None, None
    m = json.loads(metrics_path.read_text())
    f = m["findings"]
    md = (f"### Results on {m['images_evaluated']} hand-labelled images\n"
          f"| Metric | Value |\n|---|---|\n"
          f"| Finding precision | {f['precision']} |\n| Finding recall | {f['recall']} |\n| F1 | {f['f1']} |\n"
          f"| Unsupported finding rate | {m['unsupported_finding_rate']} |\n"
          f"| Hallucination on negative images | {m['negatives']['hallucination_rate']} "
          f"({m['negatives']['with_any_finding']}/{m['negatives']['images']}) |\n"
          f"| Mean box IoU | {m['boxes']['mean_iou']} |\n"
          f"| Confidence AUROC | {m['confidence_auroc']} |\n"
          f"| Seconds per image (mean) | {m['runtime_s_per_image']['mean']} |\n")
    agree = EVAL_DIR / "agreement.json"
    if agree.exists():
        a = json.loads(agree.read_text())
        md += f"\n**Labeller agreement** (Cohen's kappa, damage types): {a.get('kappa_damage_type_presence')}\n"
    rob = EVAL_DIR / "robustness.png"
    cal = EVAL_DIR / "calibration.png"
    return md, str(rob) if rob.exists() else None, str(cal) if cal.exists() else None


METHOD_MD = (ROOT / "docs" / "method.md").read_text() if (ROOT / "docs" / "method.md").exists() else ""

with gr.Blocks(title="Damage Evidence Extractor") as demo:
    gr.Markdown("# Damage Evidence Extractor\nPhoto in, verified and structured damage evidence out. "
                "We extract evidence and say how sure we are. Coverage is decided downstream.")
    with gr.Tab("Analyse"):
        with gr.Row():
            with gr.Column(scale=1):
                inp = gr.Image(type="pil", label="Damage photo")
                txt = gr.Textbox(label="Claimant description (optional, only used for the consistency check)",
                                 lines=3)
                btn = gr.Button("Analyse", variant="primary")
            with gr.Column(scale=1):
                out_img = gr.Image(label="Findings (green visible, amber inferred, orange uncertain)")
                out_sum = gr.Markdown()
        out_chips = gr.HTML()
        with gr.Accordion("Raw JSON", open=False):
            out_json = gr.Code(language="json")
    with gr.Tab("Claim readiness"):
        out_ready = gr.Markdown("_Analyse a photo first._")
    with gr.Tab("Evaluation"):
        ev_md, ev_rob, ev_cal = eval_tab_content()
        gr.Markdown(ev_md)
        with gr.Row():
            if ev_rob:
                gr.Image(ev_rob, label="Robustness")
            if ev_cal:
                gr.Image(ev_cal, label="Calibration")
    with gr.Tab("Method"):
        gr.Markdown(METHOD_MD or "_docs/method.md missing_")
    btn.click(analyse, [inp, txt], [out_img, out_sum, out_chips, out_json, out_ready])

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=int(os.getenv("PORT", "7860")),
                share=os.getenv("DV_SHARE", "0") == "1")
