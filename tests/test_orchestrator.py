import json
from types import SimpleNamespace

from damagevision.backends import Backend, Generation, MockBackend
from damagevision.claude_agents import ClaudeBackend, JudgeOutput, Verdict
from damagevision.orchestrator import Orchestrator
from damagevision.readiness import assess
from damagevision.schema import ModelOutput


class Fixed(Backend):
    def __init__(self, name, data=None, fail=False):
        self.name, self.model, self.data, self.fail = name, name + "-model", data, fail

    def generate(self, img, temperature=0.0, seed=None):
        if self.fail:
            raise RuntimeError("401 bad key")
        return Generation(raw=json.dumps(self.data), output=ModelOutput.model_validate(self.data))


def out(*types):
    boxes = {"water_stain": [300, 100, 650, 400], "crack": [50, 600, 250, 900], "mould": [700, 700, 900, 900]}
    return {"damage_present": "yes", "image_quality": "good", "scene": "interior", "limitations": ["Cause not assessable"],
            "findings": [{"damage_type": t, "component": "wall", "material": "unknown", "location": "x", "extent": "small",
                          "status": "visible", "uncertain": False, "bbox_1000": boxes[t]} for t in types]}


class FakeJudge:
    model = "judge-model"

    def __init__(self, verdicts):
        self.verdicts = verdicts

    def review(self, img, merged, findings):
        idx = {f.damage_type.value: i + 1 for i, f in enumerate(findings)}
        v = [Verdict(index=idx[t], verdict=s, reason="r") for t, s in self.verdicts.items() if t in idx]
        return JudgeOutput(verdicts=v, missing_information=["Close-up with a ruler"], additional_limitations=[]), \
            {"agent": "judge", "model": self.model, "ok": True, "seconds": 0.1}


def test_orchestrator_merges_judges_and_survives_failures(img):
    agents = [Fixed("a", out("water_stain", "crack")), Fixed("b", out("water_stain")),
              Fixed("c", out("water_stain", "mould")), Fixed("d", fail=True)]
    judge = FakeJudge({"water_stain": "supported", "crack": "uncertain", "mould": "unsupported"})
    res = Orchestrator(agents=agents, judge=judge, use_judge=True, calibration_path=None).run(img, "t")
    by = {f.damage_type.value: f for f in res.findings}
    assert by["water_stain"].agreement == 1.0 and by["water_stain"].verified and not by["water_stain"].uncertain
    assert by["crack"].uncertain                                   # 1 of 3 models + judge uncertain
    assert [f.damage_type.value for f in res.dropped_findings] == ["mould"]   # 1 of 3 + unsupported
    assert res.missing_information == ["Close-up with a ruler"]
    assert any(t["agent"] == "d" and not t["ok"] for t in res.meta.agents)
    assert "Close-up with a ruler" in assess(res)["follow_up_requests"]


def test_orchestrator_all_fail_returns_error(img):
    res = Orchestrator(agents=[Fixed("x", fail=True)], use_judge=False, calibration_path=None).run(img, "t")
    assert res.status == "error"


def test_claude_backend_request_shape(img, monkeypatch):
    sent = {}
    data = out("crack")

    class Msgs:
        def create(self, **kw):
            sent.update(kw)
            return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(data))],
                                   usage=SimpleNamespace(input_tokens=10, output_tokens=5))

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    b = ClaudeBackend()
    b.caller.client = SimpleNamespace(messages=Msgs(), beta=SimpleNamespace(messages=Msgs()))
    g = b.generate(img)
    assert g.output.findings[0].damage_type.value == "crack" and g.tokens == 15
    assert sent["model"] == "claude-opus-5-5" and sent["fallbacks"] == "default"
    assert sent["output_config"]["format"]["type"] == "json_schema" and "temperature" not in sent
    assert sent["messages"][0]["content"][0]["type"] == "image"


def test_claude_refusal_is_reported(img, monkeypatch):
    class Msgs:
        def create(self, **kw):
            return SimpleNamespace(stop_reason="refusal", stop_details=SimpleNamespace(category="cyber"), content=[],
                                   usage=SimpleNamespace(input_tokens=1, output_tokens=0))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    b = ClaudeBackend()
    b.caller.client = SimpleNamespace(messages=Msgs(), beta=SimpleNamespace(messages=Msgs()))
    assert "refused" in b.generate(img).error


def test_openai_compat_falls_back_when_schema_rejected(img):
    import httpx
    from openai import BadRequestError
    from damagevision.backends import OpenAICompatBackend
    seen = []
    good = json.dumps(out("crack"))

    class Completions:
        def create(self, **kw):
            fmt = kw.get("response_format", {}).get("type")
            seen.append(fmt)
            if fmt == "json_schema":
                req = httpx.Request("POST", "https://x")
                raise BadRequestError("bad schema", response=httpx.Response(400, request=req), body=[{"error": "schema"}])
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=good))], usage=None)

    b = OpenAICompatBackend(name="gemini", model="g", base_url="https://x", api_key="k", send_seed=False)
    b.client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    g = b.generate_validated(img, seed=0)
    assert g.output.findings[0].damage_type.value == "crack" and seen == ["json_schema", "json_object"]
    b.generate_validated(img)
    assert seen[-1] == "json_object"          # remembered, no retry with the rejected schema
