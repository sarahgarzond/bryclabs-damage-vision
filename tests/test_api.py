import io
import os

import pytest

os.environ["DV_BACKEND"] = "mock"
os.environ["DV_VERIFY"] = "0"
fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from app.api import app  # noqa: E402

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["mock"] is True


def test_analyze(img):
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    r = client.post("/analyze", files={"image": ("x.jpg", buf.getvalue(), "image/jpeg")},
                    data={"claimant_text": "pipe burst"})
    body = r.json()
    assert r.status_code == 200 and body["status"] == "ok" and "readiness" in body


def test_analyze_rejects_non_image():
    r = client.post("/analyze", files={"image": ("x.txt", b"hello", "text/plain")})
    assert r.status_code == 400
