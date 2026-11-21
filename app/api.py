"""HTTP API for the static demo site (GitHub Pages).

  DV_BACKEND=openai DV_BASE_URL=http://localhost:8000/v1 uvicorn app.api:app --host 0.0.0.0 --port 8080

GitHub Pages is https, so the browser needs an https URL for this API. Easiest:
  cloudflared tunnel --url http://localhost:8080      -> https://<random>.trycloudflare.com
Paste that URL into the site's "Connect model" dialog.
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fastapi import FastAPI, File, Form, HTTPException, UploadFile  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from PIL import Image, ImageOps, UnidentifiedImageError  # noqa: E402

from damagevision.backends import get_backend  # noqa: E402
from damagevision.pipeline import Pipeline, PipelineConfig  # noqa: E402
from damagevision.readiness import assess  # noqa: E402

MAX_BYTES = 15 * 1024 * 1024

app = FastAPI(title="Damage Evidence API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("DV_CORS_ORIGINS", "*").split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

_backend = get_backend()
PIPE = Pipeline(_backend, PipelineConfig(runs=int(os.getenv("DV_RUNS", "3")),
                                          verify=os.getenv("DV_VERIFY", "1") == "1",
                                          cost_per_hour_usd=float(os.getenv("DV_COST_PER_HOUR", "0")) or None))


@app.get("/health")
def health():
    return {
        "ok": True,
        "backend": _backend.name,
        "model": _backend.model,
        "runs": PIPE.cfg.runs,
        "verifier": PIPE.verifier.model if PIPE.cfg.verify and PIPE.verifier else None,
        "mock": _backend.name == "mock",
    }


@app.post("/analyze")
def analyze(image: UploadFile = File(...), claimant_text: str = Form("")):
    data = image.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Image larger than 15 MB")
    try:
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    except (UnidentifiedImageError, OSError):
        raise HTTPException(400, "Not a readable image")
    image_id = Path(image.filename or "upload").stem[:60] or "upload"
    res = PIPE.run(img, image_id)
    out = res.model_dump(mode="json")
    out["readiness"] = assess(res, claimant_text or None)
    return out
