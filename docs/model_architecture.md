# The model

```
Y_final(plot) = Y_ref(crop, 2025-26) · a(season canopy integral)
```

Two terms. That is the whole model, and the smallness is deliberate.

## Why one modulation term and not three

Round 2's chain was `Y_ref · f(health) · a(accumulation) · g(completeness)`, and the plan
for Round 3 was to keep `f` and replace the hand-set `g` with measurement. `f` was dropped
instead.

A vigour index built from the six canopy departures would be built from **the same
measurements the season integral already integrates**. Multiplying the two would count one
measurement twice while presenting itself as two independent lines of evidence, which is
worse than useless under a rubric that scores defensibility. `g` disappears because with six
dates the season integral is either closed by observation or explicitly projected, and the
projected share is reported per plot rather than assumed per crop.

## Term 1 — `Y_ref(crop, 2025-26)`

The published Gujarat kharif yield for **the forecast season itself**, from the DA&FW
Directorate of Economics & Statistics five-year advance-estimates workbook (3rd AE,
2021-22 to 2025-26).

| crop | 2025-26 (kg/ha) | rank in 5 yrs | vs 5-yr mean | basis |
|---|---|---|---|---|
| Rice | 1675 | 5th (lowest) | 71 % | paddy |
| Maize | 2035 | 1st (highest) | 108 % | grain |
| Bajra | 1362 | 5th (lowest) | 70 % | grain |
| Groundnut | 2734 | 4th | 107 % | unshelled pods |
| Cotton | 551 lint → **1621 seed cotton** | 2nd | 98 % | kapas, 34 % ginning outturn |

This inverted the plan's assumption. The plan expected to take a multi-year detrended
average and shift it by a rainfall anomaly derived from free rainfall data. The actual
season estimate is better than a reconstruction of it, and it moves hard: **rice −29 % and
bajra −26 % against their five-year means, maize +38 %**. Kharif 2025 in Gujarat was an
excess-rain season — the state announced flood relief for Vadodara district after the
Narmada overflowed 16–18 September 2025, inside the paddy grain-fill window.

The rainfall anomaly is computed and printed but is **deliberately not used as a
multiplier**: the official estimate already measures the outcome, and multiplying by an
anomaly on top would double-count it. It appears as corroboration of direction only.

No Vadodara district uplift is applied, because no district-level 2025-26 estimate is
published. Vadodara ranks 1st in Gujarat for maize yield and 2nd for cotton, so those two
forecasts are conservative by a known sign, and that is stated rather than corrected for.

Vadodara kharif is 28.2 % irrigated (CGWB district brochure), which is why a state-level
season effect propagates to these plots at all rather than being buffered away.

## Term 2 — `a(season canopy integral)`

### The measurement

Each plot's **departure from its own June bare soil**: anchor is the mean of 6 and 19 June
(both pre-sowing), scene-level bare-soil drift removed first. Zero means "this plot, at its
own soil". Three canopy dates carry signal — 14 Aug, 13 Oct, 12 Nov — because T5's level is
interpolated and both June dates are the anchor.

`CANOPY_SIGN = +1`, measured, not assumed. See `sar_research.md`.

The season integral is a trapezoid over the observed departures, **signed**, plus a
projection to each crop's calendar harvest:

```
observed  = trapz(signed departure, DOY)
projected = last_clipped_departure × (harvest_DOY − 316)      # FLAT hold
```

Harvest DOY: Bajra 270, Maize 288, Groundnut 305, Rice 310, Cotton 380.

Two choices inside this are measured rather than assumed:

- **Signed, not clipped.** A clipped integral makes a cohort degenerate — 80.6 % of
  bajra sits at exactly the cohort median of zero, so every one of them would receive
  `a = 1.000` and the whole crop would collapse onto `Y_ref`. Signed also scores better against
  optical: **+0.564 against +0.472**.
- **A flat hold, not a decaying limb.** The decaying-limb rule looked more principled and
  scored +0.284 in the back-test. It was an artefact of the +1.65 dB district drift and
  scored −0.409 once every predictor was handed the drift. See `experiments.md`.

`extrapolated_fraction` is reported per plot. Cotton is the only crop with a material
projected share (0.56 mean, 0.75 at p90); every other crop is **closed by observation**.

### The response

`centred_factor(integral, crop, span=0.30)`: a bounded monotone map from the plot's rank
within its own crop cohort to a multiplier in [0.70, 1.30], centred so the **cohort median
lands exactly on 1.0**. The model redistributes within a cohort; it does not move the
cohort. Without centring, the arithmetic quietly drifts a typical plot below its own state
reference before anything has been measured.

`PLAUSIBLE_T_HA` is a raise-on-violation gate, not a clip. A plot outside its crop's band
stops the run rather than being silently pulled back inside it.

## Crop labelling

The five crops are not in the data. Labels are re-derived from the six-date stack by
co-association k-means over 20 seeds, on nine phenology descriptors, in two tiers:

- **Tier 1** — a label a physical threshold supports. Rice from its flood-then-rise
  signature; Cotton from a plot-level rule, `canopy_end_db ≥ 1.5 dB` on 12 November, which
  is the crop still standing when everything else has been cleared.
- **Tier 2** — the district crop mix applied to the residual along the November-canopy axis.
  These labels are **allocated, not measured**, and the shipped table says which is which
  (`crop_confidence`, and `high_confidence_share` in the village summary).

Twelve parcels (12.2 ha) are screened out as **long-duration** — above 1.5 dB over their own
soil on all three canopy dates, which no annual here reaches. See `research_log.md` §S9 for
how that screen's interpretation was falsified and corrected.

Result: 26.5 % of area is tier 1, down from Round 2's 31.6 %, but tier-1 stability rose from
87.9–100 % to 99.4–100 %, and both tier-1 crops are now independently corroborated by
optical data that did not assign them.

## Aggregation

Everything is **area-weighted in hectares**, and production is the true sum
`Σ(yield × area)` rather than a mean of ratios. Plots span 1e-16 to 3.49 ha with a median of
0.27; ten enclose effectively no ground, and area weighting is what keeps them from voting.

The village table is one row, so a 500 m zone grid carries the spatial part of the
aggregation: 46 cells with ≥ 5 farms, covering 946 of 966 farms, spreading **1.50 to
2.80 t/ha around a village figure of 2.00**.

## The answer

**893.9 t forecast at harvest over 447.5 ha, 2.00 t/ha area-weighted.**

| crop | farms | ha | Y_ref | forecast | p10–p90 | production | projected |
|---|---|---|---|---|---|---|---|
| Maize | 313 | 139.6 | 2.04 | 1.96 | 1.50–2.50 | 273.7 t | 0 % |
| Groundnut | 341 | 124.7 | 2.73 | 2.66 | 2.19–3.47 | 331.7 t | 0 % |
| Rice | 111 | 76.0 | 1.68 | 1.69 | 1.24–2.11 | 128.2 t | 0 % |
| Bajra | 139 | 61.8 | 1.36 | 1.40 | 1.20–1.64 | 86.6 t | 0 % |
| Cotton | 62 | 45.5 | 1.62 | 1.62 | 1.19–1.93 | 73.8 t | 56 % |
| **ALL** | **966** | **447.5** | — | **2.00** | 1.36–3.04 | **893.9 t** | 6 % |
