from damagevision.backends import MockBackend
from damagevision.pipeline import Pipeline, PipelineConfig
from damagevision.readiness import assess


def test_pipeline_mock_end_to_end(img):
    res = Pipeline(MockBackend(), PipelineConfig(runs=3, verify=False, calibration_path=None)).run(img, "t1")
    assert res.status == "ok"
    assert res.findings and all(0 <= f.confidence <= 1 for f in res.findings)
    stain = [f for f in res.findings if f.damage_type.value == "water_stain"][0]
    assert stain.agreement == 1.0 and stain.bbox[0] == 240.0  # 300/1000*800
    r = assess(res, "Water came through the ceiling after a pipe burst")
    assert any("Reported water" in c for c in r["claim_text_consistency"])


class Broken(MockBackend):
    name = "broken"

    def generate(self, img, temperature=0.0, seed=None):
        raise RuntimeError("server down")


def test_pipeline_error_is_reported_not_raised(img):
    res = Pipeline(Broken(), PipelineConfig(runs=2, verify=False, calibration_path=None)).run(img, "t2")
    assert res.status == "error" and res.meta.errors


class FakeVerifier:
    model = "fake"

    def detect(self, img, types):
        return {"water_stain": [(0.9, [240, 60, 280, 180])]}

    def check(self, dets, t, box):
        from damagevision.verifier import Verification
        hits = dets.get(t, [])
        return Verification(bool(hits), hits[0][0] if hits else 0.0, hits[0][1] if hits else None)


def test_verifier_marks_unconfirmed_uncertain(img):
    res = Pipeline(MockBackend(), PipelineConfig(runs=1, verify=True, calibration_path=None),
                   verifier=FakeVerifier()).run(img, "t3")
    by = {f.damage_type.value: f for f in res.findings}
    assert by["water_stain"].verified is True and by["water_stain"].uncertain is False
    if "crack" in by:
        assert by["crack"].verified is False and by["crack"].uncertain is True
