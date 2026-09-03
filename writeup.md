# Sokhda kharif 2025: a final yield forecast from six Capella X-band passes

**Six acquisitions, 966 plots, no ground truth. So we wrote our predictions down before we
looked, and nine of seventeen were wrong.**

## What the data actually is

`Sokhda_Farms.shp` holds 966 polygons, every one reading `VILLAGE = 'Sokhda'`, `ID_1 = 22`.
The Overview promises an expanded set of villages; the shapefile holds one polygon over the
same plots as Round 2. It says the crop classification is carried forward; the shapefile has
five fields and none is a crop, so we re-derived it. We would rather say that than write
around it. One village makes the village table a single row, so we add a 500 m zone grid.
Median plot 0.27 ha, and ten enclose effectively nothing (< 1e-6 ha); they still get a row,
and area weighting stops them voting.

The stack is six Capella X-band HH SLCs, 6 Jun to 12 Nov 2025, and one of them fights you.
T5, on 29 October, is **right-looking** at view azimuth 318.4° where every other pass views
from about 135°, a 01:37 IST pass at maximum canopy dew three days after 63.1 mm of rain.
Uncorrected, it looks like a growth flush in a season that is ending.

## Ingest, and two things the geometry told us

Calibration follows each scene's own metadata — `beta0 = |I+jQ|²·sf²`,
`sigma0 = beta0·sinθ − NESZ`, `gamma0 = sigma0/cosθ` — and geocoding is
`gdal.Warp(rpc=True, errorThreshold=0.0)` onto a per-scene terrain height fitted against the
vendor preview.

The six heights land on **−17.34 m, spread 0.89 m**, but how they got there matters more. A
height error displaces a pixel along ground range, so a right-looking scene must displace
opposite to a left-looking one — and T5's offsets alone run negative. Nothing was fitted to
make that happen, and it is our strongest evidence the height is terrain.

T5 then broke the co-registration matcher at 108 m against Capella's ~5 m CE90. We diagnosed
before fixing: its correlation peak is a third of the stack's and nearly flat, because at 1 m
the edges a phase correlator keys on *are* shadow and layover, which swap sides under a
reversed look. A two-scale search registers all six to 0.06–1.48 m.

## Radiometric normalisation: T6 is offset, T5 cannot be

Invariant targets are chosen on 8 m block averages from T1–T3, then scored on T4 and T6, which
took no part in choosing them: **4.01 dB apart before correction, 0.27 after**.

T6 carries a flat **+4.28 dB** across the scene's 39 dB brightness range, and since no surface
process has a flat signature — harvest darkens fields and leaves roofs alone — this is the
sensor, not the season. T5 refuses it: its residual changes sign, −3.5 dB on dark targets to
+2.3 dB on bright, because rain brightens rough dark surfaces while the reversed look
extinguishes the dihedrals that make built-up bright. No constant undoes two opposite
mechanisms, so **T5's level is never used**, replaced by the T4–T6 interpolation.

Its *residual* we keep: 63 mm of rain on 966 plots is a soil-moisture experiment nobody paid
for. We predicted it would rank the cohorts by soil exposure, bajra brightest. It does not —
medians run +0.36 dB on bajra to +0.82 on maize — so the T5 anomaly stays a weak covariate.

## The canopy sign was pre-registered, and it was wrong

Four of the five crops are *darkest* at what looks like peak canopy, which reads as the canopy
attenuating the surface return. We wrote that into a constant above the code that opens the
optical file — `{Rice: +1, Cotton: −1, Maize: −1, Bajra: −1, Groundnut: −1}` — and have not
edited it since.

Sentinel-2 lands on a Capella date twice, 13 Oct and 12 Nov, both under 0.1 % cloud, and the
decisive form is the *difference* on both instruments, because plot size, soil texture and row
orientation cancel. T5's only candidate was 79.1 % cloud, so no T5 control exists.

**The measured sign is +1 on all five crops**, rho = +0.569 over n = 813 at p = 8.1e−71,
+0.334 to +0.705 per crop. That p assumes independent plots, which our own Moran's I says they
are not, so the honest version is a 500 m block bootstrap: **[+0.508, +0.618]**. Greener is
brighter here. We were wrong on four crops of five, because nothing in a SAR stack separates
"canopy attenuating the surface" from "surface that is smooth that week". Our sign-agnostic
`|departure|` scores −0.085 — not conservative but empty — so `phenology.py` was rebuilt.

The same test refused the per-plot harvest date we had promised — plots the SAR called
"standing" were the *least* green, one-sided p = 1.00 — so we replaced it with
`cleared_fraction`, monotone against the optical change at rho = **−0.529** (n = 479,
p = 6.9e−36).

## The model

    Y_final(plot) = Y_ref(crop, 2025) × a(season-complete canopy integral)

**One modulation term, not three.** Round 2 measured its own problem: within a cohort its
health index and yield estimate correlated at exactly 1.000, one ranking wearing two names.
The integral is *signed*, scoring +0.564 against clipped's +0.472 — and because we chose the
form on those scores, 13 Oct and 12 Nov cannot then validate it, which is what the reserved
scenes are for. Signing it also fixes a degeneracy that left 80.6 % of bajra on the median.

`Y_ref` is the season's official estimate, the 3rd Advance Estimates and the latest published,
and it inverted our planning assumption. Sokhda's monsoon measured 1098.5 mm against a
1995–2024 mean of 923.1 mm (z = +0.66), so we had planned to adjust last year's yield upward. DA&FW says the opposite: Gujarat kharif **rice and bajra hit five-year lows**,
−29 % and −26 %, in an *excess*-rain season — the Narmada overflowed 16–18 September, inside
the paddy grain-fill window. Had we applied that elasticity we would have forecast rice above
a reference the state measured 29 % below. No district uplift is applied either, leaving maize
and cotton conservative by a known sign.

Projection past 12 November is **flat, not decaying**, and fires on cotton alone at 56 %
projected canopy-days; the other four are closed by observation, where Round 2 discounted
cotton by a hand-set 0.45. Our own bound moves the total under a percent across 0.15–0.45.
Take the radar out, `a() ≡ 1`, and the total is **910.1 t** — 1.8 % away, but the median plot
moves **11.8 %**: the term redistributes, it does not set the level.

## Validation is the deliverable

**The back-test is the headline, and it is negative.** We fit on T1–T4, predict the withheld
12 November pass, on Round 2's four-date labels so nothing about November leaks. Our decaying
projection first scored **+0.284** against persistence, a number we quote nowhere else: it
predicts a higher canopy and T6 sits +1.65 dB above T1 district-wide, so it could win by
offsetting a drift neither predictor models. Handed that drift it scores **−0.409**, so we
shipped the flat hold, at **−0.119 [−0.280, +0.022]**.

So **the shipped rule does not beat persistence at 30 days**, and scores −0.216 where it
fires. At 60 days it scores **+0.140**, so the loss is phenological rather than temporal: it
fails where the harvest has happened, and a crop calendar is what fixes that. Per crop it
helps bajra (+0.352) and groundnut (+0.213) and hurts maize and rice, both still carrying
canopy on 12 November.

**Reproducibility found two defects, and the second was ours.** The same notebook on Kaggle
reproduced every SAR number and then disagreed about 39 plots: the tier-2 axis had been the
November canopy *clipped at zero*, so 403 of 793 allocated plots sat at exactly 0.0 and sort
order alone decided the bajra/maize cut. The signed departure separates that block across 392
values, and one machine could never have shown us. We then reported the re-ranking confirmed —
and our own audit found the ANOVA still residualising against the axis from before the fix.
Corrected, tier-2 labels carry **no** optical information beyond their own axis (η² 0.0023,
p = 4.29e-01) while the tier-1 control does (p = 0.005). The control passing makes the failure
readable: tier 2 is an *allocation*, which is what we call it.

**Reserved optical.** We reserved 12 Dec 2025 and 16 Jan 2026 from the first fetch, and an
assertion fails the run if any module but the validator names them. Cotton's December NDVI is
**0.690 against 0.474–0.532**, one-sided p = 1.26e-11: a SAR-only label picked the right plots
on a scene it had never seen, and cleared plots are under rabi rather than bare, so this is
not measuring "good field".

**An independent instrument.** Nothing here observed the window in which we hold cotton flat,
so we found something that did: 16 free Sentinel-1 passes, feeding no feature, label or
forecast. Cotton is the only cohort above its own June soil after 12 November, *rising*
**+0.985 dB** to 21 December, so the flat hold is not optimistic. The same data prices this
competition's premise: a 6-pass integral ranks plots as a 13-pass one does, rho **+0.915**.

**Controls.** Row direction, a PCA on each parcel's ring over n = 650, does not drive that
anomaly: rho = −0.051, p = 0.195, inside the ±0.2 threshold set beforehand. Moran's I on a
999-permutation null leaves a within-crop residual of **+0.151, p < 0.001**, so structure
survives the crop label.

## Aggregation, and the numbers

**893.9 t forecast at harvest over 447.5 ha, 2.00 t/ha area-weighted.**

| crop | plots | ha | t/ha | tonnes |
|---|---:|---:|---:|---:|
| Groundnut | 341 | 124.7 | 2.66 | 331.7 |
| Maize | 313 | 139.6 | 1.96 | 273.7 |
| Rice | 111 | 76.0 | 1.69 | 128.2 |
| Bajra | 139 | 61.8 | 1.40 | 86.6 |
| Cotton | 62 | 45.5 | 1.62 | 73.8 |

The village row sums the shipped plot file, rounded once *before* aggregating after
`cross_check` caught a 0.0015 t discrepancy, and the 46-cell grid spreads **1.50–2.80** t/ha.
The rollup is gated on the village *geometry*, not its name: 962 of 966 plots agree with the
attribute and none disagree, and all 447.5 ha sits inside a boundary enclosing 1174.1 ha, so
we report **38.1 % of Sokhda**.

**What that total is worth.** We priced five sources by re-running the chain under each: the
state reference at a stated ±10 %, **±89.4 t**; the district crop mix that allocates three of
five cohorts, **±61.5 t**; Round 2's labels, ±6.8 t; speckle, ±2.7 t; tie ordering, ±0.0 t.
The mix is the one row we can score against itself, because rice and cotton are assigned by
threshold and not by it: it overstates both, 0.26 against our 0.170 and 0.32 against 0.102,
and the spread of those log-ratios sets the perturbation. **External assumptions sum to
150.9 t; the radar contributes 9.5 t.** Somebody else's numbers set where the line falls *and*
how big three of five cohorts are.

## What we do not claim

**153 of the 966 plots are not fully observed**: 82 interpolated from their own dates and 71
imputed from their eight nearest measured neighbours, with `data_quality` per plot. The
back-test scores only the 813 measured; Moran's I does not, so part of its positive I is
imputation putting neighbours' values onto neighbours.

Tier-1 labels cover 26.5 % of area, **below Round 2's 31.6 %, a missed target** we did not
meet by loosening a threshold. Median peak canopy is **0.77 dB**: real, corroborated and
small. X-band is said to saturate early, and across six NDVI bins the departure rises
monotonically to **+4.15 dB per NDVI unit** — which says nothing beyond what Sokhda grew.
Plot-level irrigation could produce the same green-and-bright correlation we read as canopy,
and only the scene-level version is ruled out. T5 remains our weakest registration, and our
projection is no better than persistence.
