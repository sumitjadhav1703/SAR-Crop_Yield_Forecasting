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

Cotton: 0.690 against 0.495–0.532 for the other four, and the only label greener in January
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
