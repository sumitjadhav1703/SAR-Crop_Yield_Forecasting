# Leakage analysis

There is no label, so the classic leak — a target quantity reaching a feature — cannot
occur in the usual form. Three other forms can, and all three are live in this project.

## 1. Optical leakage into a claim of optical validation

Sentinel-2 is the only external check on any SAR-derived quantity here. If optical data
enters a decision and then validates it, the validation is circular.

**What optical DID set, and is therefore disqualified from validating:**

- the **canopy sign** (`phenology.CANOPY_SIGN = +1`), arbitrated by the same-day 13 Oct and
  12 Nov scenes;
- the tier-2 assignment axis in `crop_type`, checked against 13 Oct NDVI.

**What optical also touched, corrected 2026-08-31.** An audit of this document against the
modules it describes found two entries below the wrong heading. Both are recorded here rather
than quietly moved, because a leakage analysis that is wrong about leakage is worse than none:

- **the season integral's functional form.** `phenology.py:68-72` chooses the *signed*
  departure over the clipped one because "scored against optical the signed form reaches
  rho=+0.564 against +0.472 for the clipped-positive form, and it is the better of the two on
  four of the five crops". That is a selection made against 13 Oct / 12 Nov NDVI, and
  `canopy_sign.report()` then prints the same correlation as support for the choice. The
  integral is the **only** per-plot term in the forecast, so this is the most consequential
  entry in this document. The three scores (−0.085 absolute, +0.472 clipped, +0.564 signed)
  were always published; what was wrong was filing the integral as optically untouched.
  It is disqualified from being validated by 13 Oct or 12 Nov. It is **not** disqualified from
  the reserved December and January scenes, which is why they exist.
- **`COTTON_NOV_DB = 1.5`.** `crop_type.py:234-237` already disclosed this in the module —
  "the optical banding above was inspected before this constant was fixed. The optical
  agreement at 1.5 dB specifically is therefore corroboration, not an independent test of that
  value" — and this document contradicted its own source. The threshold was informed by the
  T4→T6 NDVI *banding*, not fitted to December NDVI, so the reserved-scene cotton test
  (p = 1.26e-11) still scores a label on a scene never seen. It is corroboration of a
  well-chosen threshold, not proof that 1.5 dB is the right number.

**What optical did NOT touch, and can therefore test it:**

- `LONG_DURATION_MIN_DB = 1.5`, set from cotton's 90th percentile in SAR;
- the accumulation response `a()` and its bound `ACCUM_SPAN`;
- `Y_ref` and the forecast's level, which come from DA&FW state statistics;
- every decision in the ingest chain: calibration, geocoding, co-registration, the scene
  offsets, and all three Phase 1 gates.

**Two scenes are reserved outright**: 12 December 2025 and 16 January 2026. They are fetched
by `s2_ndvi` and read by `validate` and `figures` and by nothing else.
`validate.assert_reserved_unread()` greps every `src/*.py` for `ndvi_R1` / `ndvi_R2` and raises
if any other module names them, on every shipped run.

**What that check is and is not, corrected 2026-08-31.** This document called it "enforced, not
promised". That overstates it. It is a **source lint**, and its limits are worth stating because
a reader will find them anyway: it matches one spelling of two column names; it would not catch
an f-string access such as `df[f"ndvi_{code}"]` (which `validate.py` itself uses), nor the
unprotected `ndvi_cov_R1` / `ndvi_date_R1` / `ndvi_scene_R1` columns, nor a whole-frame read of
`work/farm_ndvi.csv`, which physically contains the reserved columns. It globs `src/*.py` only,
and it runs at step 12 of 14, so it annotates a violation rather than preventing one.

What actually keeps the reserved scenes clean is not the lint: it is that the fetch is the last
thing `s2_ndvi` does, that no module upstream of `validate` names or joins them, and that the
development log records the reservation before the scenes were fetched. The lint is a guard
against future edits, and it is worth exactly that much.

**The honest limit of the reserved scenes.** December and January are post-kharif and inside
the rabi window — Gujarat rabi sowing runs mid-October to end-November. December NDVI over a
harvested paddy plot is a rabi crop, so correlating the kharif forecast against it would
measure whether a field is a good field, not whether the forecast is right. They can test
exactly one thing well: which plots still carry a **kharif** crop after everything else has
finished. Of the five, only cotton is picked into January.

That claim is scored, with its own negative control: if plots cleared by 12 November had
turned out to be bare in December, the reserved scene would be measuring kharif after all
and the reading would be wrong. They are not bare (0.488 against a population 0.520) — they
are under rabi, which is what the reading requires.

## 2. Temporal leakage into the back-test

The leave-future-out back-test fits on T1–T4 and predicts the withheld T6. Anything derived
from T6 that reaches a predictor destroys it.

- The crop labels used in the back-test are **Round 2's**, derived from T1–T4 alone. Round
  3's own labels read T6 (`canopy_end_db`, `d46`) and are therefore ineligible.
- Only `measured` plots are scored. An imputed plot's "observation" at T6 is a neighbour's,
  so scoring it would score the imputation.
- The June anchor is used to re-express departures as levels. It is June-only, so it adds no
  knowledge of November.

A subtler one was found and fixed. Scoring on the raw level, the decaying-senescence-limb
rule (B5) scored **+0.284** against persistence and looked like a win. It was not: the
district bare-soil level rises +1.65 dB between June and November, B5 happened to predict a
higher canopy than persistence did, and it was collecting credit for offsetting a drift
neither predictor modelled. A control (`level_driftaware`) that hands **every** predictor
the same +1.65 dB turned B5's score into **−0.409**. B5 was deleted from the shipped model
and kept in the ladder so the comparison stays runnable.

## 3. Selection leakage into a threshold

Any threshold chosen by looking at the thing it will later be reported against is fitted,
not measured. Two guards:

- `canopy_sign.EXPECTED_SIGN` is written **above** the code that opens the optical
  reference, and was never edited after the measurement. Four of its five predictions were
  contradicted, and the contradiction is the reported finding.
- Every threshold is shipped with a sensitivity sweep, printed by the run:
  `crop_type.cotton_sensitivity` over `COTTON_NOV_DB` ∈ {1.0, 1.5, 2.0} and
  `phenology.clearing_sensitivity` over `MIN_CANOPY_DB` ∈ {0.25, 0.5, 1.0}. A threshold
  whose result only exists at one value is visible as such.

## 3b. A second instrument, and the rule that keeps it outside the model

`src/s1_audit.py` reads 16 Sentinel-1 passes over the same plots. A validation instrument is
only independent for as long as nothing in the model touches it, and "nothing touches it" is
a claim that decays silently — a single convenient import a week from now would leave every
number in section 4b of `validation_strategy.md` looking exactly as good as it does today
while meaning nothing.

So it is enforced rather than asserted:

- `tests/test_pipeline.py::test_s1_audit_is_not_imported_by_any_model_module` scans every
  module in `src/` and fails if any of them names `s1_audit`. `pipeline.py` is the single
  exemption, because it is the runner: it calls the report *after* the forecast is already
  computed and passes nothing back.
- The module runs last in the chain, after `submit`. If a C-band column ever reached a
  feature, a label or the forecast, the village total would move — so the shipped headline
  is itself a check on this.

**What this does not guard.** The exemption is real: `pipeline` could be edited to thread a
value from `s1_audit` back into the forecast, and the test would still pass. That is the same
class of limitation as `assert_reserved_unread`, which is a lint over source text rather than
a runtime capability check, and it is stated here for the same reason — a guard described as
stronger than it is, is worse than no guard.

**On the direction of the P16 result.** The sampling-adequacy test compares a 6-pass integral
against a 13-pass integral *on C-band*. It says six acquisitions on the Capella calendar
recover a dense integral's ranking **for a C-band series over these fields**. It does not
prove the same for X-band, which has a shallower penetration and a different dynamic range,
and the write-up does not claim it does.

## 4. What is NOT claimed

- The Y_ref term is a published state figure, not a fit. It moves every plot in a cohort by
  the same factor and can carry a state-level error straight into the answer. That is a
  stated assumption, not a validated one.
- Plot-level irrigation on 12 November cannot be separated from plot-level canopy in the
  sign measurement. Scene-level moisture is excluded (T4 and T6 carry near-identical 14-day
  antecedent rainfall, 11.9 against 12.2 mm), but per-field irrigation is not, and it is
  recorded as an open caveat rather than argued away.
