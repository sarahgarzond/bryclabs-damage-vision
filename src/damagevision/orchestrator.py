"""Orchestrator: several vision models as parallel subagents, merged by cross-model agreement,
then a judge agent that checks every finding against the photo.

  photo ──► subagents in parallel (Gemini, GPT, optional Qwen-VL via vLLM)
                 each returns the same schema-constrained JSON
            ──► merge: cluster findings by type + box overlap, agreement = share of models that found it
            ──► judge (Gemini or GPT): supported / uncertain / unsupported per finding + missing information
            ──► rules: unsupported and not agreed by most models -> dropped (kept for transparency)
                       uncertain, unsupported or low agreement     -> flagged uncertain
            ──► confidence, claim readiness, ImageResult

Agents are enabled by which API keys exist (GEMINI_API_KEY, OPENAI_API_KEY, DV_BASE_URL for vLLM)
and can be limited with DV_AGENTS="openai,gemini,vllm".
A failing agent never fails the request: it is recorded in meta.agents and the rest continue.
"""
from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from PIL import Image

from .backends import Backend, OpenAICompatBackend
from .consistency import merge_runs
from .pipeline import confidence_score, error_result, load_calibration
from .schema import DamagePresent, ImageResult, RunMeta


def build_agents(enabled: Optional[str] = None) -> list[Backend]:
    wanted = {a.strip() for a in (enabled or os.getenv("DV_AGENTS", "openai,gemini,vllm")).split(",") if a.strip()}
    agents: list[Backend] = []
    if "openai" in wanted and os.getenv("OPENAI_API_KEY"):
        agents.append(OpenAICompatBackend(
            name="openai", model=os.getenv("DV_OPENAI_MODEL", "gpt-5.1"), base_url="https://api.openai.com/v1",
            api_key=os.getenv("OPENAI_API_KEY"), strict=True, send_temperature=False,
            token_param="max_completion_tokens", max_tokens=int(os.getenv("DV_OPENAI_MAX_TOKENS", "8000"))))
    if "gemini" in wanted and (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
        agents.append(OpenAICompatBackend(
            name="gemini", model=os.getenv("DV_GEMINI_MODEL", "gemini-3.1-pro-preview"),
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"), max_tokens=8000, send_seed=False))
    if "vllm" in wanted and os.getenv("DV_BASE_URL"):
        agents.append(OpenAICompatBackend(name="qwen-vllm"))
    return agents


def available() -> bool:
    return bool(build_agents_cheap())


def build_agents_cheap() -> list[str]:
    """Which agents would be enabled, without constructing clients."""
    out = []
    wanted = os.getenv("DV_AGENTS", "openai,gemini,vllm")
    if "openai" in wanted and os.getenv("OPENAI_API_KEY"):
        out.append("openai")
    if "gemini" in wanted and (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
        out.append("gemini")
    if "vllm" in wanted and os.getenv("DV_BASE_URL"):
        out.append("qwen-vllm")
    return out


class Orchestrator:
    name = "orchestrator"

    def __init__(self, agents: Optional[list[Backend]] = None, judge=None, use_judge: Optional[bool] = None,
                 calibration_path: Optional[str] = "outputs/eval/calibration.json"):
        self.agents = agents if agents is not None else build_agents()
        if use_judge is None:
            use_judge = os.getenv("DV_JUDGE", "1") == "1"
        if judge is None and use_judge:
            from .judge import Judge, default_provider
            if default_provider():
                judge = Judge()
        self.judge = judge if use_judge else None
        self.calib = load_calibration(calibration_path)
        self.cost_per_mtok = None

    def describe(self) -> dict:
        return {"backend": "orchestrator",
                "model": " + ".join(f"{a.name}:{a.model}" for a in self.agents) or "none",
                "agents": [{"name": a.name, "model": a.model} for a in self.agents],
                "judge": getattr(self.judge, "model", None), "runs": len(self.agents),
                "verifier": getattr(self.judge, "model", None), "mock": False}

    def _call(self, agent: Backend, img: Image.Image):
        t = time.perf_counter()
        gen = agent.generate_validated(img, temperature=0.0, seed=0, retries=1)
        trace = {"agent": agent.name, "role": "extractor", "model": agent.model, "ok": gen.output is not None,
                 "seconds": round(time.perf_counter() - t, 2), "tokens": gen.tokens,
                 "findings": len(gen.output.findings) if gen.output else None}
        if gen.output is None:
            trace["error"] = (gen.error or "no output")[:400]
        return gen, trace

    def run(self, img: Image.Image, image_id: str) -> ImageResult:
        t0 = time.perf_counter()
        w, h = img.size
        if not self.agents:
            return error_result(image_id, "no model API keys configured on the server")

        outputs, traces = [], []
        with ThreadPoolExecutor(max_workers=len(self.agents)) as ex:
            futures = [ex.submit(self._call, a, img) for a in self.agents]
            for fut in as_completed(futures):
                gen, trace = fut.result()
                traces.append(trace)
                if gen.output is not None:
                    outputs.append(gen.output)
        traces.sort(key=lambda t: t["agent"])
        errors = [f"{t['agent']}: {t['error']}" for t in traces if not t["ok"]]
        meta = RunMeta(model=" + ".join(t["model"] for t in traces if t["ok"]) or "none", backend="orchestrator",
                       runs=len(self.agents), runtime_s=0.0, agents=traces, errors=errors,
                       calibrated=self.calib is not None,
                       tokens=sum(t.get("tokens") or 0 for t in traces) or None)
        if not outputs:
            meta.runtime_s = round(time.perf_counter() - t0, 3)
            return error_result(image_id, "all models failed: " + "; ".join(errors), meta)

        merged = merge_runs(outputs, w, h)  # agreement = share of successful models reporting the finding
        findings = merged.pop("findings")
        missing: list[str] = []

        judge_out = None
        if self.judge is not None:
            judge_out, jtrace = self.judge.review(img, merged, findings)
            jtrace["role"] = "judge"
            meta.agents.append(jtrace)
            meta.tokens = (meta.tokens or 0) + (jtrace.get("tokens") or 0) or None
            if judge_out is None:
                meta.errors.append(f"judge: {jtrace.get('error')}")
            else:
                meta.verifier = self.judge.model

        verdicts = {v.index: v for v in (judge_out.verdicts if judge_out else [])}
        kept, dropped = [], []
        for i, f in enumerate(findings, 1):
            v = verdicts.get(i)
            agreed = (f.agreement or 0) >= 0.67
            if v is not None:
                f.verified = v.verdict == "supported"
                f.verifier_score = {"supported": 1.0, "uncertain": 0.5, "unsupported": 0.0}[v.verdict]
                note = f"Judge: {v.reason}"
                f.notes = f"{f.notes} | {note}" if f.notes else note
                if v.verdict == "unsupported" and not agreed:
                    dropped.append(f)
                    continue
                if v.verdict != "supported":
                    f.uncertain = True
            if not agreed and len(outputs) > 1:
                f.uncertain = True
            f.confidence = confidence_score(f, meta.verifier is not None, self.calib)
            kept.append(f)

        if judge_out:
            missing = judge_out.missing_information
            for lim in judge_out.additional_limitations:
                if lim not in merged["limitations"]:
                    merged["limitations"].append(lim)
        if not kept and merged["damage_present"] == DamagePresent.yes:
            merged["damage_present"] = DamagePresent.unclear
            merged["limitations"].append("Proposed damage was not confirmed by the review")

        meta.runtime_s = round(time.perf_counter() - t0, 3)
        return ImageResult(image_id=image_id, width=w, height=h, findings=kept, dropped_findings=dropped,
                           missing_information=missing, meta=meta, **merged)
