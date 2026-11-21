"""Vision-language model backends.

- openai : any OpenAI-compatible server. Main path: `vllm serve Qwen/Qwen2.5-VL-7B-Instruct`
           on the AWS GPU, with schema-constrained JSON output. Also works for hosted APIs
           (frontier baseline) by changing base_url / model.
- hf     : local transformers (Colab / Kaggle), optional 4-bit. JSON is parsed and validated.
- mock   : deterministic fake output. For tests and for building the website without a GPU.
           Outputs are marked backend="mock" and must never be reported as results.

Every backend returns (raw_text, parsed ModelOutput or None, tokens or None).
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
from dataclasses import dataclass
from typing import Optional

from PIL import Image
from pydantic import ValidationError

from .prompt import SYSTEM_PROMPT, user_prompt
from .schema import ModelOutput, model_output_schema


@dataclass
class Generation:
    raw: str
    output: Optional[ModelOutput]
    tokens: Optional[int] = None
    error: Optional[str] = None


def parse_json(text: str) -> Optional[ModelOutput]:
    """Lenient parse: strip code fences / chatter, take the outermost JSON object, validate."""
    if not text:
        return None
    text = re.sub(r"```(?:json)?", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return ModelOutput.model_validate(json.loads(text[start : end + 1]))
    except (json.JSONDecodeError, ValidationError):
        return None


def _to_data_url(img: Image.Image, max_side: int = 1280) -> str:
    img = img.convert("RGB")
    if max(img.size) > max_side:
        img = img.copy()
        img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


class Backend:
    name = "base"
    model = "unknown"

    def generate(self, img: Image.Image, temperature: float = 0.0, seed: int | None = None) -> Generation:
        raise NotImplementedError

    def generate_validated(self, img: Image.Image, temperature: float = 0.0, seed: int | None = None,
                           retries: int = 2) -> Generation:
        """Retry on invalid JSON. Never raises: errors come back in Generation.error."""
        last = Generation(raw="", output=None, error="not run")
        for attempt in range(retries + 1):
            try:
                gen = self.generate(img, temperature=temperature if attempt == 0 else max(temperature, 0.3),
                                    seed=None if seed is None else seed + attempt)
            except Exception as e:  # network, OOM, server down
                last = Generation(raw="", output=None, error=f"{type(e).__name__}: {e}")
                continue
            if gen.output is not None:
                return gen
            last = Generation(raw=gen.raw, output=None, tokens=gen.tokens, error="invalid JSON from model")
        return last


class OpenAICompatBackend(Backend):
    name = "openai"

    def __init__(self, model: str | None = None, base_url: str | None = None, api_key: str | None = None,
                 guided: bool = True, max_tokens: int = 2048):
        from openai import OpenAI

        self.model = model or os.getenv("DV_MODEL", "Qwen/Qwen2.5-VL-7B-Instruct")
        self.client = OpenAI(base_url=base_url or os.getenv("DV_BASE_URL", "http://localhost:8000/v1"),
                             api_key=api_key or os.getenv("DV_API_KEY", "EMPTY"))
        self.guided = guided
        self.max_tokens = max_tokens

    def generate(self, img, temperature=0.0, seed=None):
        kwargs = {}
        if self.guided:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "damage_extraction", "schema": model_output_schema()},
            }
        if seed is not None:
            kwargs["seed"] = seed
        resp = self.client.chat.completions.create(
            model=self.model,
            temperature=temperature,
            max_tokens=self.max_tokens,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": _to_data_url(img)}},
                    {"type": "text", "text": user_prompt()},
                ]},
            ],
            **kwargs,
        )
        text = resp.choices[0].message.content or ""
        tokens = getattr(resp.usage, "total_tokens", None) if resp.usage else None
        return Generation(raw=text, output=parse_json(text), tokens=tokens)


class HFBackend(Backend):
    """Local transformers backend for Qwen2.5-VL / Qwen3-VL style chat models."""

    name = "hf"

    def __init__(self, model: str | None = None, load_4bit: bool | None = None, max_new_tokens: int = 1536):
        import torch
        from transformers import AutoModelForImageTextToText, AutoProcessor

        self.model = model or os.getenv("DV_MODEL", "Qwen/Qwen2.5-VL-7B-Instruct")
        if load_4bit is None:
            load_4bit = os.getenv("DV_LOAD_4BIT", "0") == "1"
        kwargs = {"torch_dtype": "auto", "device_map": "auto"}
        if load_4bit:
            from transformers import BitsAndBytesConfig

            kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True, bnb_4bit_compute_dtype=torch.float16, bnb_4bit_quant_type="nf4")
        self.processor = AutoProcessor.from_pretrained(self.model)
        self.net = AutoModelForImageTextToText.from_pretrained(self.model, **kwargs)
        self.max_new_tokens = max_new_tokens
        self.torch = torch

    def generate(self, img, temperature=0.0, seed=None):
        img = img.convert("RGB")
        if max(img.size) > 1280:
            img = img.copy()
            img.thumbnail((1280, 1280))
        messages = [
            {"role": "system", "content": [{"type": "text", "text": SYSTEM_PROMPT}]},
            {"role": "user", "content": [{"type": "image"}, {"type": "text", "text": user_prompt()}]},
        ]
        text = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self.processor(text=[text], images=[img], return_tensors="pt").to(self.net.device)
        if seed is not None:
            self.torch.manual_seed(seed)
        gen_kwargs = {"max_new_tokens": self.max_new_tokens}
        if temperature > 0:
            gen_kwargs.update(do_sample=True, temperature=temperature, top_p=0.9)
        else:
            gen_kwargs.update(do_sample=False)
        with self.torch.inference_mode():
            out = self.net.generate(**inputs, **gen_kwargs)
        new = out[:, inputs["input_ids"].shape[1]:]
        raw = self.processor.batch_decode(new, skip_special_tokens=True)[0]
        return Generation(raw=raw, output=parse_json(raw), tokens=int(out.shape[1]))


class MockBackend(Backend):
    """Deterministic fake model. Varies a little with seed so consistency logic can be tested."""

    name = "mock"
    model = "mock"

    def generate(self, img, temperature=0.0, seed=None):
        small = img.convert("L").resize((16, 16))
        h = int(hashlib.md5(small.tobytes()).hexdigest(), 16)
        dark = sum(small.tobytes()) / 256 < 60
        drop_second = bool(seed) and temperature > 0 and (h + (seed or 0)) % 3 == 0
        findings = [{
            "damage_type": "water_stain", "component": "ceiling", "material": "paint",
            "location": "upper centre", "visible_traits": ["brown discoloration", "tide marks"],
            "extent": "medium", "age_indicators": ["tide_marks"], "status": "visible",
            "uncertain": False, "bbox_1000": [300, 100, 650, 400], "notes": None,
        }]
        if h % 2 == 0 and not drop_second:
            findings.append({
                "damage_type": "crack", "component": "wall", "material": "unknown",
                "location": "lower left", "visible_traits": ["thin diagonal line"], "extent": "small",
                "age_indicators": ["none_visible"], "status": "inferred", "uncertain": True,
                "bbox_1000": [50, 600, 250, 900], "notes": "could be a paint edge",
            })
        data = {
            "damage_present": "yes", "image_quality": "limited" if dark else "good",
            "quality_issues": ["dark"] if dark else [], "scene": "interior",
            "findings": findings, "limitations": ["Cause not assessable"],
        }
        raw = json.dumps(data)
        return Generation(raw=raw, output=ModelOutput.model_validate(data), tokens=None)


def get_backend(name: str | None = None, **kwargs) -> Backend:
    name = (name or os.getenv("DV_BACKEND", "mock")).lower()
    if name == "openai":
        return OpenAICompatBackend(**kwargs)
    if name == "hf":
        return HFBackend(**kwargs)
    if name == "mock":
        return MockBackend()
    raise ValueError(f"unknown backend {name!r} (use openai, hf or mock)")
