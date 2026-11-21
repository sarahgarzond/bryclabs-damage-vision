import json

from damagevision.backends import parse_json
from damagevision.schema import GoldLabel, ModelFinding, blank_label, model_output_schema


def test_schema_has_no_refs():
    assert "$ref" not in json.dumps(model_output_schema())


def test_degenerate_box_becomes_null():
    f = ModelFinding(damage_type="crack", component="wall", material="unknown", location="x",
                     extent="small", status="visible", uncertain=False, bbox_1000=[500, 500, 400, 600])
    assert f.bbox_1000 is None


def test_parse_json_with_fences():
    text = '```json\n{"damage_present":"no","image_quality":"good","scene":"interior","findings":[]}\n```'
    assert parse_json(text).damage_present.value == "no"


def test_parse_json_rejects_bad_enum():
    assert parse_json('{"damage_present":"maybe","image_quality":"good","scene":"interior"}') is None


def test_blank_label_valid():
    GoldLabel.model_validate(blank_label("img_001", "olivia"))
