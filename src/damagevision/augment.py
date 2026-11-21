"""Image variations.

PHOTOMETRIC variants keep geometry, so boxes stay comparable: used inside the pipeline for
self-consistency. GEOMETRIC/DEGRADING variants are used by scripts/robustness.py only.
"""
from __future__ import annotations

import io
from typing import Callable

from PIL import Image, ImageEnhance, ImageFilter


def _jpeg(img: Image.Image, q: int) -> Image.Image:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=q)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def _crop(img: Image.Image, keep: float) -> Image.Image:
    w, h = img.size
    dx, dy = int(w * (1 - keep) / 2), int(h * (1 - keep) / 2)
    return img.crop((dx, dy, w - dx, h - dy))


PHOTOMETRIC: dict[str, Callable[[Image.Image], Image.Image]] = {
    "original": lambda im: im,
    "brighter": lambda im: ImageEnhance.Brightness(im).enhance(1.15),
    "contrast": lambda im: ImageEnhance.Contrast(im).enhance(1.15),
    "jpeg80": lambda im: _jpeg(im, 80),
    "sharpen": lambda im: im.filter(ImageFilter.SHARPEN),
}

ROBUSTNESS: dict[str, Callable[[Image.Image], Image.Image]] = {
    "blur": lambda im: im.filter(ImageFilter.GaussianBlur(radius=3)),
    "dark": lambda im: ImageEnhance.Brightness(im).enhance(0.45),
    "bright": lambda im: ImageEnhance.Brightness(im).enhance(1.7),
    "jpeg20": lambda im: _jpeg(im, 20),
    "crop80": lambda im: _crop(im, 0.8),
    "rotate8": lambda im: im.rotate(8, expand=False, fillcolor=(0, 0, 0)),
    "hflip": lambda im: im.transpose(Image.FLIP_LEFT_RIGHT),
    "lowres": lambda im: im.resize((max(1, im.width // 4), max(1, im.height // 4))).resize(im.size),
}


def photometric_variants(img: Image.Image, n: int) -> list[tuple[str, Image.Image]]:
    names = list(PHOTOMETRIC)[: max(1, n)]
    # if more runs than variants, reuse them (sampling temperature still differs per run)
    while len(names) < n:
        names.append(names[len(names) % len(PHOTOMETRIC)])
    return [(name, PHOTOMETRIC[name](img.convert("RGB"))) for name in names]
