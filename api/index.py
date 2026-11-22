"""Vercel serverless entry point: exposes the FastAPI app from app/api.py."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from app.api import app  # noqa: E402,F401
