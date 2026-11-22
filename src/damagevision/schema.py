"""The JSON schema: the contract between the model, the labellers and the evaluation.

Three layers:
- ModelOutput: what the vision-language model must emit (schema-constrained decoding).
- ImageResult: the final pipeline output per image (model output + verification + confidence).
- GoldLabel: what a human labeller writes. Same field names as ImageResult so evaluation
  is a field-by-field comparison.

Allowed values match docs/labelling_guide.md. Change them only after telling the team.
"""
from __future__ import annotations

import copy
import json
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class DamagePresent(str, Enum):
    yes = "yes"
    no = "no"
    unclear = "unclear"


class ImageQuality(str, Enum):
    good = "good"
    limited = "limited"
    poor = "poor"


class QualityIssue(str, Enum):
    blur = "blur"
    dark = "dark"
    overexposed = "overexposed"
    too_far = "too_far"
    partial_view = "partial_view"
    obstructed = "obstructed"
    low_resolution = "low_resolution"


class Scene(str, Enum):
    interior = "interior"
    exterior = "exterior"
    not_a_building = "not_a_building"


class DamageType(str, Enum):
    crack = "crack"
    water_stain = "water_stain"
    mould = "mould"
    flaking_paint = "flaking_paint"
    plaster_loss = "plaster_loss"
    hole = "hole"
    swelling = "swelling"
    rot = "rot"
    rust = "rust"
    scorch = "scorch"
    broken_glass = "broken_glass"
    detachment = "detachment"
    other = "other"


class Component(str, Enum):
    wall = "wall"
    ceiling = "ceiling"
    floor = "floor"
    window = "window"
    door = "door"
    frame = "frame"
    roof = "roof"
    facade = "facade"
    pipe = "pipe"
    stairs = "stairs"
    other = "other"
    unknown = "unknown"


class Material(str, Enum):
    plaster = "plaster"
    paint = "paint"
    wallpaper = "wallpaper"
    wood = "wood"
    tile = "tile"
    concrete = "concrete"
    brick = "brick"
    glass = "glass"
    metal = "metal"
    plastic = "plastic"
    other = "other"
    unknown = "unknown"


class Extent(str, Enum):
    small = "small"
    medium = "medium"
    large = "large"
    unknown = "unknown"


class AgeIndicator(str, Enum):
    tide_marks = "tide_marks"
    multiple_layers = "multiple_layers"
    old_repair = "old_repair"
    mould_growth = "mould_growth"
    corrosion = "corrosion"
    none_visible = "none_visible"


class Status(str, Enum):
    visible = "visible"
    inferred = "inferred"
    not_assessable = "not_assessable"


# --------------------------------------------------------------------------- model output


class ModelFinding(BaseModel):
    """One damage finding as emitted by the VLM. Box is normalised 0..1000 [x1, y1, x2, y2]."""

    damage_type: DamageType
    component: Component
    material: Material
    location: str = Field(description="Short position in the image, e.g. 'lower left wall, near window'")
    visible_traits: list[str] = Field(default_factory=list, description="Observable details only")
    extent: Extent
    age_indicators: list[AgeIndicator] = Field(default_factory=list)
    status: Status
    uncertain: bool
    bbox_1000: Optional[list[int]] = Field(
        default=None, description="[x1, y1, x2, y2] normalised to 0..1000, null if not locatable"
    )
    notes: Optional[str] = None

    @field_validator("bbox_1000")
    @classmethod
    def _check_box(cls, v):
        if v is None:
            return v
        if len(v) != 4:
            raise ValueError("bbox_1000 needs 4 numbers")
        x1, y1, x2, y2 = [max(0, min(1000, int(c))) for c in v]
        if x2 <= x1 or y2 <= y1:
            return None  # degenerate box: treat as not locatable instead of failing the image
        return [x1, y1, x2, y2]


class ModelOutput(BaseModel):
    damage_present: DamagePresent
    image_quality: ImageQuality
    quality_issues: list[QualityIssue] = Field(default_factory=list)
    scene: Scene
    findings: list[ModelFinding] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- final output


class Finding(BaseModel):
    """Final finding. bbox is pixels [x, y, width, height] on the original image."""

    damage_type: DamageType
    component: Component
    material: Material
    location: Optional[str] = None
    visible_traits: list[str] = Field(default_factory=list)
    extent: Extent = Extent.unknown
    age_indicators: list[AgeIndicator] = Field(default_factory=list)
    status: Status
    uncertain: bool
    bbox: Optional[list[float]] = None
    notes: Optional[str] = None
    # pipeline-only evidence fields (absent in gold labels)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    agreement: Optional[float] = Field(default=None, ge=0, le=1, description="share of runs that found it")
    verified: Optional[bool] = Field(default=None, description="detector found it at the claimed place")
    verifier_score: Optional[float] = None


class RunMeta(BaseModel):
    model: str
    backend: str
    runs: int
    runtime_s: float
    seconds_per_run: list[float] = Field(default_factory=list)
    verifier: Optional[str] = None
    verifier_s: Optional[float] = None
    device: Optional[str] = None
    tokens: Optional[int] = None
    est_cost_usd: Optional[float] = None
    calibrated: bool = Field(default=False, description="confidence from a model fitted on gold labels")
    agents: list[dict] = Field(default_factory=list, description="per-subagent trace: model, role, ok, seconds, error")
    errors: list[str] = Field(default_factory=list)


class ImageResult(BaseModel):
    image_id: str
    width: Optional[int] = None
    height: Optional[int] = None
    damage_present: DamagePresent
    image_quality: ImageQuality
    quality_issues: list[QualityIssue] = Field(default_factory=list)
    scene: Scene
    findings: list[Finding] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    dropped_findings: list[Finding] = Field(
        default_factory=list, description="removed as unsupported, kept for transparency"
    )
    missing_information: list[str] = Field(
        default_factory=list, description="what an adjuster still needs that this photo cannot show"
    )
    meta: Optional[RunMeta] = None
    status: str = Field(default="ok", description="'ok' or 'error'")


class GoldLabel(BaseModel):
    """Human label. Same fields as ImageResult minus pipeline evidence."""

    image_id: str
    labeller: Optional[str] = None
    damage_present: DamagePresent
    image_quality: ImageQuality
    quality_issues: list[QualityIssue] = Field(default_factory=list)
    scene: Scene
    findings: list[Finding] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- helpers


def inline_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Inline $defs/$ref so every guided-decoding backend accepts the schema."""
    schema = copy.deepcopy(schema)
    defs = schema.pop("$defs", {})

    def resolve(node):
        if isinstance(node, dict):
            if "$ref" in node:
                name = node["$ref"].split("/")[-1]
                merged = {**resolve(defs[name]), **{k: v for k, v in node.items() if k != "$ref"}}
                return merged
            return {k: resolve(v) for k, v in node.items()}
        if isinstance(node, list):
            return [resolve(x) for x in node]
        return node

    return resolve(schema)


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Schema for strict structured outputs (Anthropic output_config.format, OpenAI strict):
    refs inlined, every object closed (additionalProperties false) with all keys required
    (optional values stay nullable through anyOf null), defaults and titles removed."""
    def walk(node):
        if isinstance(node, dict):
            node = {k: walk(v) for k, v in node.items() if k not in ("default", "title")}
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"])
            return node
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node
    return walk(inline_refs(model.model_json_schema()))


def model_output_schema() -> dict[str, Any]:
    return inline_refs(ModelOutput.model_json_schema())


def export_schemas(out_dir: str = "schema") -> list[str]:
    import os

    os.makedirs(out_dir, exist_ok=True)
    written = []
    for name, model in [("model_output", ModelOutput), ("image_result", ImageResult), ("gold_label", GoldLabel)]:
        path = os.path.join(out_dir, f"{name}.schema.json")
        with open(path, "w") as f:
            json.dump(inline_refs(model.model_json_schema()), f, indent=2)
        written.append(path)
    return written


def blank_label(image_id: str, labeller: str | None = None) -> dict[str, Any]:
    """Empty template for blind labelling."""
    return {
        "image_id": image_id,
        "labeller": labeller,
        "damage_present": "unclear",
        "image_quality": "good",
        "quality_issues": [],
        "scene": "interior",
        "findings": [],
        "limitations": [],
    }


def result_to_label(result: dict[str, Any], labeller: str | None = None) -> dict[str, Any]:
    """Turn a pipeline output into a pre-filled label (pipeline-only fields stripped)."""
    keep = {"damage_type", "component", "material", "location", "visible_traits", "extent",
            "age_indicators", "status", "uncertain", "bbox", "notes"}
    return {
        "image_id": result["image_id"],
        "labeller": labeller,
        "damage_present": result["damage_present"],
        "image_quality": result["image_quality"],
        "quality_issues": result.get("quality_issues", []),
        "scene": result["scene"],
        "findings": [{k: v for k, v in f.items() if k in keep} for f in result.get("findings", [])],
        "limitations": result.get("limitations", []),
    }
