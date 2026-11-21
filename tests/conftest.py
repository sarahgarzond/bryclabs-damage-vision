import pytest
from PIL import Image, ImageDraw


@pytest.fixture
def img():
    im = Image.new("RGB", (800, 600), (235, 235, 230))
    d = ImageDraw.Draw(im)
    d.ellipse([260, 70, 520, 230], fill=(150, 110, 60))
    d.line([60, 560, 180, 380], fill=(40, 40, 40), width=3)
    return im
