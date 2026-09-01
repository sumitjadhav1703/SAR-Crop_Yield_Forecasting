# Sokhda kharif 2025: a final yield forecast from six Capella X-band passes

**Six acquisitions, 966 plots, no ground truth. One measured term on a sourced reference —
and the five predictions the data contradicted are in this write-up.**

## What the data actually is

`Sokhda_Farms.shp` holds 966 polygons, every one `VILLAGE = 'Sokhda'`, `ID_1 = 22`. The
Overview says "expanded set of villages"; `Sokhda_Village.shp` holds **one polygon**, over the
same 966 plots as Round 2. It also says the crop classification is carried forward; the farm
shapefile has five fields and **none is a crop**, so we re-derive it. We say so rather than write around it, and supplement the rollup
with a 500 m zone grid: the required village table is one row with no spatial content. Median plot is 0.27 ha; ten degenerate parcels (< 1e-6 ha) carry a row, and area weighting
stops them counting.

The stack is six Capella X-band HH SLCs, 6 Jun–12 Nov 2025. **T5 (29 Oct) is
right-looking** at view azimuth 318.4° where every other pass views from ~135°; a 01:37 IST
pre-dawn pass at maximum canopy dew, following 63.1 mm of rain in three days. Read
uncorrected, it looks like a late-October growth flush in a season that is ending.

## Ingest, and two things the geometry told us

Calibration is `beta0 = |I+jQ|²·sf²`, `sigma0 = beta0·sinθ − NESZ`, `gamma0 = sigma0/cosθ`
on each scene's own metadata; geocoding is `gdal.Warp(rpc=True, errorThreshold=0.0)` onto a
terrain height fitted per scene against its vendor preview.

The six fitted heights converge on **−17.34 m, spread 0.89 m**. A height error displaces a
pixel along ground range, so a right-looking scene must displace *opposite* to a left-looking
one — and T5's offsets alone run negative while all five left-looking scenes run positive.
Nothing was fitted to make that happen: the strongest evidence the height is terrain.

T5 then broke the co-registration matcher, reporting a 108 m shift against Capella's ~5 m
CE90. We diagnosed before fixing: its correlation peak is a third of the stack's and nearly
flat, because at 1 m the edges a phase correlator keys on *are* shadow and layover, which
reverse side under a reversed look. A two-scale search registers all six: 0.06–1.48 m.

Two gates failed; neither was fixed by loosening it. G2 was solved on a window the plots spill
outside; on the plot bounding box, T3 — peak canopy — went from 1.35 m to 0.06 m. G3 failed at
4.26 dB because T6 follows most of the harvest: **it was asking the radiometry to prove the
season had not happened**, replaced by one asking whether the dates agree on targets with no
crop calendar.

## Radiometric normalisation: T6 is offset, T5 cannot be

Invariant targets are selected on 8 m block averages from T1/T2/T3 only, then scored on **T4
and T6, which took no part in choosing them: 4.01 dB apart before correction, 0.27 after.**

T6 carries **+4.28 dB**, flat across the scene's 39 dB brightness range. No surface process
has a flat signature — harvest darkens fields and leaves roofs alone. T5's residual
changes sign, −3.5 dB dark to +2.3 dB bright: rain brightens rough dark surfaces while the
reversed look extinguishes the wall–ground dihedrals that make built-up bright. No constant
undoes two opposite mechanisms, so **T5's level is never used** — it is replaced by the
T4–T6 interpolation.

Its *residual* is kept: the rain is a soil-moisture experiment on all 966 plots at once. We
predicted it would rank the cohorts by exposure, bajra cleared first and brightest. **It does
not** — medians run +0.36 dB on bajra to +0.82 on maize. Soil smoothed by 63 mm of rain is
specular at X-band, so it stays a weak covariate.

## The canopy sign was pre-registered, and it was wrong

Four of the five crops are *darkest* at what looks like peak canopy, which reads as canopy
attenuation of the surface return. We wrote that into a module constant above the code that
opens the optical file — `{Rice: +1, Cotton: −1, Maize: −1, Bajra: −1, Groundnut: −1}` — and
have not edited it since.

Sentinel-2 L2A lands on a Capella date twice, 13 Oct and 12 Nov, both under 0.1 % cloud. The
decisive form is the **difference** on both instruments: plot size, soil texture and row
orientation cancel. The arbiter is luck — twice in six passes, and T5's only candidate was
79.1 % cloud, which is why the T5 control does not exist.

**The measured sign is +1 on all five crops** (rho = +0.569, n = 813, p = 8.1e−71; per crop
+0.334 to +0.705). Greener is brighter here. The pre-registration was wrong for four of five,
because nothing in a SAR stack separates "canopy attenuating the surface" from "surface that
happens to be smooth that week". Our sign-agnostic `|departure|` scores **−0.085** against
that reference — not conservative, empty; `phenology.py` was rebuilt.

The same test refused the per-plot harvest date we promised: plots the SAR called "standing"
on 12 November were the *least* green group (one-sided p = 1.00). Three canopy observations
with a sixty-day gap cannot locate a transition. It was replaced by `cleared_fraction =
1 − canopy(T6)/peak`, monotone against the optical change at rho = **−0.529** (n = 479,
p = 6.9e−36).

## The model

    Y_final(plot) = Y_ref(crop, 2025) × a(season-complete canopy integral)

**One modulation term, not three.** Round 2 measured its own problem: within a cohort its
health index and yield estimate correlated at exactly 1.000 — one ranking under two names. The integral is **signed**, scoring +0.564 against clipped's +0.472 — and we *chose*
the form on those scores, so 13 Oct and 12 Nov cannot also validate it. That is why two scenes
are reserved. Signed also fixes a degeneracy where 80.6 % of bajra sat on the cohort median.

**`Y_ref` is the season's official estimate, and it inverted our planning assumption.**
Sokhda's monsoon measured 1098.5 mm against a 1995–2024 mean of 923.1 mm (z = +0.66), and we
had planned to adjust last year's yield upward. The DA&FW five-year table says the opposite:
Gujarat kharif **rice and bajra recorded five-year lows**, −29 % and −26 %, in an *excess*-rain
season — the state announced relief after the Narmada overflowed 16–18 September, inside the
paddy grain-fill window. Had we applied the elasticity, rice would have been
forecast above a reference the state measured 29 % below. No district uplift is applied, so
maize and cotton are conservative by a known sign.

Projection past 12 November is **flat**, not decaying. Cotton is the only crop it fires on, at
56 % projected canopy-days; the other four are closed by observation, where Round 2 discounted
cotton by a hand-set 0.45. Our own bound moves the total under a percent across 0.15–0.45.

## Validation is the deliverable

**Back-test (the headline, and it is negative).** Fit on T1–T4, predict the withheld 12
November pass, on Round 2's four-date labels so no November leaks. Our decaying projection
first scored **+0.284** against persistence — a number we quote nowhere: it predicts a higher
canopy and T6 sits +1.65 dB above T1 district-wide, so it could win by offsetting a drift
neither predictor models. Handed that drift it scores **−0.409**; we shipped the flat hold, at
**−0.119 [−0.280, +0.022]**.
**The shipped rule does not beat persistence at 30 days**, and scores −0.216 on the 732 plots
where it actually fires. Per crop it helps bajra (+0.352) and groundnut (+0.213) and hurts
maize and rice, both still carrying canopy on 12 November.

**Reproducibility, and the two defects it found.** The same notebook on Kaggle reproduced
every SAR number and disagreed about 39 plots. The tier-2 ranking axis was the November canopy
*clipped at zero*, so 403 of 793 allocated plots sat at exactly 0.0, the bajra/maize cut fell
inside that tied block, and sort order settled it. The **signed** departure separates that
block across 392 values. One machine could not have exposed it.

**Then the test that scored the fix turned out to be broken.** We predicted the re-ranked
cohorts would separate better on optical data and reported it confirmed. An audit of our own
submission found the ANOVA still removing `gamma0_T4`, the axis *before* the fix, through a
default argument in another module. Corrected: tier-2 labels carry **no** optical information
beyond their own axis (η² 0.0023, **p = 4.29e-01**) while the tier-1 control does (p = 0.005).
The control passing makes the failure readable — the test works, and it says tier 2 is an
**allocation**, which is what we call it. The axis change stands on the degeneracy it removed.

**Reserved optical.** 12 Dec 2025 and 16 Jan 2026 were reserved from the first fetch, and an
assertion fails the run if any module but the validator names them. Only cotton is picked into
January, and its December NDVI is **0.690 against 0.499–0.532**, one-sided p = 1.26e-11: a
SAR-only label picked the right plots on a scene it never saw. Cleared plots are under rabi,
not bare, so this is not "good field".

**Controls.** Row direction (PCA on each parcel's ring, n = 650) does not drive `t5_anomaly`:
rho = −0.051, p = 0.195, inside the ±0.2 threshold set beforehand. Moran's I on
a 999-permutation null gives a within-crop residual of **+0.151, p < 0.001** — structure
survives the crop label.

**A falsification we kept.** Twelve parcels held ≥1.5 dB above their own soil on all three
canopy dates, and we called them an orchard. December and January confirmed them; **June
refused them, 0.247 against 0.397, p = 1.1e-04** — bare in June, so a long-duration crop, not
one of the five annuals. The operational claim survives.

## Aggregation, and the numbers

**893.9 t over 447.5 ha, 2.00 t/ha.** Groundnut 341 / 124.7 / 2.66 / 331.7 · Maize 313 / 139.6 / 1.96 / 273.7 · Rice 111 / 76.0 / 1.69 / 128.2 · Bajra 139 /
61.8 / 1.40 / 86.6 · Cotton 62 / 45.5 / 1.62 / 73.8 t. The village row is the sum of the shipped plot
file, rounded once *before* aggregating, after `cross_check` caught a 0.0015 t discrepancy;
the 46-cell grid spreads **1.50–2.80**.

The rollup is gated on the village *geometry*, not its name: 962 of 966 plots agree with the
attribute, none disagree. All 447.5 ha sits inside a boundary enclosing 1174.1 ha — the total
covers **38.1 % of Sokhda**.

**What that total is worth.** Five sources, each priced by re-running the whole chain: the
state reference at a stated ±10 %, **±89.4 t**; the district crop mix that allocates three of
five cohorts, **±61.5 t**; Round 2's labels substituted, ±6.8 t; speckle, ±2.7 t; tie
ordering, ±0.0 t. The mix is scored against itself: rice and cotton are assigned by threshold, not by it, and it
overstates both (0.26 against 0.170, 0.32 against 0.102); the spread of those log-ratios sets
the perturbation. **External assumptions sum to 150.9 t; the radar, 9.5 t.** Somebody else's
numbers set where the line is *and* how big three of five cohorts are.

## What we do not claim

**153 of 966 plots are not fully observed**: 82 interpolated from their own remaining dates,
71 imputed from their eight nearest measured neighbours. `data_quality` ships per plot. The back-test scores only the 813 measured; Moran's I does not, so part of its
positive I is the imputation putting neighbours' values on neighbours.


Tier-1 labels cover 26.5 % of area — **below Round 2's 31.6 %, a missed target**, not met by
loosening a threshold. Median peak canopy is **0.77 dB**: real, corroborated,
small. X-band is said to saturate early with biomass; across six NDVI bins here the departure
rises monotonically and the increment does not collapse, ending at **+4.15 dB per NDVI
unit**. Plot-level irrigation could produce the same
green–bright correlation as canopy volume scattering; only the scene-level version is ruled
out. T5 is our weakest registration, and the back-test says the projection is no better than
persistence.
