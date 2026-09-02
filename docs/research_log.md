# Research log

Chronological record of Round 3, stage by stage. Each entry states what was expected before
the measurement was taken, what the measurement said, and what changed as a result. Where a
pre-registered expectation was contradicted, the contradiction is the entry — it is not
rewritten into agreement after the fact.

`AGENTS.md` is the full development log with every intermediate number. This file is the
research narrative: the hypotheses, the sources, and the decisions they forced. The ablation
tables live in `experiments.md`, the domain reading in `sar_research.md`.

All work below was done on 2026-08-25 and 2026-08-26.

---

## The ledger of pre-registered claims

Every hypothesis that was written down before the data that could test it was opened, with
its outcome. **Nine of the seventeen were contradicted, one was not met, and seven held.**
The contradicted ones did more for the final model than the ones that held: four of them
deleted a term, a rule or a whole module, and the twelfth deleted a claim we had already
published.

The ledger lives in the source as `validate.LEDGER`, is printed by every run, and is drawn
as `figures/ledger.png`. The counts above are computed from that tuple rather than typed
beside it, so a fourteenth claim cannot leave this paragraph stale.

| # | stage | claim, written before the test | outcome |
|---|---|---|---|
| 1 | S1 | A right-looking scene must displace in the opposite ground-range direction from a left-looking one under a height error | **held** — T5 alone reverses sign across the height sweep |
| 2 | S2 | Invariant built-up targets can carry a per-date radiometric offset | **held for T6** (+4.28 dB), **refused for T5** — T5's residual changes sign with brightness |
| 3 | S3 | A closing canopy attenuates the surface return at X-band HH, so peak canopy is the darkest date | **contradicted in S4** |
| 4 | S4 | `EXPECTED_SIGN = {Rice: +1, Cotton: −1, Maize: −1, Bajra: −1, Groundnut: −1}` | **contradicted on four of five** — the sign is +1 everywhere |
| 5 | S4 | A per-plot harvest DOY can be recovered from the canopy curve | **contradicted** — the SAR-derived harvest date has no optical signature |
| 6 | S5 | The parcels held above 1.5 dB on all three canopy dates are an orchard or plantation | **contradicted in S9** — bare in June |
| 7 | S5 | Six dates raise tier-1 label coverage above Round 2's 31.6 % of area | **not met** — 26.5 %, recorded as not met |
| 8 | S6 | A wet monsoon means an above-average season, so `Y_ref` should be adjusted upward | **contradicted** — Gujarat kharif rice and bajra hit five-year lows |
| 9 | S8 | The fitted senescence limb projected forward beats persistence at a 30-day horizon | **contradicted** — it loses under the drift control |
| 10 | S9 | Cotton is the greenest of the five labels on the reserved 12 December scene | **held**, one-sided p = 1.26e-11 |
| 11 | S9 | Plot orientation relative to the T5 look direction does not drive `t5_anomaly` (\|rho\| < 0.2) | **held** — rho = −0.051, p = 0.195 |
| 12 | S15 | Re-ranking tier 2 on the signed departure separates the cohorts better on residualised NDVI than the clipped axis did (η² 0.0274, F 10.30) | **contradicted in S14** — the test residualised against the wrong axis. Corrected: η² 0.0023, F 0.847, **p = 0.43** |
| 13 | S15 | `t5_anomaly` orders the tier-2 cohorts Bajra > Maize > Groundnut, most soil-exposed first | **contradicted** — medians Maize +0.82, Groundnut +0.55, Bajra +0.36 dB |
| 14 | S32 | Skill against persistence is non-positive at every horizon and decays as the horizon lengthens | **contradicted** — +0.140 [+0.071, +0.202] at 60 days against −0.180 [−0.330, −0.056] at 30. Positive at the *longer* horizon; the driver is phenology, not horizon length |
| 15 | S33 | C-band: cotton's canopy declines less than the annual cohorts over 15 Nov – 21 Dec, the window the model holds flat | **held** — cotton +0.985 dB against an annual median of −0.020, and the only cohort above its own June soil on 21 December |
| 16 | S33 | C-band: the 10 Oct – 15 Nov change correlates positively with the X-band T4–T6 change | **held** — rho = +0.248, n = 813; positive, and far weaker than the +0.569 the same construction scores at X-band |
| 17 | S33 | C-band: a season integral from 6 passes on the Capella calendar ranks plots like one from every pass, rho ≥ 0.8 | **held** — rho = +0.915, n = 956, median difference 0.27 dB over the same DOY span |

---

## S0 — Scaffold and port (2026-08-25 / 26)

Round 2's thirteen modules were extracted from its notebook into `src/` unchanged, and only
the data path and the competition slug were touched. The port gate was chosen so that a
silent transcription error could not pass it: `coreg_calib.run()` re-fits each scene's RPC
terrain height from scratch, so if any of the calibration or geocoding arithmetic had moved,
the fitted height would move with it.

All four Round 2 dates reproduced to the printed precision (−17.15, −17.61, −17.62,
−17.41 m). The port is clean, and the two rounds are therefore comparable number for number
for the rest of this log.

## S1 — Ingesting the two new acquisitions

T5 (29 October) and T6 (12 November) are not routine extra dates. T5 is right-looking with
its view azimuth reversed by 184°, it is a 01:37 IST pre-dawn pass at maximum canopy dew,
and it follows 63.1 mm of rain in three days. Three separate mechanisms all push its
backscatter the same way.

**The height fit produced an unplanned confirmation.** A geocoding height error displaces a
pixel along ground range, so a right-looking scene must displace opposite to a left-looking
one. Across the sweep from −60 m to +20 m, every left-looking scene's offsets grow positive
with assumed height and T5's alone grow negative. Nothing was fitted to make that happen; it
is the geometry asserting itself, and it is the strongest single argument that the fitted
−17.34 m mean is terrain rather than a tuning constant.

**T5 then broke the co-registration matcher, and the break was the finding.** The first run
reported a 108 m inter-date shift — impossible against Capella's ~5 m CE90 and against T5's
own 0.05 m height-fit residual. Rather than clamp it, three diagnostics were taken. T5's
correlation peak is a third of the stack's, and its near-zero peak is 90 % as strong as the
distant one: the surface is nearly flat and the matcher has almost no preference. That is
the reversed look direction expressed as a statistic — at 1 m resolution the edges a phase
correlator keys on *are* shadow and layover, and those fall on the opposite side of every
bund and building.

The fix is a two-scale search: coarse at 8× decimation where the metre-scale shadow
displacement has averaged out and the parcel mosaic dominates, then fine at full resolution
bounded to 20 m of the coarse answer. The bound is justified by geometry, not by
convenience, and `fit_height` explicitly opts out of it because its sweep mis-geocodes by
design. Unit-checked on synthetic translations, recovered to better than 0.01 px.

## S2 — Radiometric normalisation, and a gate that was measuring the season

Two gate failures, neither fixed by loosening a tolerance.

**G2 failed on T5 at 4.48 m over the full AOI, and measures 0.19 m over the farms.** The
cause was that Round 2 solved its shifts on a village-core window that the 966 plots spill
outside on three sides — the registration was optimised on ground it was not used to sample.
Moving both the solve and the gate to the plot bounding box improved every date, including
the four inherited ones: T3, the peak-canopy date, went from 1.35 m to 0.06 m.

**G3's cross-date spread gate failed at 4.26 dB against a 3 dB tolerance, and was retired.**
T6 is taken after most of the kharif harvest, so the AOI median drops 4 dB. The gate was
asking the radiometry to prove the season had not happened. This is Round 2's own lesson —
verify a gate's assumption after defining it — landing on Round 2's own gate. The spread is
still printed; the gate moved to a question that has an answer, namely whether the dates
agree on targets with no crop calendar.

**Choosing invariant targets had two traps and both were hit before being avoided.**
Thresholding a single-look date selects speckle maxima rather than structures — the
brightest 0.01 % of T1 read 17–25 dB lower on every other date. And selecting on all dates
biases the result by construction. The final estimator selects on 8 m block averages from
T1/T2/T3 only and scores on T4 and T6, which took no part in choosing the targets. **Held
out: T4 and T6 sit 4.01 dB apart before correction and 0.27 dB after.**

**T6 carries a scene-wide bias and T5 does not, and the difference is measured.** T6's
+4.28 dB residual is flat across the scene's whole 39 dB brightness range, stable from the
top 10 % of blocks to the top 0.01 %, and stable across three of four AOI quadrants. No
surface process has a flat signature — harvest darkens fields and leaves roofs alone. T5's
residual is the opposite: it changes sign, −3.5 dB on dark blocks and +2.3 dB on bright,
because rain brightens rough dark surfaces while the reversed look extinguishes the
wall–ground dihedrals that make built-up bright. **No constant can undo two mechanisms with
opposite signs, so T5's level is never used** — it is replaced by the T4–T6 interpolation.

The residual from that interpolation is kept, and it turned out to be worth keeping. The
63 mm of rain before T5 is a natural soil-moisture experiment applied to all 966 plots at
once: exposed soil responds, closed canopy is decoupled. Against Round 2's labels
`t5_anomaly` orders as the Gujarat kharif calendar predicts (Bajra +1.99 dB down to Rice
+0.24 dB). It survives into the shipped features as a weak covariate only.

## S3 — Six-date features, and the sign problem stated

Validity moved from 3-of-4 to 4-of-6, giving 813 measured / 82 interpolated / 71 imputed.

The crop-median trajectories showed rice 4 dB brighter than every other crop at peak canopy
and the only crop that does not brighten after harvest — flooded-paddy double bounce. For
the other four the peak-canopy date was the *darkest* date, which reads as canopy
attenuation of the surface return.

Round 2 had flagged getting this sign wrong as "the single largest avoidable error available
in this project". The stage ended by refusing to resolve it from the SAR stack, on the
grounds that nothing inside the stack separates "canopy attenuating the surface" from
"surface that happens to be smooth that week" — T3 is also the driest antecedent pass in the
stack, API 5.1 mm.

## S4 — The canopy sign, arbitrated by an independent instrument

`canopy_sign.EXPECTED_SIGN` was written as a module constant above the code that opens the
NDVI file, and has not been edited since. The reference is Sentinel-2 L2A on the two dates
where an acquisition lands on the same day as a Capella pass — 13 October and 12 November,
both under 0.1 % tile cloud.

The decisive form is the **difference** between the two dates on both instruments. Plot size,
soil texture, row orientation and position in the AOI are identical on both dates and cancel
out; a correlation that survives is a correlation between things that changed.

**The measured sign is +1 on all five crops** (ALL rho = +0.569, n = 813, p = 8.1e−71;
per-crop +0.334 to +0.705). Greener is brighter. The pre-registration was wrong for four of
the five, and the SAR-internal reasoning that produced it was wrong for a reason the SAR
stack could not have exposed.

**What the wrong sign had cost was then measured rather than asserted.** The shipped
sign-agnostic design, `abs(departure)`, scored **−0.085** against the optical reference; the
clipped form scored +0.472 and the signed form +0.564. The sign-agnostic design was not
conservative, it was empty. `phenology.py` was rebuilt.

**The promised per-plot harvest DOY did not survive the same test and was deleted.** Plots
the SAR called "standing" on 12 November were the *least* green group on that date
(one-sided p = 1.00), and stratifying by inferred clearing date produced no optical
separation at all (p = 0.35). The cause is structural, not a bug: a canopy episode is
observed on three dates with a sixty-day gap across September, and a transition located from
three irregular samples is a free parameter wearing the clothes of a measurement.

It was replaced by `cleared_fraction = 1 − canopy(T6)/peak`, continuous and bounded, which
does validate: monotone against the optical change, rho = **−0.529** (n = 479, p = 6.9e−36).
The categorical quantity was removed and the continuous one kept.

**A confound is left standing rather than argued away.** Soil moisture also brightens
X-band, so a plot irrigated for rabi sowing between the two optical dates would green and
brighten together with no canopy volume scattering. The scene-level version is excluded —
14-day API is 11.9 mm at T4 against 12.2 mm at T6, so district rainfall cannot be the common
driver — but plot-level irrigation remains a genuine contributor to the measured slope, and
the writeup says so.

The honest headline from this stage: median peak canopy is **0.77 dB**. The signal is real
and independently corroborated, and it is small.

## S5 — Re-deriving crop labels from six dates

Three new descriptors, all departures from each plot's own June bare soil so that none
carries the +1.65 dB scene-level drift: the October-to-November change, the canopy remaining
on 12 November, and the season integral.

**Cotton moved from a cluster rule to a plot-level absolute rule.** Cotton does not form its
own mode — the optical greening fraction rises smoothly across ascending November canopy
(0.22 → 0.79) with no break — so cluster assignment split it, labelling 89 % of the top band
and 50 % of the band below with identical optical signatures. The rule is now
`canopy_end_db >= 1.5 dB`, absolute rather than z-scored because a z-score threshold moves
when the clustering moves, and the stability table showed exactly that. **Disclosure: the
optical banding was inspected before the constant was fixed, so the agreement at 1.5 dB is
corroboration, not an independent test of that value.** The full sensitivity range is
printed.

**The tier-1 target was missed and is recorded as missed.** Coverage went from 31.6 % to
26.5 % of area. Two things moved it: 15.1 ha of Round 2's high-confidence cotton was the
long-duration cluster that Round 2 did not screen, and the cotton threshold is now a
physical constant rather than a generous cluster z-score. What improved is the part that
matters — tier-1 area now ranges 118.5–150.0 ha across clustering settings where Round 2's
ranged 46.8–130.6 ha.

**The labels were then checked against an instrument that had no part in assigning them.**
Cotton is the only label still greening into November (+0.138 NDVI) and rice the only one
whose level declines. Both tier-1 crops independently corroborated — something Round 2 could
not do, because both of its optical dates predate the separation.

Overall agreement with Round 2 is 40.3 %, dominated by the tier-2 allocation, which is a
ranking of an unseparable remainder whose ranking axis moved from 13 October to 12 November.
The part that is claimed agrees: **91 % of new Rice was Round 2 Rice.** Both label sets are
carried forward and village totals are reported under each.

## S6 — Season context, and the planning assumption that inverted

The plan proposed taking last season's published yield and shifting it by a rainfall anomaly.
That was written before checking whether 2025-26 had been officially estimated. It has: the
DA&FW Directorate of Economics and Statistics publishes state × season yield in kg/ha as a
machine-readable five-year spreadsheet, currently at Third Advance Estimates for 2025-26.
Free, no registration, and a judge can re-download the identical file.

**The official estimate inverted the plan's expected direction.** Sokhda's 2025 monsoon
measured 1098.5 mm against a 1995–2024 mean of 923.1 mm — 119 % of mean, z = +0.66 — and the
plan read that as an above-average season. Gujarat kharif 2025-26 recorded its **lowest rice
and bajra yields in five years**, rice down 29 % and bajra down 26 % against 2024-25. It was
an excess-rain season, and Vadodara was directly affected: the state announced a relief
package after the Narmada overflowed 16–18 September 2025, inside the grain-fill window for
kharif paddy. Maize, on better-drained land and harvested earlier, posted the best of the
five years.

**Had the plan's rainfall elasticity been applied, rice would have been forecast above its
2024-25 reference in a season the state measured 29 % below it.** This is the single most
consequential correction in the round, and it came from checking a source rather than from
modelling.

The rainfall record is retained as corroboration of the season's character, not as a
multiplier. No district uplift is applied — Vadodara ranks 1st in Gujarat for maize yield
and 2nd for cotton, but no district-level 2025-26 estimate is published, so the maize and
cotton forecasts are conservative by a known sign and the module prints that fact.

Why a state figure can serve as a village reference at all: the Central Ground Water Board
district brochure puts Vadodara kharif at 35.7 % irrigated, with groundwater — used mainly
in rabi and summer — at ~95 % of sources. Kharif here is predominantly rainfed, so a
state-level season effect propagates rather than being buffered.

## S7 — The forecast model

    Y_final(plot) = Y_ref(crop, 2025) * a(season-complete canopy integral)

**One modulation term, not three.** Round 2 measured its own problem: within a crop cohort
its health index and its yield estimate correlated at exactly 1.000, because two of the four
factors are cohort constants and the third is linear in the first. Two separately scored
columns were one ranking under two names. Round 3 keeps the single per-plot term that has
independent external support and reports the health index as a diagnostic that does not
multiply the answer.

**The integral is signed, and that was a measurement.** Signed +0.564 against the optical
reference, clipped +0.472, absolute −0.085. Signed also fixes a degeneracy the clipped form
created: 80.6 % of bajra plots landed exactly on the cohort median of zero, so most of the
maize cohort was being assigned exactly the state reference yield. Signed puts that at 0.4 %.
The clearing fraction keeps the clipped depth, because it is a ratio and both halves must be
non-negative to mean anything.

Result: **894 t over 447.5 ha, 2.00 t/ha area-weighted.** Cotton is the only crop whose
season runs past the stack and the only one carrying a projected share, at 56 % of its
canopy-days. That is what the two extra acquisitions bought — Round 2 discounted cotton by a
hand-set 0.45 and bajra by 1.00, and four of five crops now need no discount because the
stack contains their harvest.

## S8 — The back-test, which deleted a rule of my own

Fit on T1–T4, predict T6, score against what was observed, with Round 2's T1–T4-derived
labels so that no November information reaches any predictor.

**The first pass appeared to vindicate the model and the number is quoted nowhere.** The
decaying-limb projection scored +0.284 [+0.206, +0.353] against persistence on the raw
level. The suspicion that invites is specific: the decaying rule predicts a higher canopy
than persistence, and T6 sits +1.65 dB above T1 district-wide, so the rule could be winning
by being biased in the direction that offsets a drift neither predictor models. Handing
every predictor the drift removes that route. Under the control, the decaying rule scores
**−0.409**, and restricted to plots where it actually changed the answer, **−0.317**. A
30-day slope fitted to a 1 dB signal from two acquisitions 60 days apart is mostly noise.

The projection in the shipped model is now **flat** — last observed canopy carried forward
with no decay. That is what the back-test supports and it is also the right physical read
for the only crop it fires on: cotton is picked in three or four rounds from October into
January and the plant stands through all of them. The decaying variant is retained as B5 so
the comparison that produced the design stays runnable rather than becoming a claim in a
comment.

**A finding about the calendar, not the radar.** The rule's "zero once the calendar harvest
has passed" branch is right for bajra (+0.352) and groundnut (+0.213) and wrong for maize
(−0.581) and rice (−0.887): both still carry canopy on 12 November despite nominal harvest
dates of DOY 288 and 310, consistent with an extended excess-rain monsoon pushing sowing and
harvest later across Gujarat. It does not change the shipped numbers, because in production
the calendar date sets only the length of the tail past 12 November and for maize and rice
that tail is zero either way.

**What can honestly be claimed.** The shipped rule does not beat persistence at a 30-day
horizon on this AOI: −0.119, 95 % interval [−0.280, +0.022], which contains zero. It is
indistinguishable from carrying the last observation forward, which is what it reduces to
for cotton. That is weaker than the plan hoped and it is what the data supports. The value
of the back-test was not to certify the model — it was to delete a rule that looked
principled, produced a favourable headline, and did not survive a control built to break it.

## S9 — Held-out optical, confound controls, spatial coherence

Two Sentinel-2 dates were reserved from the first fetch: **12 December 2025** and **16
January 2026**. `assert_reserved_unread()` greps the source tree and fails the run if any
module outside the fetcher, the validator and the figure that draws the result names those
columns, so "held out" is enforced rather than promised.

**What they can and cannot test is stated before the result.** December and January fall
inside the Gujarat rabi window, so December NDVI over a harvested paddy plot is measuring a
rabi crop; correlating the kharif forecast against it would measure whether a field is a
good field. What they can test is which plots still carry a *kharif* crop after everything
else has finished — and of the five, cotton alone is picked from October into January.

**Cotton's December NDVI is 0.690 against 0.495–0.532 for the other four, one-sided
p = 1.26e-11, and it is the only label greener in January than in December.** A SAR-only
label, assigned from a 12 November acquisition before the December scene existed in the
pipeline, predicted the right plots on a scene it never saw. This is the strongest external
corroboration in the round.

**The negative control matters as much as the result.** If plots cleared by 12 November had
been bare in December, the cotton result would have been measuring "good field" rather than
"still-standing cotton". They are not bare — 0.488 against a population 0.520, both under a
rabi crop. The interpretation survives its own control.

**The long-duration screen was wrong about what it caught, and the record says so.**
Hypothesis 1b predicted the twelve flagged parcels would be green in December, January *and*
June, since no annual can be all three. December and January came in exactly as predicted
(0.777 vs 0.519, p = 1.6e-05; 0.756 vs 0.568, p = 4.9e-04). **June went the other way and
just as decisively: 0.247 against a population 0.397, p = 1.1e-04**, with a June radar level
indistinguishable from everyone else's (p = 0.71). In June these are bare fields, which
falsifies the orchard reading. What the trajectory actually describes is a long-duration
crop sown with the monsoon and standing past every kharif annual — 9 of the 12 never fall
more than 0.5 dB between consecutive passes. Sugarcane and banana both fit, both are grown
in Vadodara, and the data cannot separate them. The screen's operational claim — that these
are not one of the five kharif annuals — survives untouched, and the constant and flag were
renamed `LONG_DURATION_MIN_DB` / `long_duration_flag` to say only that.

**Look-direction control.** Row direction is not in the shapefile, so it is estimated by PCA
on each parcel's exterior ring, tested only on the 650 parcels elongated enough for a
principal axis to mean something. rho(angle to the T5 look, `t5_anomaly`) = −0.051 and
rho(cos 2Δ, `t5_anomaly`) = +0.051, both p = 0.195 and both inside the ±0.2 threshold set
before looking. Clean.

**Spatial coherence.** Moran's I over 8 nearest neighbours with a 999-permutation null — 199
until an audit pointed out that the `p = 0.005` it produced three times *is* 1/200, the
smallest number that estimator can return (§S14). The forecast (+0.279) and the season
integral (+0.187) are expected to cluster — neighbouring fields share soil, water and
management. The one worth reporting is the within-crop residual at **+0.151, p < 0.001**: after conditioning on the crop label there is still real spatial
structure. Had that been near zero, the residual would have been plot-level noise and the
forecast would be five numbers with speckle on top.

## S10 — Shipped tables and figures

Three tables, and a schema gate that runs on the files rather than the frames. Because the
round is rubric-judged there is no prescribed schema, which removes a constraint and adds an
obligation: the columns are ours to choose, so they are the ones a judge can check the work
with. `farm_forecast.csv` carries the forecast and every term that produced it.

**The gate caught three defects, all of them in shipped artefacts.** The village total did
not equal the sum of the shipped file, by 0.0015 t, because the plot table was rounded after
being aggregated at full precision — a judge adding up the CSV would have got a different
number from the summary. `canopy_peak_doy` reported 14 August for 378 plots that never grew
a canopy, because `argmax` over an all-zero curve returns index 0. And NaN in
`cleared_fraction` is not a defect but had to be made precise: the gate now asserts the null
pattern exactly, null if and only if `has_canopy` is false.

**Two figures were caught printing different numbers from their own modules' logs** — the
exact defect Round 2 hit three times, and the reason figures read delivered files instead of
re-deriving. Both now call the module that owns the number.

The back-test figure states its negative result as its headline rather than burying it.

---

## S11 — Reproducibility, and the defect it found (2026-08-27)

The notebook was run end to end on Kaggle and its log compared to `logs/pipeline_clean.log`
number by number. **Every SAR number matched exactly** — the six fitted terrain heights, all
three Phase 1 gates, the T4-versus-T6 invariant-target score (4.01 dB → 0.27 dB), the
813/82/71 data-quality split, the entire canopy-sign section, the entire back-test. The
k-means partition matched too: same nine cluster sizes, same areas, same z-scored descriptors.

**Only the tier-2 allocation moved, and 39 plots with it** — Maize 316 → 277, Bajra 136 → 175,
the village total 898.3 t → 896.6 t. The cause was ours, not Kaggle's. The tier-2 ranking axis
was the November canopy *clipped at zero*, so 403 of the 793 allocated plots sat at exactly
0.0; the bajra/maize cumulative-area cut fell inside that block of tied keys, and an unstable
sort settled it. Inside that same block the *signed* departure runs −14.316 to −0.001 dB
across 392 distinct values.

This is the degeneracy S4 had already measured and removed from the season integral (signed
+0.564 against the optical reference, clipped +0.472, absolute −0.085), still standing one
module downstream — S4 looked at the integral and not at the classifier that consumes the
same column.

**Nothing available on one machine could have found it.** Every gate passed, forty tests
passed, the write-up's own audit traced every number to a log that printed it, and the number
was perfectly stable on either machine alone. Running the same code somewhere else is the
control, and it is the only one that works on a quantity with no ground truth.

The fix is the axis, not the sort: `TIER2_AXIS = "departure_T6"`, with a stable mergesort on
`[axis, farm_id]` so the result is a property rather than a coincidence. 185 tier-2 labels
moved; the re-ranked cohorts separate **better** on optical data they never saw (claim 12
above). Village total 893.9 t. A shuffled-input regression test now pins it.

The same session found a second gate that was passing for the wrong reason. The write-up
claimed `t5_anomaly` ordered the cohorts by exposure, "Bajra +1.99 dB … Rice +0.24" — numbers
**no Round 3 run ever printed**. `audit_writeup.py` matched bare tokens against the whole log
and both strings happened to occur on unrelated lines. `--trace` now writes every token beside
the line it was read off. The claim was replaced by the measured medians and the prediction
recorded as contradicted (claim 13).

## S12 — What the total is worth (2026-08-27)

**Five** sources of uncertainty on the village total, each obtained by **re-running the whole
chain** under that one change rather than by propagating a formula through it: the state
reference at a stated ±10 % (±89.4 t), the district crop mix that allocates three of five
cohorts (±61.5 t), Round 2's labels substituted (±6.8 t), speckle at 4.34/√N dB per plot over
1000 draws (±2.7 t), and the tier-2 tie ordering over 200 permutations (±0.0 t).

The district-mix row was added on 2026-09-01 (§S15). It was missing for four days, and its
absence was the largest single omission an audit found in this project: the mix sets the areas
of Bajra, Maize and Groundnut — 793 of 966 plots — and until that row existed the table priced
everything about the answer except its biggest assumption.

**External assumptions sum to 150.9 t; everything the radar and this pipeline contribute sums
to 9.5 t.** That is not a weakness of the method, it is the correct description of it: the
per-plot SAR term ranks plots within a cohort, and both the level that ranking sits around and
the size of three of the five cohorts are somebody else's numbers. Any yield forecast without
ground truth has this shape; most do not say so, and the earlier version of this table did not
say all of it.

---

## S13 — What the shapefiles say, and what the brief says (2026-08-27)

Two claims in the competition Overview are not what the shipped files contain, and both are
now stated in the write-up rather than worked around.

**"An expanded set of villages."** `Sokhda_Village.shp` holds exactly one feature,
`{ID: 22, VILLAGE: 'Sokhda'}`. We had said this from the farm attribute (`ID_1 = 22` on all
966 rows); saying it from the village file itself is the same conclusion with one inference
fewer.

**"The crop classification carried forward from prior rounds."** `Sokhda_Farms.shp` carries
five fields — `FID`, `id`, an unnamed all-null one, `ID_1`, `VILLAGE` — and none of them is a
crop. The classification is not in the data. That is why `crop_type.py` exists and why the
canopy sign and the back-test score against *our own* Round 2 labels. Nothing about the
method changes; what changes is that a reader who assumed labels were supplied would have
read the classification module as work that did not need doing.

**The village roll-up is now gated on geometry.** `Sokhda_Village.shp` had been read in one
place, to draw an outline, while the rollup grouped plots by a text column. Grouping by a
name is an aggregation assumption; the village polygon is what turns it into a claim.
`submit.village_containment` reprojects both shapefiles to UTM 43N, intersects every plot
with every village polygon and assigns by largest shared area — not centroid-in-polygon,
because an edge parcel can have its centroid outside the boundary with most of its ground
inside. It raises if any plot's geometric village differs from its attribute, or if more than
1e-6 ha of real parcel lies outside every polygon, and it runs before any table is written.

962 of 966 plots agree, **none disagree**, and **100.00 % of digitised parcel area is inside
the boundary**. The four that cannot be placed enclose no measurable ground; seven of the ten
degenerate parcels intersect nothing at all and fall back to a centroid test.

The number that came out of it and had not been stated anywhere: the village polygon encloses
**1174.1 ha** and the digitised parcels total 447.5 ha, so **the village total covers 38.1 %
of Sokhda**. It is a total over mapped farmland, not over the village.

**What the canopy sign cost in coverage.** The measured sign is the one quantity the radar
could not settle alone; it needed a second instrument on the same day. The run's own log says
how often that existed: twice in six passes, and T5's only candidate was 79.1 % cloud, which
is why there is no T5 optical control. That is a limitation of this method rather than of
this data, and it is why co-located optical–SAR acquisition is the thing that would change
what a stack like this can prove.

---

## S14 — An adversarial audit of our own submission (2026-08-31)

Three independent auditors were run over the shipped tree with one instruction: find every
reason an expert panel should not score this highly. The report is `docs/judge_report.md`. It
found three things that were **false as written**, and every one of them was ours.

**Our leakage analysis was wrong about leakage.** `leakage_analysis.md` listed the season
integral and `COTTON_NOV_DB` under *"what optical did NOT touch, and can therefore test it"*.
Both were touched. `phenology.py:68-72` says the signed form of the integral was chosen because
it "reaches rho=+0.564 against +0.472 for the clipped-positive form" — a selection made against
13 Oct / 12 Nov NDVI — and the integral is the only per-plot term in the forecast.
`crop_type.py:234-237` had disclosed the optical informing of `COTTON_NOV_DB` all along, so the
leakage document contradicted its own source file.

The three scores were always published. What was wrong was filing the quantity as optically
untouched *while publishing the numbers that show it was not*. Both entries are corrected in
place under a heading that says they were corrected. The pre-registered string in
`validate.RESERVED_TEST` that says the cotton label had "no optical input" is **left standing**
with the correction recorded beneath it — rewriting a registration after the fact is the one
thing this project does not do.

A consequence worth stating: the run now prints **all three** arms of the comparison that chose
the integral's form (signed +0.564, clipped +0.472, absolute −0.085), where it previously
printed two of three — and it labelled the signed one `(clip>=0)`, which was simply wrong.

**A p-value that was a resolution floor.** See the spatial-coherence entry above and
`AGENTS.md` S23b. `p = 0.005` from a 199-permutation null is 1/200.

**A repository that ran for nobody but us.** No `requirements.txt`, no `README`, no
data-acquisition step; `.venv` built with `--system-site-packages` so none of numpy, pandas,
scipy, sklearn, GDAL or pytest actually shipped; and `geocode.py` resolving `DATA_DIR` at import
time against a data directory outside the repo, so `import geocode` failed on a clean machine
and took the whole test suite with it. The Kaggle notebook ran. The repository did not, and the
winner's obligation is a reproducible repository. Both files added, plus a resolver fix so the
Round 2 labels shipped in `kaggle_dataset/` are actually found by a fresh clone.

**The audit's own second round overturned a published claim.** Fixing the leakage document
exposed the test underneath it. `s2_ndvi.label_information_test` took `axis` as a *default
argument* — `"g0_db_filled_T4"`, which was the tier-2 ranking axis until §S13/S15 moved it to
`departure_T6`. The single call site never passed the argument. So from the moment the axis
changed, the test residualised against a column that was no longer the ranking axis, while the
run printed "residualised against gamma0 T4, the tier-2 ranking axis" and pre-registered claim
12 was scored by it and reported **held**.

Corrected, the picture inverts completely:

```
tier              axis                n   eta2 raw  eta2 resid        F          p
2 (allocated)  departure_T6         735     0.0335     0.00231     0.847   4.29e-01
2 (allocated)  g0_db_filled_T4      735     0.0335     0.03017    11.387   1.35e-05
1 (control)    departure_T6         170     0.0071     0.04605     8.109   4.95e-03
1 (control)    g0_db_filled_T4      170     0.0071     0.00009     0.015   9.03e-01
```

Read the first and third rows together. Residualised against the axis that actually assigns
them, tier-2 labels carry **no** information about NDVI (p = 0.43) — and the tier-1 positive
control, which had been failing silently, now **passes** (p = 0.005). That is the design
condition stated in the function's own docstring: tier 1 must pass or a tier-2 failure cannot
be trusted. It passes, so the failure can be trusted.

**Claim 12 is therefore contradicted, and the ledger says so.** What it does not do is
undermine the S15 axis change, which stands on the degeneracy it removed — 403 tied plots
reduced to 49, permutation spread on cohort area exactly 0.00 ha. Nor does it undermine the
model, because the project has described tier 2 as "allocated, radar cannot separate" from the
beginning. The uncomfortable part is the opposite: the broken test had been telling us
something *better* than our own honest framing, and we published it.

Both residualisations are now printed side by side, `axis` is a required argument so no future
axis change can silently invalidate the test again, and the prediction is scored in the run on
both the like-for-like row and the corrected one.

**What the audit did not overturn.** The forecast is unchanged at 893.9 t. No gate, no
back-test result, no reserved-scene result and no aggregation number moved. Every defect it
found was in a claim *about* the work rather than in the work — which is its own finding, and
not entirely a comfortable one: the documentation was audited less carefully than the code.

---

## Sources

External data, all free and re-obtainable by a judge without registration:

- **Sentinel-2 L2A** via Earth Search v1 (`earth-search.aws.element84.com`), `sentinel-cogs`
  anonymous COG access, MGRS tiles 43QBE and 43QCE.
- **NASA POWER** daily `PRECTOTCORR` point series at 22.4254 N, 73.1567 E, 1995–2025.
- **DA&FW Directorate of Economics and Statistics**, five-year estimates of foodgrains,
  oilseeds and other commercial crops 2021-22 to 2025-26 —
  `https://desagri.gov.in/statistics/5-year-estimates-of-foodgrains-oilseeds-and-other-commercial-crops-2021-22-to-2025-26/`
- **Ministry of Agriculture & Farmers Welfare**, Second Advance Estimates 2025-26 (released
  10 March 2026), used as an independent read on the national kharif.
- **Central Ground Water Board**, Vadodara district groundwater brochure, Table 6 —
  `https://cgwb.gov.in/old_website/District_Profile/Gujarat/Vadodara.pdf`

Rejected sources, and why:

- **Kaggle APY mirror** (`arjunyadav99/indian-agriculture-crop-production-and-yield`) — the
  unit scale differs per crop, so the yield column cannot be decoded. Vadodara kharif rice
  2018 decodes to either 216 kg/ha or 2.17 t/ha; the same transformation gives cotton lint
  4595 kg/ha, an order of magnitude above any Indian cotton yield recorded. A plausibility
  gate on the final number would not have caught this, because 2.17 t/ha for paddy is
  perfectly plausible and only cotton reveals the inconsistency.
- **Sentinel-1** — Round 1 measured the fusion negative, and a 0.27 ha median plot is about
  27 pixels at 10 m.
- **SoilGrids** — 250 m over a 5.9 × 4.7 km AOI is roughly 24 × 19 pixels and cannot
  differentiate 0.27 ha plots.

## S15 — Pricing the district crop mix (2026-09-01)

The uncertainty budget priced four sources and omitted the one that sets three of the five
cohort areas. `crop_type.allocate_tier2` cuts the 793 plots the radar cannot separate at
cumulative-area shares taken from a district crop mix, so Bajra, Maize and Groundnut — about
326 of 447 ha — are sized by an external prior. The run had always said the agreement was "by
construction"; the budget had no row for it.

**The scale did not have to be invented.** Two of the five crops are assigned by threshold
rules rather than by the mix, so the mix can be scored against them:

```
Rice      district 0.26   measured 0.170   log-ratio -0.426
Cotton    district 0.32   measured 0.102   log-ratio -1.147
```

It overstates both, and by different amounts. A common bias would renormalise away; what moves
the tier-2 split is the *disagreement between* crops, so the standard deviation of those
log-ratios — σ = 0.51 — sets a multiplicative perturbation on the three tier-2 weights, which
are renormalised, re-cut and re-forecast over 200 draws.

Result: **±61.5 t on the village total**, 6.9 %, and cohort areas that range from 13 to 184 ha
(Bajra), 21 to 246 (Maize), 38 to 256 (Groundnut). The row is second only to the state
reference and is nine times every radar term combined.

Two honest caveats, both printed by the run. This is a **scenario**, not a posterior: it
assumes the prior errs on the three crops we cannot check by about as much as it errs on the
two we can. And the cohort-area ranges are wide because σ = 0.51 is large — which is itself
the finding, since σ was measured rather than chosen.

What it changes: the write-up's headline moves from "every radar term sums to 9.5 t against
89.4 t for the reference" to **"external assumptions 150.9 t, radar 9.5 t"**. The shape of the
claim is the same and the statement is stronger, because it no longer omits an assumption
larger than everything it was already pricing.
