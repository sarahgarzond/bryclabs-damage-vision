# Damage Photo Labelling Guide

## Purpose

We label 100 damage photos by hand to build a **gold test set**. It measures how accurate, complete and honest our extraction is. These labels are **never used for training or prompt tuning**.

**Golden rule: label only what you can see in the image.** Do not guess causes, history or anything from the claim story. When you cannot tell, say so with `null`, `unknown` or `not_assessable`. An honest "unknown" is a correct label. A confident guess is an error.

Every label uses the gold label schema (`schema/gold_label.schema.json`, same field names as the model output), so evaluation is a field-by-field comparison.

## Image set and work split

| Group | Images | What it tests |
|---|---|---|
| Clear damage | 60 | Extraction accuracy and completeness |
| Ambiguous or poor quality (blur, dark, far away, partial view) | 25 | Uncertainty handling |
| Negatives (no damage, or not a building) | 15 | Invented features (hallucination) |

`scripts/make_images_csv.py` assigns images: 5 calibration images (everyone, excluded from the test set), 20 shared blind images (pairs Olivia+Tugce and Eva+Sarah, 10 per pair) and the rest split evenly with model pre-labels. Label blind shared images **before** your own pre-labelled images.

## Fields and allowed values

**Image level**

| Field | Allowed values | Rule |
|---|---|---|
| `damage_present` | yes, no, unclear | "no" means the visible area is undamaged |
| `image_quality` | good, limited, poor | Limited: usable with gaps. Poor: main area not assessable |
| `quality_issues` | blur, dark, overexposed, too_far, partial_view, obstructed, low_resolution | All that apply |
| `scene` | interior, exterior, not_a_building | |
| `limitations` | free text list | What cannot be judged from this image, e.g. "Cause not assessable" |

**Finding level (one entry per distinct damage)**

| Field | Allowed values | Rule |
|---|---|---|
| `damage_type` | crack, water_stain, mould, flaking_paint, plaster_loss, hole, swelling, rot, rust, scorch, broken_glass, detachment, other | One type per finding |
| `component` | wall, ceiling, floor, window, door, frame, roof, facade, pipe, stairs, other, unknown | |
| `material` | plaster, paint, wallpaper, wood, tile, concrete, brick, glass, metal, plastic, other, unknown | Only when visibly identifiable |
| `location` | short free text | "lower left wall, near window" |
| `visible_traits` | free text list | Observable details: crack pattern, stain colour, edges, tide marks |
| `extent` | small, medium, large, unknown | Small: hand sized. Medium: up to about 1 m. Large: beyond |
| `age_indicators` | tide_marks, multiple_layers, old_repair, mould_growth, corrosion, none_visible | Signs of long-term damage. Indicators only |
| `status` | visible, inferred, not_assessable | See below |
| `uncertain` | true, false | True when you hesitated |
| `bbox` | `[x, y, width, height]` in pixels, or null | Boxed images only |
| `notes` | free text | |

## Status and uncertainty

| Status | Use when | Example |
|---|---|---|
| `visible` | You can point at it | Clear diagonal crack from a window corner |
| `inferred` | Strongly suggested by visible cues, not directly seen | Bubbling paint above a skirting board suggests moisture |
| `not_assessable` | Relevant but the image cannot show it | Whether a ceiling stain is still wet |

- Unknown values are `null` or `unknown`, never a best guess.
- Set `uncertain: true` whenever two values seemed plausible.
- Causes are never findings. "Leaking pipe" is not a label. Water staining with tide marks is.
- The claim story is not evidence. Label the photo as if you had no text.

## Edge cases

| Situation | Rule |
|---|---|
| Stain with a crack through it | Two findings |
| Many small cracks in one area | One finding, "multiple hairline cracks" in `visible_traits` |
| Stain could be water, soot or dirt | `other`, `uncertain: true`, options in `notes` |
| Dark patch could be mould or shadow | Label only if texture or spotting is visible, else `damage_present: unclear` |
| Line could be crack or paint edge | `crack`, `status: inferred`, `uncertain: true` |
| Damage partly outside the frame | Label it, add `partial_view` |
| Old visible repair | Not a finding. `old_repair` in `age_indicators` of the nearby finding |
| Normal wear (scuffs, faded paint) | Not damage |
| View blocked | `obstructed` |
| Screenshot, collage, heavy filter | `image_quality: limited`, describe in `limitations` |
| Not a building | `scene: not_a_building`, `damage_present: no`, no findings |

Add new cases here when you find them and tell the team.

## Bounding boxes

Boxes on 30 images: the 20 shared blind images plus 10 clear images (`boxed = yes` in `data/images.csv`).

- One tight box per finding around its full visible extent. Pixels `[x, y, width, height]` from the top left of the original image.
- In the labelling app, click top left then bottom right and paste the `"bbox"` line.
- Many small cracks in one area: one box around the area. `inferred`: box the cue. `not_assessable` and negatives: `null`.

## Worked examples

Clear damage (ceiling water stain):

```json
{
  "image_id": "img_001", "damage_present": "yes", "image_quality": "good", "quality_issues": [],
  "scene": "interior",
  "findings": [{
    "damage_type": "water_stain", "component": "ceiling", "material": "paint",
    "location": "centre right ceiling, next to light fitting",
    "visible_traits": ["brown discoloration", "darker concentric rings"], "extent": "medium",
    "age_indicators": ["tide_marks"], "status": "visible", "uncertain": false,
    "bbox": [412, 120, 380, 300], "notes": null
  }],
  "limitations": ["Cause not assessable", "Whether the stain is still wet not assessable"]
}
```

Ambiguous (blurry, dark wall corner):

```json
{
  "image_id": "img_002", "damage_present": "unclear", "image_quality": "poor", "quality_issues": ["blur", "dark"],
  "scene": "interior",
  "findings": [{
    "damage_type": "crack", "component": "wall", "material": "unknown", "location": "upper left, near corner",
    "visible_traits": ["thin dark line, possibly a crack or paint edge"], "extent": "unknown",
    "age_indicators": ["none_visible"], "status": "inferred", "uncertain": true, "bbox": null,
    "notes": "Request a sharp close-up in daylight"
  }],
  "limitations": ["Image too blurry to confirm damage", "Material not identifiable"]
}
```

No damage:

```json
{"image_id": "img_003", "damage_present": "no", "image_quality": "good", "quality_issues": [],
 "scene": "interior", "findings": [], "limitations": ["Only the visible wall section was assessed"]}
```

## Quality control

1. Calibration round: all four label the same 5 images, compare for 15 minutes, update the edge cases.
2. Label blind shared images before own images.
3. `scripts/agreement.py` computes Cohen's kappa on the shared images.
4. Adjudicate disagreements in pairs, save the agreed label in `labels/adjudicated/`, log the reason.
5. Spot check 5 of another person's pre-labelled images.
6. `scripts/merge_gold.py` builds `labels/gold/`. Commit it **before** comparing any model result.

Before saving each image: every finding can be pointed at (or is `inferred`), no cause as a finding, unknowns are `null`/`unknown`, status and `uncertain` filled, limitations listed, box drawn if boxed.
