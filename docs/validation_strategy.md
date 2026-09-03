# Validation strategy

There is no ground truth, so validation is not a step after the model — it **is** the
deliverable. Five independent lines, in the order they carry weight.

## 1. Leave-future-out back-test — and it does not go our way

Fit on T1–T4 (6 Jun to 13 Oct, exactly Round 2's data), predict the withheld 12 November
pass, score against what was actually observed. 813 measured plots, 2000-bootstrap CIs,
Round 2's T1–T4-only crop labels so no information about the withheld date reaches any
predictor.

Skill against persistence, on the raw level with the +1.65 dB district drift handed to every
predictor (the control):

| predictor | RMSE (dB) | skill | 95 % CI |
|---|---|---|---|
| B1 persistence | 1.536 | +0.000 | — |
| B2 cohort mean at T4 | 1.719 | −0.253 | [−0.418, −0.117] |
| B3 linear extrapolation | 1.938 | −0.592 | [−0.693, −0.498] |
| **B4 shipped rule (flat hold)** | **1.625** | **−0.119** | **[−0.280, +0.022]** |
| B5 decaying limb (rejected) | 1.823 | −0.409 | [−0.532, −0.303] |

**The shipped rule does not beat persistence.** Its interval contains zero. That is stated
as the headline on the figure and in the write-up rather than buried.

What the back-test does establish is narrower and still worth having:

- the projection is **not worse** than carrying the last observation forward, and it beats
  every alternative that models the limb more aggressively;
- per crop, the flat hold is the best of the five predictors on Bajra (+0.352), Cotton
  (+0.007) and Groundnut (+0.213), and loses to plain persistence on Maize (−0.581) and Rice
  (−0.887). Rice's RMSE of 2.44 dB is by far the worst in the table — paddy's transition out
  of a flooded specular surface is the hardest thing in this stack to extrapolate;
- it **deleted a rule**. See §5.

## 1b. The same back-test at every horizon the stack supports

One point is not a curve, and "the rule does not beat persistence" invites the obvious next
question: at what range does it stop working? `backtest.horizon_curve` runs the same
experiment at both splits the six dates admit, on the departure target, where the scene-level
bare-soil drift is already removed per date.

Label-free predictors only. Round 2's labels have seen T4, so at a hold-T3-predict-T4 split
they leak the target. Dropping them also removes B4's calendar-harvest zeroing, so the 30-day
row below is **not** the shipped −0.119 — it is the same rule with its calendar taken away.

| fit | predict | days | predictor | RMSE (dB) | skill | 95 % CI |
|---|---|---:|---|---:|---:|---|
| T3 | T4 | 60 | persistence | 1.553 | +0.000 | — |
| T3 | T4 | 60 | **flat hold, no calendar** | **1.440** | **+0.140** | **[+0.071, +0.202]** |
| T3–T4 | T6 | 30 | persistence | 1.217 | +0.000 | — |
| T3–T4 | T6 | 30 | **flat hold, no calendar** | **1.322** | **−0.180** | **[−0.330, −0.056]** |
| T3–T4 | T6 | 30 | linear extrapolation | 1.611 | −0.751 | [−0.895, −0.610] |

**The pre-registration was that skill would be non-positive everywhere and decay with
horizon. It is positive at the longer horizon and negative at the shorter one, and neither
interval contains zero.** Ledger entry 14.

The mechanism is phenological rather than temporal, and it argues *for* the shipped design.
The 60-day row predicts 13 October, inside the growing season, where refusing to let a
departure fall below its own soil is the right behaviour. The 30-day row predicts 12
November, after most of the harvest, where the same refusal is exactly wrong — and what
removes it is the calendar-harvest zeroing this label-free variant had to drop. So the curve
does not measure skill against horizon *length*; it measures skill against what is being
predicted, and it says the flat hold is a good rule for a standing crop and a bad one for a
harvested field. That is why the shipped rule carries a crop calendar.

Note also that T1 and T2 cannot anchor a horizon: they *are* the June anchor, both
pre-sowing, so there is no canopy to persist and no `departure_T1` exists to carry forward.

## 2. Held-out optical

Two Sentinel-2 scenes reserved from the start — 12 December 2025 and 16 January 2026 — read
by nothing upstream, enforced by `assert_reserved_unread()` on every run.

They cannot score the yield forecast: both are post-kharif and inside the rabi window, so
December NDVI over a harvested paddy plot is a rabi crop. They can settle one thing, and it
was pre-registered:

| claim | outcome |
|---|---|
| Cotton is the greenest of the five on 12 December | **PASS**, one-sided p = 1.26e-11 |
| The long-duration parcels are greener than the population in December **and** in June | **FAILED on June** |
| (negative control) Plots cleared by 12 Nov are under rabi in December, not bare | **holds** |

Cotton: 0.690 against 0.474–0.532 for the other four, and the only label greener in January
than December. The label is a SAR threshold on 12 November — and, corrected 2026-08-31, that
threshold's *value* was informed by the October-to-November optical banding
(`crop_type.py:234-237`, and `docs/leakage_analysis.md`). What the December scene tests is
therefore a SAR-only rule against a date nothing upstream had opened, which is the claim that
matters. What it does not test is whether 1.5 dB is the right cut; `cotton_sensitivity` prices
that separately.

The negative control matters as much as the test. Had cleared plots been bare in December,
the first claim would have been measuring "good field" rather than "still-standing cotton".
They are not bare — 0.488 against a population 0.520.

The failed claim is in §5.

## 3. Confound controls, declared before they were run

- **Look direction.** T5 is the only right-looking pass, and a row-orientation effect
  reverses with look direction. Row azimuth is estimated as the PCA principal axis of each
  parcel's exterior ring; on the 650 parcels elongated enough for that to mean anything,
  `rho(angle to look, t5_anomaly) = −0.051` and `rho(cos 2Δ, t5_anomaly) = +0.051`, both
  p = 0.195, both inside the ±0.2 threshold set beforehand. Clean.
- **Diurnal / dew.** T5 is a 01:37 pass and T1 is midday. Handled by the persistent-scatterer
  scene offsets rather than argued about; held-out left-looking dates sit 4.01 dB apart
  before the offsets and 0.27 dB after, against a 1.5 dB tolerance.
- **Scene moisture in the sign measurement.** T4 and T6 carry near-identical 14-day
  antecedent rainfall (11.9 against 12.2 mm), so the differenced sign test is not measuring
  a wetting event. Plot-level irrigation is **not** excluded and is reported as an open
  caveat.
- **Residual incidence angle.** `gamma0 = sigma0/cos θ` verified on invariant targets across
  28.69–35.24° rather than assumed; what remains is a scene offset, not an angle trend.

## 4. Spatial coherence

Moran's I over 8 nearest neighbours with a **999**-permutation null (the parcel graph is
irregular, so a normal approximation is not safe).

| quantity | I | permutation mean | p | permutations reaching I |
|---|---|---|---|---|
| yield forecast | +0.279 | −0.001 | < 0.001 | 0 / 999 |
| season integral | +0.187 | −0.001 | < 0.001 | 0 / 999 |
| **within-crop residual** | **+0.151** | −0.001 | **< 0.001** | 0 / 999 |

**The `<` is the point, and it was wrong until 2026-08-31.** With the add-one estimator
`(1+r)/(n+1)`, a null of 199 permutations cannot report anything below 1/200 = 0.005 — so the
`p = 0.005` this table used to carry on all three rows was the test's own resolution, not a
measurement. Worse, 0.005 sits above a Bonferroni threshold for the ~30 p-values this run
prints, so the statistic had been fixed below the multiplicity it has to survive. The null is
now 999 permutations, the run prints the exceedance count beside every p, and it prints `<`
when it means `<`. See `AGENTS.md` S23b.

The first two are expected — neighbouring fields share soil, water and management. The third
is the informative one: after conditioning on the crop label there is still real spatial
structure left. Had it been near zero, the residual would be plot-level speckle and the
forecast would be five numbers with noise on top.

## 4b. An independent instrument, used as a witness

`src/s1_audit.py`. Sixteen Sentinel-1 IW RTC passes over Sokhda, 12 June – 21 December 2025,
VV+VH at 10 m, terrain-corrected to gamma0 — the same quantity and the same UTM 43N grid the
Capella chain produces. Free and open Copernicus data, served anonymously by the Microsoft
Planetary Computer and equally available from CDSE and ASF, so it meets the rule that
external data be free to all participants. Cached to `work/s1_cache/` and the per-plot table
ships, so the tests re-run with no network.

**This is not the Sentinel-1 fusion Round 1 rejected.** That decision stands: 27 pixels per
plot at 10 m, and the fusion measured negative on this AOI. What was rejected was C-band as a
per-plot *feature*. This module feeds nothing — no feature, no label, no forecast — and
`tests/test_pipeline.py::test_s1_audit_is_not_imported_by_any_model_module` fails if any
module in the chain imports it. If the village total ever moves when this module is present,
the independence is gone and the change is wrong.

Three claims, written into `s1_audit.PREREG` before a single Sentinel-1 pixel was read.

**P14 — the projection audit, and it is the one that matters.** The shipped model holds
cotton's canopy flat from 12 November to its calendar harvest at DOY 380. That assumption
carries 56 % of cotton's canopy-days and 73.8 t, and **nothing else in this submission
observes that window at all** — the last Capella pass is the last observation of any kind.
Sentinel-1 flew on 15 Nov, 27 Nov, 9 Dec and 21 Dec.

| cohort | 15 Nov | 27 Nov | 9 Dec | 21 Dec | change |
|---|---:|---:|---:|---:|---:|
| **Cotton** | **+1.741** | **+1.750** | **+1.570** | **+2.726** | **+0.985** |
| Bajra | −1.106 | −0.696 | −1.202 | −0.908 | +0.198 |
| Groundnut | −0.486 | −0.440 | −0.716 | −0.725 | −0.239 |
| Maize | −0.754 | −0.612 | −0.962 | −0.553 | +0.201 |
| Rice | −1.883 | −1.788 | −2.192 | −2.466 | −0.582 |

Cotton is the only cohort above its own June bare soil on any date after 12 November, and it
is 2.2–3.3 dB clear of every other cohort throughout. **Held.** The flat hold is not
optimistic here — C-band says cotton did not decay across the window the model declines to
observe.

What this does *not* establish is that the held level is the right one. A rising cross-pol
return late in cotton can be canopy, boll opening or structural change, and separating those
needs a polarimetry this stack does not have.

Unplanned, and worth more than the test it came from: those 62 cotton plots separate on a
**different sensor**, on dates no module had opened. That is a second independent
corroboration of the tier-1 cotton label, after the reserved December optical at p = 1.26e-11.

**P15 — cross-band sign.** `CANOPY_SIGN = +1` rests on two Sentinel-2 scenes and nothing
else. The 10 Oct → 15 Nov change in C-band VH against the 13 Oct → 12 Nov change in X-band
departure: rho = **+0.248**, n = 813. Positive, so **held** — and far weaker than the +0.569
the same construction scores at X-band against optical, which was stated in advance as the
expected shape. The sign generalises across band and polarisation, and how far it generalises
is now a number instead of an assumption. This is corroboration of the sign, not a second
measurement of it.

**P16 — sampling adequacy, and it prices the competition's own premise.** Six acquisitions
have to carry a season integral. Nothing in the Capella stack can test whether six is enough,
because six is all there is. C-band can: build the integral from every pass over DOY 163–319,
then from only the six passes nearest the Capella dates, over the same span.

rho = **+0.915**, n = 956, median difference **0.27 dB**. **Held** against the pre-registered
0.8. Six acquisitions on this calendar recover the ranking a 13-pass integral gives. The
test needs no ground truth and runs on an instrument that had no part in building the model.

**The honest caveat on all three: these are confirmations, and a confirmation is worth less
than a contradiction.** Two of the three test whether this project's own design choices were
adequate, which is an easier question than the ones the ledger got wrong.

## 5. Things that were killed by their own validation

This is the part that most distinguishes a defensible pipeline from a plausible-looking one,
so it is listed as validation rather than hidden in a changelog.

- **A decaying senescence limb** scored +0.284 against persistence and was going to ship. A
  control built specifically to break it — handing the +1.65 dB district bare-soil drift to
  every predictor — turned it into −0.409. It had been collecting credit for offsetting a
  drift it did not model. Deleted; kept in the ladder as B5 so the comparison stays runnable.
- **A per-plot harvest date** was built, produced a clean-looking categorical
  harvested/standing label, and had **zero** optical support: "standing" plots were the
  *least* green (0.482 against 0.560), p = 1.00. Three canopy samples with a 60-day September
  gap cannot locate a transition. Deleted and replaced with a continuous `cleared_fraction`,
  which validates at rho = −0.529.
- **The sign-agnostic `|departure|` design** scored rho = −0.085 against optical. Measurably
  empty. Rebuilt on the measured sign rather than patched; the rebuilt integral scores
  +0.564.
- **The "orchard or plantation" reading** of the long-duration screen was falsified by the
  reserved June scene. Corrected in place, with the failed prediction recorded.

## What is NOT claimed

- No accuracy against true yield. There is none to measure against.
- No skill statement stronger than "not worse than persistence".
- No district correction to `Y_ref`, because no district 2025-26 estimate exists.
- The tier-2 crop labels are **allocated from the district mix**, not measured, and the
  shipped tables mark them as such.
