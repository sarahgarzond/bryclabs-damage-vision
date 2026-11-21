"""Claim readiness: what is established, what is only indicated, what is missing.

Rule based on purpose: every statement here is traceable to a field in the extraction. It never
says whether a claim is covered. That is the policy check and human review downstream.
"""
from __future__ import annotations

import re
from typing import Optional

from .schema import ImageResult

# keywords in the claimant's text -> damage types that would visually support them
REPORTED_EVENTS = {
    "water": (r"water|leak|flood|wet|pipe|burst|wasser|feucht|rohr", {"water_stain", "mould", "swelling", "rot", "flaking_paint"}),
    "mould": (r"mou?ld|schimmel", {"mould"}),
    "crack": (r"crack|riss|split", {"crack"}),
    "fire": (r"fire|smoke|soot|burn|brand|feuer|rauch", {"scorch"}),
    "storm": (r"storm|wind|hail|sturm|hagel", {"broken_glass", "detachment", "hole"}),
    "break-in": (r"break.?in|burglar|einbruch", {"broken_glass", "hole"}),
}


def assess(result: ImageResult, claimant_text: Optional[str] = None) -> dict:
    established, indicated, missing, requests, consistency = [], [], [], [], []

    for f in result.findings:
        label = f"{f.damage_type.value.replace('_', ' ')} on {f.component.value}"
        if f.status.value == "visible" and not f.uncertain and (f.confidence or 0) >= 0.7:
            established.append(f"{label} ({f.extent.value} extent, confidence {f.confidence:.2f})")
        else:
            why = "inferred" if f.status.value == "inferred" else "uncertain"
            indicated.append(f"{label} ({why}, confidence {f.confidence or 0:.2f})")
        if f.material.value == "unknown":
            requests.append(f"Close-up of the {label} so the material can be identified")
        if f.extent.value == "unknown":
            requests.append(f"Wider shot showing the full extent of the {label}")
        if f.uncertain:
            requests.append(f"Sharp, well lit close-up of the {label} to confirm it")
        long_term = [a.value for a in f.age_indicators if a.value != "none_visible"]
        if long_term:
            indicated.append(f"Possible long-term damage indicators at {label}: {', '.join(long_term)}")

    if result.image_quality.value != "good":
        issues = ", ".join(q.value for q in result.quality_issues) or result.image_quality.value
        missing.append(f"Photo quality limits the assessment ({issues})")
        requests.append("Retake the photo in daylight, closer, without blur")
    if result.damage_present.value == "unclear":
        missing.append("Damage could not be confirmed from this photo")
    missing.extend(result.limitations)

    if claimant_text:
        found = {f.damage_type.value for f in result.findings}
        for event, (pattern, supporting) in REPORTED_EVENTS.items():
            if re.search(pattern, claimant_text, flags=re.I):
                if found & supporting:
                    consistency.append(f"Reported {event}: visual indicators present ({', '.join(sorted(found & supporting))})")
                else:
                    consistency.append(f"Reported {event}: no supporting visual indicator in this photo")

    # dedupe, keep order
    def uniq(xs):
        seen, out = set(), []
        for x in xs:
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out

    return {
        "established": uniq(established),
        "indicated": uniq(indicated),
        "missing": uniq(missing),
        "follow_up_requests": uniq(requests),
        "claim_text_consistency": consistency,
        "note": "Evidence summary only. Coverage is decided by the policy check and human review.",
    }
