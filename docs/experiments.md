# Experiments and ablations

Every row here was run. Nothing is a thought experiment, and the losses are listed with the
wins because the losses are what shaped the model.

## The canopy sign

| design | rho(season integral, optical) |
|---|---|
| `\|departure\|`, sign-agnostic | **−0.085** |
| clipped positive departure | +0.472 |
| **signed departure (shipped)** | **+0.564** |

The sign-agnostic design was the original, chosen deliberately to avoid assuming a sign
before measuring one. It turned out to be measurably empty, and it was rebuilt rather than
patched.

Pre-registered per-crop signs, differenced 13 Oct → 12 Nov on both instruments, n = 813:

| crop | predicted | measured rho | verdict |
|---|---|---|---|
| Rice | + | +0.551 | agrees |
| Cotton | − | +0.569 | **contradicted** |
| Maize | − | +0.647 | **contradicted** |
| Bajra | − | +0.334 | **contradicted** |
| Groundnut | − | +0.705 | **contradicted** |
| ALL | mixed | +0.569, slope +4.93 dB/NDVI | positive on all five |

## The season integral

| variant | outcome |
|---|---|
| clipped at zero | **degenerate** — 80.6 % of bajra at exactly the cohort median of 0, so every one of them got `a = 1.000` and that cohort's p10 = Y_ref |
| **signed (shipped)** | full within-cohort spread; scores +0.564 vs +0.472 |

A related bug found by inspection rather than by a test: mixing a **signed** numerator with
a **clipped** denominator inflated cotton's `extrapolated_fraction` to 0.78, because cotton's
median T3 departure is −1.33 dB and the whole negative excursion was being charged to the
projection. Computing both halves clipped gives 0.52.

## The projection rule — the ablation that changed the model

Skill against persistence, 813 plots, 2000-bootstrap CIs:

| rule | raw level | with drift control |
|---|---|---|
| B1 persistence | +0.000 | +0.000 |
| B2 cohort mean at T4 | −0.310 | −0.253 |
| B3 linear extrapolation | −0.408 | −0.592 |
| **B4 flat hold (shipped)** | −0.144 | **−0.119** |
| B5 decaying limb | **+0.284** | **−0.409** |

B5 was the intended shipped rule. It looked more principled than a flat hold, it scored
+0.284, and the CI excluded zero. The control was built because the result was suspicious in
a specific way: B5 predicts a **higher** canopy than persistence does, and the district
bare-soil level rises +1.65 dB between June and November, so B5 could be winning by being
biased in the direction that happens to offset a drift neither predictor models. Handing
every predictor the drift removed that route to a win, and B5 collapsed to −0.409.

Restricted to plots where the rule actually changes the answer (732 of 813), the flat hold
scores −0.216; on the 81 where it is silent it is identical to persistence by construction.

Per crop, on the departure target:

| crop | n | model RMSE | skill [95 % CI] | best |
|---|---|---|---|---|
| Bajra | 142 | 0.978 | +0.352 [−0.004, +0.559] | flat hold |
| Groundnut | 221 | 1.125 | +0.213 [−0.114, +0.456] | flat hold |
| Cotton | 92 | 1.338 | +0.007 [−0.041, +0.065] | flat hold |
| Maize | 251 | 0.926 | −0.581 [−1.129, −0.208] | persistence |
| Rice | 107 | **2.438** | −0.887 [−1.695, −0.326] | persistence |

Rice is the worst-predicted crop in the stack by a wide margin, and that is physically
legible: paddy's exit from a flooded specular surface is a large, fast, plot-specific
transition.

## Harvest detection

| approach | outcome |
|---|---|
| per-plot harvest DOY, backward search to the plot's own soil | **deleted** — "standing" plots were the *least* green on the reserved scene (0.482 vs 0.560), p = 1.00, no stratified separation at any threshold |
| **continuous `cleared_fraction` = 1 − canopy(T6)/canopy_peak** | **shipped** — rho = −0.529 against held-out optical |

The root cause is structural, not a tuning failure: three canopy samples with a 60-day
September gap cannot locate a transition date. A categorical label built on that gap looks
like information and is not.

Sensitivity to `MIN_CANOPY_DB`:

| threshold | plots with a canopy | median cleared |
|---|---|---|
| 0.25 dB | 669 | 0.632 |
| **0.50 dB (shipped)** | **588** | **0.625** |
| 1.00 dB | 389 | 0.613 |

The median clearing fraction barely moves across a 4× change in threshold, which is what a
robust measure looks like.

## Crop labelling

| | Round 2 (4 dates) | Round 3 (6 dates) |
|---|---|---|
| tier-1 area | 31.6 % | 26.5 % |
| tier-1 stability across clustering setups | 87.9–100 % | 99.4–100 % |
| tier-1 crops corroborated by independent optical | — | both |

Tier-1 coverage went **down** and the labelling got better. Round 2's cotton included the
long-duration parcels; removing them cost area and bought a label that survives a held-out
test at p = 1.26e-11.

Cotton moved from a cluster-level z-score to a plot-level absolute threshold on the November
canopy. Sensitivity to `COTTON_NOV_DB`:

| threshold | plots | area | share |
|---|---|---|---|
| 1.0 dB | 132 | 79.2 ha | 17.7 % |
| **1.5 dB (shipped)** | **57** | **39.3 ha** | **8.8 %** |
| 2.0 dB | 36 | 28.7 ha | 6.4 % |

This is the least stable threshold in the pipeline and it is reported as such. 1.5 dB is
three times the 0.5 dB plot-to-plot soil spread measured on the two June dates that cannot
contain a canopy, which is the anchor it is set from — not from the resulting area.

Agreement with Round 2's labels is 40.9 % overall and 91 % on rice. The disagreement is in
the expected direction.

## The reference yield

| approach | outcome |
|---|---|
| plan: multi-year detrended mean, shifted by a rainfall anomaly | **replaced** |
| **shipped: the published estimate for the forecast season itself** | rice −29 %, bajra −26 %, maize +38 % against their five-year means |

The plan intended to reconstruct the season effect. The season effect is published. The
rainfall anomaly is still computed and printed, as corroboration of direction, but is
explicitly **not** used as a multiplier — the official estimate already measures the
outcome, and multiplying would double-count it.

## Rejected without building

- **Sentinel-1 fusion** — 0.27 ha median plot is ~27 pixels at 10 m; Round 1 measured the
  fusion as negative on this AOI. (Also a user decision.)
- **SoilGrids** — 250 m over a 5.9 × 4.7 km AOI is ~24 × 19 pixels.
- **CNN / transformer / ensembling** — no label to fit, no out-of-fold estimate to weight
  by. Building one would be modelling theatre and would cost points under Plausibility.
- **A double-logistic phenology fit** — three canopy samples cannot constrain four
  parameters.
