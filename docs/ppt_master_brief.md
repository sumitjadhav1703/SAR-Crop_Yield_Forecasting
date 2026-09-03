# Master brief for the Goa Finals deck — why, what and how, across three rounds

**What this file is.** One place holding everything needed to talk a judge through this
project: what each round asked for, what was built, why each choice was made, what was
measured, and what went wrong. Part A is the reference. Part B is the slide script. The two
appendices are a figure-to-slide map and an honest list of what is still weak.

**Rules this file follows.** Every Round 3 number is printed by the shipped run in
`logs/pipeline_clean.log`. Every Round 1 and Round 2 number carries a citation into that
round's own frozen `AGENTS.md`. Nothing here is estimated, reconstructed or rounded into a
nicer shape. Where a number could not be traced, this file says so instead of filling it in.

**Read order if you have ten minutes.** A0 (what was asked), A3 (Round 3's method), A4
(validation), then Part B.

---

# PART A — THE STORY

## A0. The competition, across three rounds

Same organiser (GalaxEye Space Solutions), same Capella X-band SAR, same district. The
question changed each round, and so did how it was scored.

| | Round 1 | Round 2 | Round 3 |
|---|---|---|---|
| **Question** | Kharif **acreage** per crop | crop type + health + **yield-to-date** at 13 Oct | **final yield at harvest** |
| **Unit** | 29 Gujarat villages × 5 crops = 145 cells | 966 farm plots, one village | the same 966 plots |
| **Data** | 4 Capella HH passes | the same 4 passes | **6** passes, 6 Jun – 12 Nov 2025 |
| **Scored by** | **MSE on a public leaderboard** | a panel, against a rubric | a panel, against a rubric |
| **Ground truth** | hidden, but a score fed back | none | **none** |
| **Result** | LB **60.757, rank #2** | 1001.6 t, 2.24 t/ha | **893.9 t, 2.00 t/ha** |

The single most important line for a judge: **the scoring changed from a metric to a rubric,
and then the labels disappeared entirely.** Round 1 could iterate against a leaderboard. Round
3 cannot iterate against anything. That is why Round 3 spends its effort on controls and
held-out tests rather than on model capacity — there is nothing for a CNN to regress onto and
no out-of-fold estimate for an ensemble to weight by.

### The rubric this deck is scored against

Round 3, 100 points (`docs/competition.md:30-36`):

| Criterion | Points |
|---|---|
| Technical Soundness — a rigorous, well-justified method for a final forecast from the six-pass series | **25** |
| Creativity — a novel or thoughtful modelling approach, including sensible use of external data | 15 |
| Plausibility & Defensibility — physically and agronomically plausible values, with clear reasoning and sanity checks **given the absence of ground truth** | **25** |
| Aggregation — sound logic for rolling plot forecasts up to village level, by crop | 15 |
| Documentation & Presentation | 20 |

Round 2's was similar but not identical (`Round 2/AGENTS.md:15-17`): Technical Soundness 25 ·
Methodological Creativity 20 · Validity & Plausibility 20 · Village Aggregation & Coverage 10 ·
Documentation & Reproducibility 15 · Presentation Quality 10, with "notebook runs clean, CSV
schema" as a yes/no gate.

**Fifty of the hundred Round 3 points are Technical Soundness plus Plausibility &
Defensibility**, and both ask whether the reasoning holds, not whether a number is close to
anything. Build the deck against that.

The host says the absence of labels is deliberate: *"part of the challenge is building a
defensible methodology to arrive at plot-level and village-level yield predictions without
labeled targets to fit against directly"* and *"submissions are judged on the strength and
defensibility of the methodology, not a match to a hidden label"* (`docs/competition.md:14-16,
27-28`).

### What deliverables are due

Kaggle Writeup submitted before **2026-09-03 07:00 UTC**, carrying a ≤2000-word write-up, a
media gallery with a cover image, a public notebook containing the full pipeline, and a
**10-minute PowerPoint for the Goa Grand Finale, 2–3 September 2026**
(`docs/competition.md:44-53`). Six teams were shortlisted from Phase 2; one final submission
per team.

---

## A1. Round 1 — acreage, a leaderboard, and a deadlock

*(Frozen. All citations are `Round 1/AGENTS.md` unless stated.)*

### Why it matters to this deck

Round 1 is where the team learned **what X-band HH cannot do**. Every Round 3 design choice
that looks like restraint — no CNN, no per-pixel classifier, no claim of biomass retrieval,
only two of five crops labelled by measurement — traces back to a physical ceiling Round 1 hit
head-on and documented.

### The task

Estimate Kharif crop acreage in hectares for Rice, Cotton, Maize, Bajra and Groundnut across
**29 Gujarat villages** (`:397`). Scored by **MSE over all 145 village × crop cells** (`:398`).
Four Capella HH acquisitions — 6 Jun, 19 Jun, 14 Aug, 13 Oct 2025 (`:399`), the dates confirmed
from the scenes' own metadata rather than from the organiser's prose, which said
"June/July/August/October" for a stack with two June scenes and no July (`:40-41`).

**Fully unsupervised** — no labels, no cross-validation, no local score (`:400, 420`). The
organiser's own guidance, quoted verbatim: *"We are primarily expecting participants to adopt a
rule-based or threshold-based approach"* and, on external data, *"the provided Capella X-band
SAR imagery should remain the primary dataset"* (`:410-416`).

### What was built (Stage 1 — the remote sensing)

1. **A wrong-file discovery that reset the project.** Notebooks NB0–NB15 had been reading the
   8-bit contrast-stretched `*_GEO_HH_*_preview.tif` browse thumbnail, not the real product
   (`:7-24`). The calibrated signal is in the complex SLC — β⁰, slant range, with RPCs and 225
   GCPs — and needs `gdal.Warp(rpc=True)` to geocode (`:26, 852`).
2. **Geocode and convert**: complex → intensity → `gdal.Warp(rpc=True)` → EPSG:32643 at 1 m → dB.
3. **Per-village clustering**: clip four dates, mask to pixels valid on all four, flatten to
   (N, 4), **per-village column-wise MinMaxScaler**, subsample ≤500k px,
   **KMeans(k=7, n_init=5) across 10 fixed seeds, take the median** (`:678, 922`).
4. **Cluster → crop by a ranked heuristic** on brightness and temporal deltas against phenology
   reference curves. Not a classifier — there were no labels to train one.
5. **Failed and sliver villages**: 4–5 villages have zero SAR footprint on some or all dates
   (Manpura, Sankhyad, Kotna, Pilol, Alindra, `:567-581`), filled by area-proportional KNN
   imputation from the three nearest neighbours.
6. **Cropland masking — the single biggest lever in the competition.** Gating KMeans to ESA
   WorldCover class 40 (Cropland) removed 55.1 % of "valid" SAR pixels before clustering and
   moved the leaderboard **−512.9 MSE (−27.5 %), "by far the biggest single jump"** (`:70`).
   Earlier pipelines had been clustering more than half non-agricultural land.
7. **Mask upgrade**: WorldCover 2020 → Impact Observatory Annual LULC v02 (2023), class 5.
   Fresher and season-specific; removed 46.4 % of pixels rather than 55.1 %, and scored
   **1132.987 against 1348.108, −16.0 %**.

### The deadlock, and how it broke

From early July, **six consecutive structural experiments scored worse than the standing best**
(NB19_percrop, LB 1348.108):

| experiment | outcome |
|---|---|
| NB20 — γ⁰ physics, drop per-village MinMax | percrop **+1430.67 worse** (`:467`) |
| NB21 — absolute-dB rice flood pre-mask | **+135.7** worse; percrop +1564.3 (`:468-469`) |
| NB23 — fresh consensus OBIA pipeline | **+285.6** worse (`:470`) |
| NB24 — crop-mix "sink" cluster, several variants | every variant negative, worst **+888.7** (`:471, 484`) |
| GMM instead of KMeans | **+35.4 %** worse (`:120-124`) |
| Sentinel-1 DpRVI cross-check | **no crop-type signal at all** — water and crops in the same index band (`:126-144`) |

The verdict at the time: *"Sixth closed experiment this session … all converge on the same
conclusion: NB19_percrop (LB 1348.108) is very likely at or near the ceiling of what this
unsupervised pixel/object-clustering approach family can reach"* (`:144`).

**The physical cause.** X-band's 3.1 cm wave penetrates only the top canopy and saturates at
canopy closure, so Cotton, Maize and Bajra converge to nearly identical backscatter by August;
single-pol HH lacks the VV/VH features the literature says separate structurally similar
dryland crops (Known Failure Mode #9, `:767`). Every experiment was hitting physics, not a bug.

**The break.** An independent re-audit
(`Round 1/DEADLOCK_BREAKTHROUGH_RESEARCH.md:133`) noticed that all six failures had perturbed
the **crop-type** axis and none had touched the **mask** since NB19 — and the mask was the only
lever that had ever produced a large win:

> *"'we hit the ceiling' really means 'we exhausted the type-discrimination axis,' which was
> the wrong axis to keep pushing. The area axis (mask quality, rice physics, total-area
> decoupling, non-target removal) is not exhausted."*

Acting on it gave NB26 and LB 1132.987. That re-audit also **corrected an earlier breakthrough
draft** that had proposed an eigenvalue DpRVI (physically impossible from single-pol HH — there
is no covariance matrix), zero-shot MobileSAM segmentation (all cited evidence was optical),
and a Dirichlet prior that was near-isomorphic to machinery already in place.

### Stage 2, and why this deck must handle it carefully

Below 1132.987, every gain came from a different lever entirely: any scored submission `p`
gives an exact measurement of its correlation with the hidden truth,
`C = mean(p·t) = (P + T − S)/2`, which turns past submissions into a solvable linear system.
That drove 1132.987 → 1003.657 → 526.761 → 523.458, and a deadline-day sweep that probed 66 of
145 cells individually and inverted them algebraically reached **60.757, rank #2**.

**Round 1's own log is explicit about what that is** (`:286`):

> *"the sweep carries zero remote-sensing information and zero generalization value… Stage 1
> (NB26_percrop, MSE 1132.987) remains the substantive contribution and is what we ask to be
> judged on if the committee views Part 6 as outside the challenge's spirit."*

The framing decision was also deliberate and is recorded (`:301`): the probe machinery is
presented as *leaderboard-guided closed-form calibration, fully disclosed* — not euphemised —
because organisers can see the full submission history anyway.

> **For the deck:** do not lead with "60.757, rank #2." The honest answer to the obvious
> follow-up is "that number is not remote sensing," and volunteering it is far better than
> being asked. If Round 1 appears at all, it appears as **the round that established the
> physical ceiling** — mask quality dominates crop-type discrimination, X-band HH cannot
> separate structurally similar dryland crops, and Sentinel-1 fusion measured negative on this
> AOI. All three of those findings are load-bearing in Round 3.

### Round 1's other dead ends, all measured

- **Lee 7×7 despeckle** — inflated predicted area +26.6 % and inverted the per-village share
  skew (`:810-813`).
- **GLCM texture** — a genuinely new feature axis, still lost by ~86 scaled (`:803-807`).
- **DTW + Hungarian assignment**, three iterations — never beat the plain ranked heuristic
  (`:721, 762, 786-789`).
- **Rice flood pre-mask**, at pixel and at object scale — at 1 m, single-look speckle (±5.6 dB)
  exceeds the flood-to-canopy signal; *"the flood→canopy rise signature does not exist in this
  data at any object scale"* (`:14, 379-391`).
- **Sentinel-2 NDVI phenology templates** — killed by an 11-week monsoon cloud blackout
  covering both August and October anchors (`:98-114`).
- **WorldCereal 2021 mask** — removed 66.5 % of pixels, worse than both alternatives, never
  submitted (`:224-242`).

And one prediction contradicted by its own test: the standing hypothesis that Bajra's weak
signal came from the ranking heuristic confusing it with Rice/Maize was **rejected** — the real
cause was Bajra's cluster having the lowest temporal variance of all seven (4.59 dB² against
Maize's 14.73) (`:92`).

### Two lessons that became standing rules

- **`gdal.Warp(rpc=True, errorThreshold=0.0)`, never a WarpedVRT fallback.** The fallback
  *"filled 100 % of the AOI grid instead of the true ~16.5 % swath"* (`:90`). This rule is still
  in force in Round 3.
- **No silent `except`.** *"Every 'graceful fallback' is somewhere a validation gate can
  silently stop running"* (`:781`) — found on deadline day, when hardcoded paths wrapped in
  `try/except` would have degraded quietly on Kaggle with a gate printing SKIPPED and a figure
  vanishing.
- **Never glob for a date-identifying file** — the duplicate SLC in the T2 folder (`:190`). The
  same organiser packaging bug is still present in Round 3's data.

---

## A2. Round 2 — the pipeline this project still runs on

*(Frozen. All citations are `Round 2/AGENTS.md` unless stated.)*

### Why it matters to this deck

Round 3 did not rebuild. It **extended a pipeline already verified end-to-end on Kaggle across
five runs** (`Round 3/AGENTS.md:141-143`), and then deleted four of its modules. Round 2 is
where the calibration ladder, the RPC height fit, the co-registration and the zonal engine were
built and proved. It is also where three of Round 3's four biggest design decisions came from —
each one a response to a defect Round 2 measured in itself.

### The task

Crop type, a health index, and **yield-to-date as of 13 October** for 966 plots in Sokhda, on
four passes. The deliverable schema came from `Sokhda_Dummy_Submission.xlsx`:
`village_id, farm_id, crop_type, health_index, yield_estimate_to_date` (`:128-135`). The module
docstring states the organisers' wording directly: *"the organizers ask for yield 'as observed
through October 13, not a final harvest forecast'."*

**No leaderboard** (`:8-12`) — the first round scored by a panel. And a promised input did not
exist: `round1_crop_classification.csv` was *"verified server-side, not a download issue"*
(`:43-46, 194`), so the classifier was built fresh, softly constrained to Round 1's
village-level Sokhda mix (`:200-204`).

### The method chain

**Phase 1 — calibration, geocoding, co-registration** (`:210-273`)

```
beta0  = (DN · scale_factor)^2
sigma0 = beta0 · sin(theta) − NESZ(range)        # NESZ a degree-3 polynomial in range
gamma0 = sigma0 / cos(theta)
```

Terrain height was **solved per scene, not assumed**: fitted ellipsoidal heights
−17.15 / −17.61 / −17.62 / −17.41 m, spread 0.46 m, std 0.19 m (`:238-253`), against Capella's
own focusing surface of −21.53 m. The vendor's own products are not mutually co-registered —
T2 against T1 is 4.29 m even after the height fit — so per-date shifts register everything to a
T1 master (`:255-263`). Three gates: G1 footprint IoU against the vendor preview 0.996–0.999;
G2 co-registration ≤ 2 m, worst 1.33 m; G3 radiometry, cross-date median spread 1.79 dB
(`:265-268`).

**Phase 2 — farm features** (`:281-292`). 966 rows, no NaN. Validity ≥ 3 of 4 dates at ≥ 50 %
core coverage; a single missing date interpolated from the plot's own dates; 71 farms below
that filled from their 8 nearest valid donors, with the donor distance recorded per plot.
Final split **894 measured / 71 imputed / 1 interpolated** (`:724, 926`).

**Phase 3 — crop type, two tiers** (`:294-365, 1161-1216`)

- A **physical non-crop screen before clustering**: `OUTLIER_MAX_DB = −10.0` on any date, or
  `OUTLIER_MAX_COV = 2.0`. Removed 37 farms / 21.2 ha / 4.7 % (`:308-313`).
- Features on incidence-matched dates T2/T3/T4 only —
  `level_T3, d23, d34, curv234, range234, cov_T3` — deliberately excluding T1→T2, which is
  confounded by monsoon-onset soil moisture and carries the largest incidence-angle jump.
- Consensus k-means, 9 clusters over 20 seeds, co-association partition.
- **Tier 1**: threshold rules on z-scored cluster descriptors. Rice from a level ~5 dB above
  everything else at peak canopy, falling in October; Cotton as the one cluster whose
  backscatter *rises* T3→T4 (`d34` +2.76 dB against ≤ +1.4 dB elsewhere).
- **Tier 2**: the residual allocated across Maize/Bajra/Groundnut by ranking `g0_db_filled_T4`
  ascending, cut by the district mix
  `{Rice 0.26, Cotton 0.32, Maize 0.18, Bajra 0.08, Groundnut 0.16}` — used *"openly, and only
  here."*
- Tier-1 labels were **100 % stable** across `n_clusters ∈ {7,9,11}` and `n_seeds ∈ {5,20,40}`;
  overall agreement 83–98 % (`:306`).

**Phase 3.5 — the sign, settled by measurement** (`:315-413`). The cross-date levels *looked*
like a canopy attenuating the surface. Same-day Sentinel-2 said the opposite, and
`BIOMASS_SIGN` was set to **+1**. The log states plainly that assuming it *"would have been the
single largest avoidable error available in this project."*

**Phase 4 — health index** (`:415-436`). Rank-normalised **within crop cohort**, because *"a
healthy paddy and a healthy groundnut do not share a backscatter level"*:

```
health = 100 · Σ(w_i · rank01(component_i)) / Σw_i
w = {canopy 0.35, trajectory 0.30, uniformity 0.20, senescence 0.15}
```

**Phase 5 — yield to date** (`:437-457`):

```
yield_to_date = Y_ref(crop) · f(health) · a(accumulation) · g(crop)
f = 0.55 … 1.45                        # bounded ±45 %
COMPLETENESS g = {Bajra 1.00, Maize 0.95, Rice 0.88, Groundnut 0.85, Cotton 0.45}
Y_ref kg/ha  = {Rice 2537.97 paddy, Maize 3106.00 grain, Bajra 1786.66 grain,
                Groundnut 3026.31 pods, Cotton 834.00/0.34 = 2452.9 kapas}
```

**Phase 6 — aggregation** (`:459-471`). `submission.csv` (966 rows, exactly 5 columns),
`village_summary.csv`, `zone_summary.csv` (46 sub-zones of 500 m covering 946 farms), 8 figures.

### The methodological spine: farm level, not pixel level

This is the sentence that connects Round 1 to Round 2 and is worth saying out loud in the room.
A median farm of 0.27 ha is about **2,100 pixels at 1 m**. Speckle averages down as
`4.34/√N ≈ 0.094 dB`, against **±5.6 dB per single-look pixel**. So:

> *"Round 1's documented separability ceiling was a pixel-level ceiling and does not bind at
> farm level"* (`:107-109, 283-287`).

That is why Round 2 could re-open a question Round 1 had closed twice.

### Round 2's shipped answer

**966 farms, 447.5 ha, 1001.6 t, 2.24 t/ha area-weighted, area-weighted health 46.9** — measured
directly off `village_summary.csv` and `farm_yield.csv`. Crop split from `farm_crops.csv`:
Groundnut 296 farms / 115.8 ha, Maize 293 / 130.4, Bajra 167 / 57.7, Rice 109 / 82.3,
Cotton 101 / 61.3. **Tier-1 coverage 206 farms / 141.3 ha = 31.6 % of area** (`:456-457`) — the
number Round 3 measures itself against.

(An earlier 1006.3 t appears throughout `:456, 552, 575, 725, 927`; the drop to 1001.6 t is the
direct consequence of adding the `a` factor described next.)

### The four defects Round 2 found in itself — and what Round 3 did about each

**1. The health index and the yield estimate were the same ranking under two names.** From
`yield_estimate.py`'s own docstring:

> *"Without `a`, within any one crop cohort `Y_ref` and `g` are constants and `f` is linear in
> the health index, so the within-crop rank correlation between `health_index` and
> `yield_estimate_to_date` is exactly **1.000**. Measured, not estimated — the two columns the
> rubric scores separately were the same ranking under two names."*

Round 2's fix was to add the accumulation factor `a`, which brought rho to **0.928** (`:1330-1333`).
**Round 3's answer was to delete the health index entirely** and ship one modulation term.

**2. A hand-set completeness constant.** `COMPLETENESS["Cotton"] = 0.45`, *"the single largest
'to date' discount in the whole table,"* justified agronomically (cotton is picked Oct–Jan in
3–4 pickings, only the first in hand on 13 Oct) but never measured.
**Round 3 replaced it with measurement** — six dates close four of five crops by observation,
and cotton's projected share ships per plot as `extrapolated_fraction`.

**3. Code lived only inside the notebook.** All thirteen modules existed only as `%%writefile`
cells (`:1116-1118`), a deliberate choice — "no second implementation that can drift" — that
made local iteration painful. **Round 3 inverted it**: real `.py` modules in `src/`, and the
notebook is *generated* from them by `build_notebook.py`, so the two cannot disagree.

**4. `report()` left in `__main__`, three separate times.** `pipeline.run()` never executes a
module's `__main__`, so the shipped run printed nothing while the write-up quoted its numbers:

- `s2_ndvi.py` (`:942-949`);
- `crop_type.py` — *"Phase 3 printed nothing at all: banner at 271.0s, next banner at 272.1s,
  zero lines between"* (`:1161-1174`);
- `health_index.py` and `yield_estimate.py` together (`:1342-1348`).

The rule Round 2 wrote after the third occurrence, and which Round 3 enforces structurally:
*"Fixing one instance of a defect class does not close the class. When a rule is written, sweep
every module against it the same day"* (`:1347-1348`).

### Other Round 2 incidents worth one sentence each

- **A sign-flip in prose, not code**: `flood_depth = min(T1,T2) − T3` has median **+0.36 dB**,
  described in the write-up as a *rise* of +0.4 dB when the true rise is **−0.36 dB** —
  reproducing exactly the flood-threshold failure Round 1 had already closed twice (`:1182-1192`).
- **A schema gate that was a prefix check**: `submission.csv` shipped a sixth column because
  `validate()` compared `sub.columns[:len(REQUIRED)]` (`:1362-1372`). Round 3 uses full column
  equality.
- **A GDAL borrowed-reference use-after-free** in the figure code that killed the Kaggle kernel
  with no traceback and looked exactly like OOM (`:682-700`). Hence the standing `.Clone()` rule.
- **Three separate OOM chases** where the phase that reported the death was only the one that
  happened to allocate last (`:583-709`); peak RSS came down from 2,850 MB to ~1,470 MB. Round 3
  carries the scar as a per-phase peak-RSS banner in `pipeline.py:79-92`, and has recorded no
  OOM incident of its own.
- **API version skew between Kaggle and local**: OGR's `Memory` → `MEM` rename in GDAL 3.11
  (`:559-565`), `np.trapz` → `np.trapezoid`, `boxplot(labels=)` → `tick_labels=` (`:569-573`).
- **Length estimation was wrong by 5–10×, three times.** Sentence-level polish passes aimed at
  cutting 150–200 words delivered 26, 47 and 5. Only deleting whole blocks worked, and only a
  rendered page count (headless Chrome → pypdf) revealed the write-up was 5 pages when believed
  to be "~4.5" (`:1135-1149, 1253-1281`).

### What Round 2 handed forward

`farm_crops.csv`, 966 rows, crops exactly `{Rice, Cotton, Maize, Bajra, Groundnut}`, with
`crop_confidence ∈ {high, low}`. Round 3 reads it for three things and nothing else: the
canopy-sign arbitration, the leave-future-out back-test, and the label-sensitivity term. It is
this team's own model output from a previous round, not competition data, and a copy ships at
`kaggle_dataset/round2_crops.csv` (`README.md:35-39`).

---

## A3. Round 3 — the live round

*(Citations are Round 3 files. Every number is printed by `logs/pipeline_clean.log`.)*

### The problem, stated exactly

Forecast **final yield at harvest** for 966 plots from six Capella X-band HH SLC passes, plus a
village rollup by crop. No ground truth, no leaderboard, no scored metric.

**Two things the brief says that the files do not**, and both are stated in the write-up
rather than worked around:

1. The Overview promises "966 farm plots across an expanded set of villages."
   `Sokhda_Farms.shp` has 966 features, every one `VILLAGE='Sokhda'`, `ID_1=22`, and
   `Sokhda_Village.shp` holds **exactly one polygon** — the same single village and the same
   plots as Round 2 (`AGENTS.md:63-71`).
2. The Overview says the crop classification is carried forward. **The shapefile has five
   fields and none is a crop** (`docs/data_analysis.md:62-67`). `FID` is the only stable key;
   `id` is 1.0 on every row and one field has an empty name and all-null values. That is why
   `crop_type.py` exists at all.

Consequences that shape the deliverable: one village makes the required village table a
**single row**, so a 500 m zone grid carries the spatial part of the Aggregation criterion.
Median plot is 0.27 ha; **ten parcels enclose under 1e-6 ha** and still carry a row, with area
weighting stopping them from voting; **13 parcels are MULTIPOLYGON**, and every OGR geometry is
`.Clone()`d because a borrowed reference survives locally and segfaults Kaggle with no
traceback.

### The stack, and the pass that fights you

| | date | local (IST) | look | view azimuth | incidence | DOY |
|---|---|---|---|---|---|---|
| T1 | 2025-06-06 | 12:55 | left | 134.7° | 35.24° | 157 |
| T2 | 2025-06-19 | 07:44 | left | 135.1° | 28.77° | 170 |
| T3 | 2025-08-14 | 08:41 | left | 135.1° | 28.69° | 226 |
| T4 | 2025-10-13 | 07:57 | left | 135.0° | 31.53° | 286 |
| **T5** | **2025-10-29** | **01:37** | **right** | **318.4°** | 29.84° | 302 |
| T6 | 2025-11-12 | 19:22 | left | 135.2° | 29.75° | 316 |

T1–T4 are exactly Round 2's stack. **T5 is right-looking**, view azimuth reversed by 184°, so
shadow and layover fall on the opposite side of every bund and building and any row-direction
response reverses with them. It is also a **pre-dawn pass at maximum canopy dew** where T1 is
midday, and the **second-wettest pass** — 63.1 mm of rain in the preceding three days. Geometry,
dew and soil moisture all push backscatter the same way. Read without correction, T5 looks like
a late-October flush of growth in a season that is ending.

**The `20250619` folder contains a byte-identical duplicate of the T1 SLC** — the organiser
packaging bug carried from Rounds 1 and 2. `geocode._slc_path()` builds the filename from the
folder stem rather than globbing, and `load_meta()` cross-checks the STAC acquisition instant
and raises on disagreement. Two independent checks on one defect that would otherwise produce a
wrong temporal trajectory silently (`AGENTS.md:101-106`).

### Ingest, and two things the geometry told us

Calibration follows each scene's own metadata; geocoding is
`gdal.Warp(rpc=True, errorThreshold=0.0)` at a per-scene fitted terrain height.

**Fitted heights: mean −17.34 m, spread 0.89 m, std 0.32 m** across six scenes at five
incidence angles. How they got there matters more than the number. A height error displaces a
pixel along ground range, so **a right-looking scene must displace opposite to a left-looking
one** — and in the height sweep, T5's offsets alone run negative. Nothing was fitted to make
that happen. It is the strongest evidence the height is terrain rather than a tuning knob, and
it was pre-registered (ledger claim 1).

**T5 then broke the co-registration matcher, reporting 108.42 m** against Capella's ~5 m CE90
(`AGENTS.md:233`). It was diagnosed before it was fixed: T5's correlation peak is a third of
the stack's and nearly flat, with a near-zero-lag peak 90 % as strong as the true one — because
at 1 m the edges a phase correlator keys on *are* shadow and layover, and those swap sides under
a reversed look. A two-scale search (coarse 8×-decimated and unbounded, then fine and bounded to
20 m) registers all six. The shipped run: **T3 and T4 at 0.06 m, T6 at 0.13 m, T2 at 0.23 m,
T5 at 1.48 m** over the farm window, with T5 still the weakest correlation peak in the stack.

### Radiometric normalisation: T6 is offset, T5 cannot be

Invariant targets are chosen on 8 m block averages from **T1–T3 only**, then scored on T4 and
T6, which took no part in choosing them. **4.01 dB apart before correction, 0.27 dB after**,
against a 1.5 dB tolerance. Two selection traps were hit and avoided along the way:
thresholding a single date selects speckle maxima, and selecting on all dates biases the result
by construction (`AGENTS.md:290-411`).

**T6 carries a flat +4.28 dB** across the scene's 39 dB brightness range — the same deficit on
the darkest fields and on the built-up tail. No surface process has a flat signature; harvest
darkens fields and leaves roofs alone. So it is the sensor, and one constant removes it.

**T5 refuses the same treatment.** Its residual changes sign with brightness — **−3.54 dB on the
darkest decile to +2.31 dB on the brightest** — because rain brightens rough dark surfaces while
the reversed look extinguishes the dihedrals that make built-up bright. Two mechanisms with
opposite signs; no constant undoes both. **T5's level is therefore never used**, replaced by the
T4–T6 interpolation. Only the residual `t5_anomaly` survives, as a weak covariate.

Its residual is still worth something: 63 mm of rain on 966 plots is a soil-moisture experiment
nobody paid for. It was pre-registered to rank the cohorts by soil exposure, bajra brightest. It
does not — medians run Maize +0.82, Groundnut +0.55, Bajra +0.36 dB (ledger claim 13,
contradicted).

### The frame everything is measured in

Two things make raw levels incomparable across dates:

- **Scene-level bare-soil drift**, measured on **16,473,273 non-farm AOI pixels** that belong to
  no farm polygon and cannot have grown a crop: **the district bare-soil level is +1.65 dB
  higher at T6 than at T1**. Any model comparing November to June without removing that reads a
  radiometric shift as biomass — and, as the back-test showed, a projection rule can win by
  accidentally offsetting it.
- **Each plot's own soil differs.** So **every model input is a departure from that plot's own
  June bare soil**, anchored on the mean of 6 and 19 June (both pre-sowing), with the scene
  drift removed first. Zero means "this plot, at its own soil." That is the only frame in which
  a 0.27 ha plot in one corner of the village is comparable to one in another.

Per-farm statistics are taken on an **eroded polygon core**, so a plot's number is not
contaminated by its bund or by the next field. Validity is ≥ 4 of 6 dates (Round 2 used ≥ 3 of
4). Result: **813 measured, 82 interpolated, 71 imputed** — 153 of 966 plots (15.8 %) are not
fully observed, disclosed per plot in `data_quality`.

### The canopy sign was pre-registered, and it was wrong

Four of the five crops are *darkest* at what looks like peak canopy, which reads as the canopy
attenuating the surface return. That was written into a constant sitting above the code that
opens the optical file — `{Rice: +1, Cotton: −1, Maize: −1, Bajra: −1, Groundnut: −1}` — and has
not been edited since.

Sentinel-2 lands on a Capella date twice, **13 Oct and 12 Nov, both under 0.1 % cloud**. The
decisive form is the **difference** on both instruments, because plot size, soil texture and row
orientation cancel. (T5's only candidate was **79.1 % cloud**, so no T5 control exists.)

**The measured sign is +1 on all five crops.** rho = **+0.569** over n = 813, and per crop:

| crop | n | rho | p | dB per NDVI unit | pre-registered |
|---|---:|---:|---|---:|---|
| Rice | 107 | +0.551 | 7.98e-10 | +7.84 | + — agrees |
| Cotton | 92 | +0.569 | 3.26e-09 | +4.01 | − — **contradicts** |
| Maize | 251 | +0.647 | 3.21e-31 | +3.74 | − — **contradicts** |
| Bajra | 142 | +0.334 | 4.93e-05 | +1.90 | − — **contradicts** |
| Groundnut | 221 | +0.705 | 1.58e-34 | +5.04 | − — **contradicts** |
| **ALL** | **813** | **+0.569** | 8.11e-71 | +4.93 | mixed |

That p assumes 813 independent plots, which this project's own Moran's I says they are not. The
honest statement is a **500 m spatial block bootstrap over 999 draws and 50 blocks:
rho = +0.569, 95 % [+0.508, +0.618]**. Both are printed; the interval is named as the honest one.

**Greener is brighter here.** The most likely reading is that these are small, rough,
row-planted fields on soil that does not stay smooth, so the volume term from an erect canopy
outruns the attenuation term. The sign-agnostic `|departure|` design scored **rho = −0.085** —
not conservative but measurably empty — so `phenology.py` was rebuilt rather than patched.

The same test refused the per-plot harvest date that had been promised: plots the SAR called
"standing" were the *least* green, one-sided **p = 1.00**. Three canopy samples with a 60-day
September gap cannot locate a transition. It was deleted and replaced with a continuous
`cleared_fraction`, which validates at **rho = −0.529** (n = 479, p = 6.9e-36).

### Crop labels, re-derived from six dates

Nine clusters over 20 seeds by co-association k-means on nine phenology descriptors, after a
non-crop screen removes 51 plots (34.3 ha, 7.7 %). Two tiers:

- **Tier 1 — a label a physical threshold supports.** Rice from its flood-then-rise signature;
  Cotton from a plot-level rule, `canopy_end_db ≥ 1.5 dB` on 12 November — the crop still
  standing when everything else has been cleared. Cotton moved from Round 2's cluster z-score to
  a plot-level absolute threshold because cotton showed a smooth monotone optical gradient with
  no cluster break.
- **Tier 2 — allocated, not measured.** The district crop mix applied to the residual along the
  signed November-canopy axis. The shipped table marks which is which.

**Tier-1 coverage is 26.5 % of area (170 farms, 118.5 ha), below Round 2's 31.6 %.** That was a
pre-registered target and it is recorded as **not met** rather than met by loosening a
threshold (ledger claim 7). What improved instead: tier-1 stability is **100 % across every
clustering setting tried** (7/9/11 clusters, 5/20/40 seeds) where Round 2's ranged 87.9–100 %,
and both tier-1 crops are now independently corroborated by optical data that did not assign
them. Round 2's cotton included the long-duration parcels; removing them cost area and bought a
label that survives a held-out test at p = 1.26e-11.

`COTTON_NOV_DB` is the least stable threshold in the pipeline and is reported as such:

| threshold | plots | area | share |
|---|---:|---:|---:|
| 1.0 dB | 132 | 79.2 ha | 17.7 % |
| **1.5 dB (shipped)** | **57** | **39.3 ha** | **8.8 %** |
| 2.0 dB | 36 | 28.7 ha | 6.4 % |

1.5 dB is three times the 0.5 dB plot-to-plot soil spread measured on the two June dates that
cannot contain a canopy — set from that anchor, not from the resulting area.

**Twelve parcels are screened out as long-duration** (above 1.5 dB over their own soil on all
three canopy dates). They were pre-registered as an orchard or plantation. The reserved June
scene **falsified that**: they are bare in June, 0.247 against 0.397 (p = 1.1e-04), and their
June radar level is −20.24 dB against −20.42 for everything else. Nine of twelve never fall
more than 0.5 dB between consecutive passes and all stay green to 16 January. Not an orchard —
a long-duration crop sown with the monsoon and still standing in January; sugarcane and banana
both fit and both are grown in Vadodara. The constant was renamed `PERENNIAL_MIN_DB` →
`LONG_DURATION_MIN_DB` and the finding kept (ledger claim 6).

### The model

```
Y_final(plot) = Y_ref(crop, kharif 2025-26) × a(season-complete canopy integral)
```

**One modulation term, not three.** Round 2 measured its own problem: within a cohort its health
index and yield estimate correlated at exactly 1.000. A vigour index built from the six canopy
departures would be built from *the same measurements the season integral already integrates*,
so multiplying them would count one measurement twice while presenting itself as two
independent lines of evidence — *"worse than useless under a rubric that scores defensibility"*
(`docs/model_architecture.md:15-18`).

**Term 1 — `Y_ref`, and the assumption it inverted.** The published Gujarat kharif yield for
the forecast season itself, DA&FW Directorate of Economics & Statistics, 3rd Advance Estimates:

| crop | 2025-26 kg/ha | rank in 5 yrs | vs 5-yr mean | basis |
|---|---:|---|---:|---|
| Rice | 1675 | 5th (lowest) | 69.7 % | paddy |
| Maize | 2035 | 1st (highest) | 110.9 % | grain |
| Bajra | 1362 | 5th (lowest) | 69.5 % | grain |
| Groundnut | 2734 | 4th | 106.6 % | unshelled pods |
| Cotton | 551 lint → **1621 seed cotton** | 2nd | 98.0 % | kapas, 34 % ginning outturn |

Sokhda's monsoon measured **1098.5 mm against a 1995–2024 mean of 923.1 mm — 119.0 % of mean,
z = +0.66**, so the plan was to adjust last year's yield upward. **DA&FW says the opposite.**
Gujarat kharif rice and bajra hit **five-year lows, −29 % and −26 %, in an excess-rain season**:
the state announced flood relief for Vadodara after the Narmada overflowed 16–18 September,
inside the paddy grain-fill window. Had the planned elasticity been applied, rice would have
been forecast *above* a reference the state measured 29 % below (ledger claim 8, contradicted).

The rainfall anomaly is still computed and printed, as corroboration of direction only — it is
deliberately **not** a multiplier, because the official estimate already measures the outcome
and multiplying would double-count it. No Vadodara district uplift is applied either, because
no district-level 2025-26 estimate is published; Vadodara ranks 1st in Gujarat for maize yield
and 2nd for cotton, so those two are **conservative by a known sign**, stated rather than
corrected for.

**Term 2 — the season canopy integral.** A trapezoid over each plot's signed departures, plus a
projection to that crop's calendar harvest (Bajra DOY 270, Maize 288, Groundnut 305, Rice 310,
Cotton 380). Two choices inside it were measured, not assumed:

- **Signed, not clipped.** Clipping degenerates a cohort: **80.6 % of bajra sits at exactly the
  cohort median of zero**, so every one of them would receive `a = 1.000` and the whole crop
  would collapse onto `Y_ref`. Signed also scores better against optical, **+0.564 against
  +0.472** — and because the form was *chosen* on those scores, 13 Oct and 12 Nov cannot then
  validate it. That is what the reserved scenes are for, and it is stated as such.
- **A flat hold, not a decaying limb.** See A4 — the back-test deleted the decaying rule.

The response is `centred_factor(integral, crop, span=0.30)`: a bounded monotone map from a
plot's rank *within its own crop cohort* to a multiplier in [0.70, 1.30], centred so the cohort
median lands exactly on 1.0. **The model redistributes within a cohort; it does not move the
cohort.** Without centring, the arithmetic quietly drifts a typical plot below its own state
reference before anything is measured. `PLAUSIBLE_T_HA` is a raise-on-violation gate, not a
clip: a plot outside its crop's band stops the run rather than being pulled quietly back inside.

### What makes it a forecast rather than a restatement

`extrapolated_fraction` ships per plot. **Cotton is the only crop with a material projected
share — 0.56 mean, 0.75 at p90 — and every other crop is closed by observation**, 139/139
bajra, 341/341 groundnut, 313/313 maize, 111/111 rice. Round 2 discounted the unobserved
remainder with a hand-set constant; Round 3 replaced the constant with measurement, because the
six-date stack now contains the harvest for four crops of five.

### Aggregation, and the answer

**893.9 t forecast at harvest over 447.5 ha, 2.00 t/ha area-weighted.**

| crop | plots | ha | Y_ref | t/ha | p10–p90 | tonnes | projected |
|---|---:|---:|---:|---:|---|---:|---:|
| Groundnut | 341 | 124.7 | 2.73 | 2.66 | 2.19–3.47 | 331.7 | 0 % |
| Maize | 313 | 139.6 | 2.04 | 1.96 | 1.50–2.50 | 273.7 | 0 % |
| Rice | 111 | 76.0 | 1.68 | 1.69 | 1.24–2.11 | 128.2 | 0 % |
| Bajra | 139 | 61.8 | 1.36 | 1.40 | 1.20–1.64 | 86.6 | 0 % |
| Cotton | 62 | 45.5 | 1.62 | 1.62 | 1.19–1.93 | 73.8 | **56 %** |
| **ALL** | **966** | **447.5** | — | **2.00** | 1.36–3.04 | **893.9** | 6 % |

Everything is **area-weighted in hectares**, and production is the true sum `Σ(yield × area)`
rather than a mean of ratios. The village row is the sum of the shipped plot file, rounded once
*before* aggregating — `cross_check` caught a **0.0015 t** discrepancy caused by rounding after
aggregation (`docs/submission.md:97`, `docs/research_log.md:371`; the gate is in the shipped run,
the historical figure is not), which would have let a judge adding up the CSV get a different number from the
summary.

The rollup is gated on the **village geometry, not the village name**: 962 of 966 plots assign
to the same village by largest shared area as by attribute, **0 disagree**, and **100.00 % of
digitised parcel area sits inside the boundary**. The village polygon encloses **1174.1 ha**, so
the 447.5 ha of digitised parcels is **38.1 % of Sokhda** — the mapped farmland, not the
village. Everything else inside the boundary is not forecast and is not claimed.

One village makes the required village table a single row, so a **46-cell 500 m grid** (≥ 5
farms per cell, covering 946 of 966 farms and 437.9 of 447.5 ha) carries the spatial part of
the aggregation: **1.50 to 2.80 t/ha around a village figure of 2.00**.

---

## A4. Validation is the deliverable

Fifty of the hundred rubric points are Technical Soundness plus Plausibility & Defensibility,
and there is no label to fit. So the validation is not a step after the model — it *is* the
submission. Nine independent lines, in the order they carry weight.

### A4.1 The pre-registration ledger — 17 claims, 9 contradicted

Every hypothesis written down **before** the data that could test it was opened. The ledger
lives in the source as `validate.LEDGER`, is printed by every run, and is drawn as
`figures/ledger.png`. The counts are computed from the tuple rather than typed beside it, so an
eighteenth claim cannot leave the paragraph stale. **No entry has been edited to agree with a
later measurement.**

| # | stage | claim, as written | outcome |
|---|---|---|---|
| 1 | S1 | A right-looking scene must displace opposite to a left-looking one under a height error | **held** — T5 alone reverses sign |
| 2 | S2 | Invariant built-up targets can carry a per-date radiometric offset | **held for T6** (+4.28 dB), **refused for T5** |
| 3 | S3 | A closing canopy attenuates the surface return at X-band HH, so peak canopy is the darkest date | **contradicted** — the sign is +1 |
| 4 | S4 | `EXPECTED_SIGN = {Rice +1, Cotton −1, Maize −1, Bajra −1, Groundnut −1}` | **contradicted on four of five**; module rebuilt |
| 5 | S4 | A per-plot harvest DOY can be recovered from the canopy curve | **contradicted** — one-sided p = 1.00; deleted |
| 6 | S5 | The parcels above 1.5 dB on all three canopy dates are an orchard | **contradicted** — bare in June, p = 1.1e-04 |
| 7 | S5 | Six dates raise tier-1 coverage above Round 2's 31.6 % | **not met** — 26.5 % |
| 8 | S6 | A wet monsoon means an above-average season, so `Y_ref` adjusts upward | **contradicted** — rice −29 %, bajra −26 % |
| 9 | S8 | The fitted senescence limb beats persistence at 30 days | **contradicted** — +0.284 became −0.409; deleted |
| 10 | S9 | Cotton is the greenest of the five on the reserved 12 December scene | **held** — 0.690, p = 1.26e-11 |
| 11 | S9 | Plot orientation does not drive `t5_anomaly` (\|rho\| < 0.2) | **held** — rho = −0.051, p = 0.195 |
| 12 | S15 | Re-ranking tier 2 separates the cohorts better on residualised NDVI | **contradicted** — wrong axis; corrected p = 0.43 |
| 13 | S15 | `t5_anomaly` orders the cohorts Bajra > Maize > Groundnut | **contradicted** — Maize +0.82 > Groundnut +0.55 > Bajra +0.36 |
| 14 | S32 | Skill is non-positive at every horizon and decays as the horizon lengthens | **contradicted** — +0.140 at 60 d, −0.180 at 30 d |
| 15 | S33 | C-band: cotton declines less than the annuals over 15 Nov – 21 Dec | **held** — +0.985 dB against an annual median of −0.020 |
| 16 | S33 | C-band: the 10 Oct – 15 Nov change correlates positively with the X-band T4–T6 change | **held** — rho = +0.248 |
| 17 | S33 | C-band: a 6-pass integral ranks plots like a 13-pass one, rho ≥ 0.8 | **held** — rho = +0.915, n = 956 |

**Nine contradicted, one not met, seven held.** The contradicted ones did more for the model
than the ones that held: four of them deleted a term, a rule or a whole module, and the twelfth
deleted a result this project had already published.

### A4.2 The leave-future-out back-test — the headline, and it is negative

Fit on T1–T4 (6 Jun to 13 Oct, exactly Round 2's data), predict the withheld 12 November pass,
score against what was actually observed. 813 measured plots, 2000-bootstrap CIs, and **Round
2's four-date crop labels so nothing about November leaks into any predictor**.

On the raw level, with the +1.65 dB district drift handed to every predictor (the control):

| predictor | RMSE dB | skill vs persistence | 95 % CI |
|---|---:|---:|---|
| B1 persistence | 1.536 | +0.000 | — |
| B2 cohort mean at T4 | 1.719 | −0.253 | [−0.418, −0.117] |
| B3 linear extrapolation | 1.938 | −0.592 | [−0.693, −0.498] |
| **B4 shipped rule (flat hold)** | **1.625** | **−0.119** | **[−0.280, +0.022]** |
| B5 decaying limb (rejected) | 1.823 | −0.409 | [−0.532, −0.303] |

**The shipped rule does not beat persistence.** Its interval contains zero, and on the 732
plots where the rule actually changes the answer it scores **−0.216** — the fairer number and
the worse one. Both are quoted; neither is buried.

**What the back-test actually bought was a deletion.** The decaying limb was the intended
shipped rule. It looked more principled, it scored **+0.284**, and its CI excluded zero — a
number this project quotes nowhere else. It was suspicious in a specific way: B5 predicts a
*higher* canopy than persistence, and the district bare-soil level rises +1.65 dB between June
and November, so B5 could be winning by being biased in the direction that offsets a drift
neither predictor models. Handing every predictor that drift removed the route to a win and B5
collapsed to **−0.409**. It was deleted and kept in the ladder as B5 so the comparison stays
runnable.

Per crop, on the departure target: the flat hold is the best of the five on Bajra (**+0.352**),
Groundnut (**+0.213**) and Cotton (+0.007), and loses to plain persistence on Maize (−0.581)
and Rice (−0.887). Rice's RMSE of **2.438 dB** is the worst in the table by a wide margin, and
that is physically legible — paddy's exit from a flooded specular surface is the largest, fastest,
most plot-specific transition in the stack.

### A4.3 The horizon curve — and the fifth pre-registration contradicted

One point is not a curve. `backtest.horizon_curve` runs the same experiment at both splits the
six dates admit, label-free predictors only (Round 2's labels have seen T4, so at the
hold-T3-predict-T4 split they would leak the target — which also removes B4's calendar-harvest
zeroing, so the 30-day row is *not* the shipped −0.119).

| fit | predict | days | predictor | RMSE | skill | 95 % CI |
|---|---|---:|---|---:|---:|---|
| T3 | T4 | 60 | persistence | 1.553 | +0.000 | — |
| T3 | T4 | 60 | **flat hold, no calendar** | **1.440** | **+0.140** | **[+0.071, +0.202]** |
| T3–T4 | T6 | 30 | persistence | 1.217 | +0.000 | — |
| T3–T4 | T6 | 30 | **flat hold, no calendar** | **1.322** | **−0.180** | **[−0.330, −0.056]** |
| T3–T4 | T6 | 30 | linear extrapolation | 1.611 | −0.751 | [−0.895, −0.610] |

The pre-registration said skill would be non-positive everywhere and decay with horizon. **It is
positive at the *longer* horizon and negative at the shorter one, and neither interval contains
zero.** The mechanism is phenological, not temporal: the 60-day row predicts 13 October, inside
the growing season, where refusing to let a departure fall below its own soil is right; the
30-day row predicts 12 November, after most of the harvest, where the same refusal is exactly
wrong — and what removes it is the calendar-harvest zeroing this label-free variant had to drop.
**So the curve argues for the shipped design.** It is the first evidence the crop calendar earns
its place.

### A4.4 Two reserved optical scenes nothing upstream could read

**12 December 2025 and 16 January 2026** were reserved from the first fetch, and
`assert_reserved_unread()` fails the run if any module but the validator names them. Both sit
inside the rabi window on purpose, which is what makes them independent and also what limits
what they can test: they cannot score the yield forecast.

They settle one pre-registered claim, and they settle it hard:

| crop | n | NDVI 12 Dec | NDVI 16 Jan | NDVI 10 Jun |
|---|---:|---:|---:|---:|
| **Cotton** | 58 | **0.690** | **0.742** | 0.232 |
| Groundnut | 257 | 0.532 | 0.541 | 0.403 |
| Maize | 277 | 0.505 | 0.565 | 0.378 |
| Rice | 109 | 0.502 | 0.601 | 0.591 |
| Bajra | 112 | 0.474 | 0.647 | 0.356 |

**One-sided Mann-Whitney, cotton greater than the rest on 12 December: p = 1.26e-11.** A SAR-only
label picked the right plots on a scene it had never seen, and cotton is the only label greener
in January than December.

**The negative control matters as much as the test.** Had cleared plots been bare in December,
the first claim would be measuring "good field" rather than "still-standing cotton". They are
not bare: cleared plots read 0.488 against a population median of 0.520 — they are under rabi.

The same scenes falsified the orchard reading of the long-duration screen (§A3).

### A4.5 An independent instrument, used as a witness

Nothing in the Capella stack observes the window in which cotton is held flat — the last pass
*is* the last observation of any kind, and that assumption carries 56 % of cotton's canopy-days
and 73.8 t. So something that did observe it was found: **16 free Sentinel-1 IW RTC passes,
12 June – 21 December 2025, VV+VH at 10 m**, terrain-corrected to gamma0 on the same UTM 43N
grid.

**This is not the Sentinel-1 fusion Round 1 rejected.** That decision stands — 27 pixels per
plot at 10 m, and the fusion measured negative on this AOI. What was rejected was C-band as a
per-plot *feature*. `s1_audit.py` feeds no feature, no label and no forecast, and
`tests/test_pipeline.py::test_s1_audit_is_not_imported_by_any_model_module` fails if any module
in the chain imports it. If the village total ever moves when this module is present, the
independence is gone.

Three claims, written into `s1_audit.PREREG` before a single Sentinel-1 pixel was read:

**P14 — the projection audit.** Cohort VH departure from its own June soil:

| cohort | 15 Nov | 27 Nov | 9 Dec | 21 Dec | change |
|---|---:|---:|---:|---:|---:|
| **Cotton** | **+1.741** | **+1.750** | **+1.570** | **+2.726** | **+0.985** |
| Maize | −0.754 | −0.612 | −0.962 | −0.553 | +0.201 |
| Bajra | −1.106 | −0.696 | −1.202 | −0.908 | +0.198 |
| Groundnut | −0.486 | −0.440 | −0.716 | −0.725 | −0.239 |
| Rice | −1.883 | −1.788 | −2.192 | −2.466 | −0.582 |

**Cotton +0.985 dB against an annual-cohort median of −0.020 dB over 36 days: held.** Cotton is
the only cohort above its own June bare soil on any date after 12 November, and it stands
2.2–3.3 dB clear of every other cohort throughout. The flat hold is not optimistic. What this
does *not* establish is that the held level is the right one — a rising cross-pol return late in
cotton can be canopy, boll opening or structure, and separating those needs a polarimetry this
stack does not have.

Unplanned, and worth more than the test it came from: those 62 cotton plots separate on a
**different sensor at dates no module had opened**. That is a second independent corroboration
of the tier-1 cotton label.

**P15 — cross-band sign.** `CANOPY_SIGN = +1` rests on two Sentinel-2 scenes and nothing else.
C-band VH change 10 Oct → 15 Nov against X-band departure change 13 Oct → 12 Nov:
**rho = +0.248, n = 813, p = 7.88e-13.** Positive, so held — and far weaker than the +0.569 the
same construction scores at X-band, which was stated in advance as the expected shape. The sign
generalises across band and polarisation, and how far it generalises is now a number.

**P16 — sampling adequacy, and it prices the competition's own premise.** Nothing in the Capella
stack can test whether six acquisitions are enough, because six is all there is. C-band can:
build the integral from all 13 passes over DOY 163–319, then from only the six nearest the
Capella dates. **rho = +0.915, n = 956, median difference 0.27 dB.** Held against the
pre-registered 0.8. Six acquisitions on this calendar recover the ranking a 13-pass integral
gives — measured on an instrument that had no part in building the model, and needing no ground
truth.

**The honest caveat the run prints itself: these are confirmations, and a confirmation is worth
less than a contradiction.** Two of the three test whether this project's own design choices
were adequate, which is an easier question than the ones the ledger got wrong.

### A4.6 Confound controls, declared before they were run

- **Look direction.** T5 is the only right-looking pass and a row-orientation effect reverses
  with look direction. Row azimuth is estimated as the PCA principal axis of each parcel's
  exterior ring; on the 650 parcels elongated enough (axis ratio ≥ 1.5) for that to mean
  anything, **rho = −0.051 and +0.051, both p = 0.195**, both inside the ±0.2 threshold set
  beforehand. Clean.
- **Diurnal and dew.** Handled by the persistent-scatterer scene offsets rather than argued
  about — held-out left-looking dates 4.01 dB apart before, 0.27 dB after.
- **Scene moisture in the sign measurement.** T4 and T6 carry near-identical 14-day antecedent
  rainfall (11.9 against 12.2 mm), so the differenced sign test is not measuring a wetting
  event. **Plot-level irrigation is not excluded** and is recorded as an open caveat.
- **Residual incidence angle.** `gamma0 = sigma0/cos θ` verified on invariant targets across
  28.69–35.24° rather than assumed; what remains is a scene offset, not an angle trend.

### A4.7 Spatial coherence

Moran's I over 8 nearest neighbours, **999-permutation** null (the parcel graph is irregular, so
a normal approximation is not safe):

| quantity | I | permutation mean | p | permutations reaching I |
|---|---:|---:|---|---|
| yield forecast | +0.279 | −0.001 | < 0.001 | 0 / 999 |
| season integral | +0.187 | −0.001 | < 0.001 | 0 / 999 |
| **within-crop residual** | **+0.151** | −0.001 | **< 0.001** | 0 / 999 |

The first two are expected — neighbouring fields share soil, water and management. The third is
the informative one: after conditioning on the crop label there is still real spatial structure
left. Had it been near zero, the residual would be plot-level speckle and the forecast would be
five numbers with noise on top.

**The `<` is the point, and it was wrong until 2026-08-31.** With the add-one estimator
`(1+r)/(n+1)`, a 199-permutation null cannot report anything below 1/200 = 0.005 — so the
`p = 0.005` this table used to carry on all three rows was the test's own resolution, not a
measurement. Worse, 0.005 sits above a Bonferroni threshold for the ~30 p-values this run
prints, so the statistic had been fixed below the multiplicity it has to survive.

### A4.8 The null ablation — what the radar actually buys

Take the radar out entirely, `a() ≡ 1`:

- village total **910.1 t** against the shipped 893.9 t — a difference of **−16.2 t, −1.78 %**;
- but the **median plot moves 11.8 %**, 30.0 % at p90, and **734 of 966 plots move more than 5 %**.

That gap is the whole of what the radar buys, and it is a **redistribution**: the level comes
from `Y_ref` and the season integral only decides which plots sit above and below it. The
ablation runs through the shipped code path (it is the span-0 row of the ACCUM_SPAN sweep)
rather than a re-implementation.

### A4.9 The uncertainty budget — every row is a chain re-run

Not a formula propagated through the model. Each row is the **entire pipeline re-run under that
one change**:

| source | low t | high t | ± t | ± % | basis |
|---|---:|---:|---:|---:|---|
| reference yield `Y_ref` | 804.5 | 983.3 | **89.4** | 10.0 | ±10 % on the DA&FW 3rd Advance Estimate |
| district crop mix | 832.3 | 955.3 | **61.5** | 6.9 | 200 draws at σ = 0.51 in log-share |
| crop labelling | 880.3 | 893.9 | 6.8 | 0.8 | whole chain re-run on Round 2's labels |
| speckle on the farm means | 890.1 | 895.6 | 2.7 | 0.3 | 1000 draws at 4.34/√N dB per plot |
| tier-2 tie ordering | 893.9 | 893.9 | 0.0 | 0.0 | 200 permutations of the tied keys |

**External assumptions sum to 150.9 t; everything the radar and this pipeline contribute sums
to 9.5 t.** That is the shape a no-ground-truth forecast should have, and saying it first is
stronger than having it extracted.

**How the district-mix row was priced, since it is the one most open to challenge.** Two crops
are assigned by threshold rules, *not* by the mix, so the mix can be scored against them:

| | district | measured | log-ratio |
|---|---:|---:|---:|
| Rice | 0.26 | 0.170 | −0.426 |
| Cotton | 0.32 | 0.102 | −1.147 |

It overstates both. The **spread** of those log-ratios, **σ = 0.51**, is the scale used to
perturb the three tier-2 weights — a common bias renormalises away; what moves the split is the
crops disagreeing by different amounts. This is a scenario, and it assumes the prior errs on the
three crops that cannot be checked by about as much as it errs on the two that can. An
assumption — but a measured one, and better than assuming the prior is exact.

### A4.10 The answer to the strongest attack: does X-band saturate?

The standing criticism of X-band for crop work is that a 3 cm wave saturates early. It was
answered by measurement, on 813 plots binned by NDVI, free of any crop label:

| bin | n | NDVI mean | departure dB | dB per NDVI unit |
|---|---:|---:|---:|---:|
| 1 | 136 | 0.288 | −1.328 | — |
| 2 | 135 | 0.364 | −0.350 | +12.89 |
| 3 | 135 | 0.426 | −0.051 | +4.85 |
| 4 | 136 | 0.504 | +0.188 | +3.07 |
| 5 | 135 | 0.605 | +1.054 | +8.56 |
| 6 | 136 | 0.701 | +1.452 | +4.15 |

**Monotone increasing across all six bins**, with the increment ending at +4.15 rather than
collapsing toward zero. Over the NDVI range these fields actually occupy, the response does not
saturate. It is a **bounded** answer — the top bin averages NDVI 0.70, so this says nothing
about biomass beyond what Sokhda grew — and the model claims a within-cohort *rank* on an
external level, not a biomass retrieval. A compressed top end would bound the ranking's dynamic
range rather than invert it.

Two published anchors were added afterwards, so neither influenced a design decision
(`docs/sar_research.md:56-106`):

- **Inoue, Sakaiya & Wang 2014**, *Remote Sensing* 6(7):5995 — of all canopy variables tested,
  **panicle biomass** was the one best correlated with X-band σ⁰; X-band has *"limited
  capability to assess the whole-canopy variables"* but is *"promising for direct assessments of
  rice grain yields."* That is the saturation objection stated precisely, and it is aimed at a
  retrieval this model never attempts. The same paper's **within-image "water-point"
  differencing** is a published antecedent for this project's departure-from-own-bare-soil
  anchor, arrived at independently.
- **Prashnani & Justice 2026**, *Remote Sensing* 18(8):1238 — Central India, kharif, four of the
  same five crops: **multiclass SAR accuracy 48.3 %** with systematic cereal–legume confusion,
  and cross-district transferability highest for **rice (74 %) and cotton (72 %)**. Those are
  exactly this project's two tier-1 crops, and the three it refuses to claim are exactly the
  three that do not transfer. Independently derived, different data, different state.

### A4.11 What is evidence about the process rather than the model

Two things the current deck never mentions and a panel would credit:

- **Eight Kaggle runs, five of them after the audit, and every one reproduced the local log.**
  The eighth matched **51 of 51 signature lines**. Cross-platform reproduction is what found the
  tier-2 tie defect in the first place — two machines, the same code, 39 plots different.
- **An adversarial audit of this submission, by this team, that found real defects.**
  `docs/judge_report.md` scored it **78/100** on an explicitly internal basis, and **88/100**
  after its findings were actioned. It is shipped **unedited** — *"a report that quietly edits
  itself is worth nothing"* — with a status table (§23) recording what is closed and what is
  not. Its findings included two false claims in the project's own leakage analysis, a p-value
  that was a resolution floor, and a default argument that had silently invalidated a
  pre-registered test whose "CONFIRMED" verdict had already been published in four documents.
  No panel has seen that scorecard; it is an internal estimate and should be presented as one.

---

## A5. What changed between rounds, and the measured reason

| | Round 1 | Round 2 | Round 3 | why it changed |
|---|---|---|---|---|
| **unit of analysis** | pixel, clustered per village | **farm plot** | farm plot | speckle averages to 0.094 dB over ~2,100 px; Round 1's separability ceiling was a *pixel-level* ceiling |
| **crop labels** | ranked heuristic on 7 clusters | 2 tiers, 4 dates | 2 tiers, 6 dates | harvest timing is a discriminator four dates could not provide |
| **tier-1 coverage** | — | **31.6 %** | **26.5 %** | a pre-registered target **missed**, recorded as missed. Stability rose from 87.9–100 % to 100 %, and both tier-1 crops gained independent optical corroboration |
| **the canopy sign** | assumed | **measured** (+1), same-day S2 | measured again, differenced, per crop | Round 2 called assuming it "the single largest avoidable error"; Round 3 pre-registered the opposite and was wrong on four crops of five |
| **model chain** | area only | `Y_ref · f(health) · a · g` | **`Y_ref · a`** | health index and yield estimate correlated at exactly **1.000** within a cohort — one ranking under two names |
| **season completeness** | — | hand-set `g`, Cotton **0.45** | measured `extrapolated_fraction`, per plot | six dates close four crops of five by observation; only cotton is projected, at 0.56 |
| **projection rule** | — | — | **flat hold**, not a decaying limb | the decaying limb scored +0.284 and collapsed to −0.409 under a drift control; deleted |
| **`Y_ref`** | — | individually-sourced prior-season figures | **DA&FW 3rd AE for 2025-26** | the season's own official estimate exists and inverts the rainfall assumption — this is most of why 1001.6 t became 893.9 t |
| **code home** | one script per experiment | `%%writefile` cells only | real `src/*.py`, notebook **generated** | a module and a notebook cannot disagree if one is built from the other |
| **validation** | leaderboard MSE | NDVI correlation, reserved scene | 9 independent lines, 17 pre-registered claims | there is no metric left to iterate against |
| **external data** | WorldCover, IO LULC, S1, S2 | S2, district statistics | S2, NASA POWER, DA&FW, CGWB, **S1 as a witness only** | S1 fusion measured negative in Round 1 and stays rejected as a *feature*; as an independent witness it is new |
| **uncertainty** | — | — | **5-row budget, each a chain re-run** | with no ground truth, the honest headline is which assumptions own the width |

**Three lines that carry the arc**, if the deck only has room for three:

1. **Round 1 found the ceiling.** X-band HH cannot separate structurally similar dryland crops
   at pixel level; the mask, not the classifier, was the lever.
2. **Round 2 moved the unit of analysis to the plot**, which put the ceiling somewhere else —
   and then measured two defects in its own output that Round 3 exists to fix.
3. **Round 3 removed model capacity and added validation**, because the scoring changed from a
   metric to a rubric and the labels went away.

---

## A6. War stories — the bugs that cost a session, and the rules they wrote

Each of these is a real incident. Several became standing rules that are still enforced by
tests.

**`gdal.Warp(rpc=True, errorThreshold=0.0)` — never the approximate transformer.** rasterio's
WarpedVRT fallback *"filled 100 % of the AOI grid instead of the true ~16.5 % swath"*
(`Round 1/AGENTS.md:90`). Verified correct only when it reproduced the documented failed and
sliver village lists exactly.

**`.Clone()` every OGR geometry.** GDAL hands out borrowed references to sub-geometries. A
use-after-free on MULTIPOLYGON survived locally and killed the Kaggle kernel with no traceback,
masquerading as OOM (`Round 2/AGENTS.md:682-700`). 13 of the 966 parcels are MULTIPOLYGON.

**Never glob `*.tif` in a scene folder.** The `20250619` folder ships a byte-identical duplicate
of the T1 SLC — three rounds running. The filename is built from the folder stem, and the STAC
acquisition instant is cross-checked and raises on disagreement.

**No `try/except` around a data path.** *"Every 'graceful fallback' is somewhere a validation
gate can silently stop running"* (`Round 1/AGENTS.md:781`) — found on deadline day, where
hardcoded paths with fallbacks would have degraded quietly on Kaggle with a gate printing
SKIPPED and a figure vanishing. Round 3 ships **one `try/except` across 16 modules**, and it is
not on a data path.

**Every `report()` is called from `pipeline.run()`, never left in `__main__`.** Round 2 shipped
this defect **three separate times** (§A2). `pipeline.run()` does not execute a module's
`__main__`, so the shipped log printed nothing while the write-up quoted a dozen numbers from
it.

**T5's 108.42 m co-registration failure.** Diagnosed before it was fixed: the correlation peak
is a third of the stack's and nearly flat, with a near-zero-lag peak 90 % as strong as the true
one, because at 1 m the edges a phase correlator keys on *are* shadow and layover and those swap
sides under a reversed look. Fixed with a two-scale search justified by geometry rather than
convenience — and `fit_height` explicitly opts out of the bound, because its sweep mis-geocodes
on purpose. Unit-checked on synthetic translations to under 0.01 px.

**The Kaggle 39-plot disagreement (S14).** The SAR chain reproduced to the digit; the crop
labels did not. Maize 316 → 277, Bajra 136 → 175, village total 898.3 t → 896.6 t. Root cause:
the tier-2 ranking axis was the November canopy **clipped at zero**, so **403 of 793 allocated
plots sat at exactly 0.0** (183.0 ha), the Bajra/Maize cumulative-area cut fell *inside* that
tie block, and pandas' default quicksort — which is not stable — settled it differently per
machine. No gate caught it, because **the number was perfectly stable on either machine alone**.
The signed departure separates the same plots across 392 distinct values; the sort is now a
stable mergesort on `[axis, farm_id]`. One machine could never have found this.

**The ANOVA that residualised against the pre-fix axis (S24).** After S15 changed `TIER2_AXIS`
to `departure_T6`, `s2_ndvi.label_information_test(axis="g0_db_filled_T4")` kept using its
**default argument**, which the call site never overrode. The log line claimed it had
residualised against the current ranking axis. It had not. Corrected, the result **reversed**:
tier-2 labels carry no NDVI information beyond their own axis (η² 0.0023, F 0.847, **p = 0.43**)
while the **tier-1 control passes** (p = 0.005) — and the control passing is what makes the
tier-2 failure readable rather than a dead test. `axis` is now a required argument. The
project's own summary: *"The broken test had been flattering us, and we published it."*

**The phase-ordering bug that only appears on a clean machine (S12).** `farm_features` ran
before `scene_diagnostics`, and `farm_features` raises if `scene_offsets.json` is missing rather
than defaulting the offsets to zero. So the pipeline completed only when a previous run had left
the file behind, and died on an empty `work/`. **Invisible for exactly as long as nobody started
from empty.**

**The offline claim that was false (S27).** `s2_ndvi` cached the rasters but not the STAC search
responses, and `search()` was called unconditionally *before* any cache was consulted — so an
offline run raised on the first window and never reached the files it shipped. Three documents
claimed otherwise. Fixed cache-first and demonstrated by monkey-patching `urlopen` to raise.
A side effect worth noting: caching the search **pins the reserved-scene choice**, because the
16 January window returns three candidates all at 0.0 % cloud and the winner had been decided by
whatever order Earth Search returned them in — a re-indexed catalogue could have handed a future
run a different held-out scene without saying so.

**The caption that survived three clean re-runs (S30).** Kaggle crops gallery thumbnails to
16:9, and four figures at 2.18–2.40:1 had their sides cut — on `backtest.png` that removed the
"THE SHIPPED RULE DOES NOT BEAT PERSISTENCE" annotation, which is the whole point of the figure.
Fixed by padding the canvas rather than re-laying out ("two days from a deadline is how a working
figure gets broken"). **Then, reading the rendered PNGs rather than grepping them**, a caption on
`reserved_optical.png` still said "no optical input" — the exact sentence corrected everywhere
else, surviving because it lived inside a multi-line `fig.text()` string that a grep on the
write-up's phrasing could not match. **No automated gate reads a rendered image.** It was caught
by looking.

**Three OOM chases (Round 2).** The phase that reported the death was only the one that happened
to allocate last, so the failure kept moving a phase later as upstream memory came down; peak
RSS fell from 2,850 MB to about 1,470 MB. Round 3 carries the scar as a per-phase peak-RSS
banner using `VmHWM` (the high-water mark, which is what fragments the heap and what the kernel
limit is compared against), and has recorded **no OOM incident of its own**.

**Two Kaggle path bugs, same class, ten days apart (S19, S35).** Kaggle mounted the attached
dataset three directory levels deep while the resolver globbed one. Fixed by enumerating three
depths explicitly rather than using `**`, which would stat every SLC raster. The second
occurrence, on the C-band table, was fixed the same way but deliberately **returns `None`
instead of raising** — that table is a derivable cache, not a required input, so its absence
should degrade to recomputation rather than kill the run. The eighth Kaggle run proved it:
`reading the shipped C-band table, /kaggle/input/datasets/sumit1703/s1-per-farm/s1_per_farm.csv`
— three directories deep, only the fixed glob matches.

**A number in the write-up that no run ever printed (S18).** `audit_writeup.py --trace` caught
the claim "Bajra +1.99 dB … Rice +0.24" as a **coincidental substring match** that the untraced
version of the auditor had waved through. Replaced with measured medians. The tracer now writes
a token-to-log-line mapping to `logs/writeup_trace.txt`, so every number in the write-up is
attached to the line that printed it.

---

## A7. Numbers appendix

Everything below is printed by `logs/pipeline_clean.log` (886 lines) unless marked otherwise.
`logs/writeup_trace.txt` maps each write-up token to the line that produced it.

**The headline**
- 893.9 t at harvest · 447.5 ha · **2.00 t/ha** area-weighted · 966 plots · one village
- Groundnut 341 / 124.7 ha / 331.7 t · Maize 313 / 139.6 / 273.7 · Rice 111 / 76.0 / 128.2 ·
  Bajra 139 / 61.8 / 86.6 · Cotton 62 / 45.5 / 73.8
- 46 zones spread **1.50–2.80 t/ha**; village polygon 1174.1 ha, digitised parcels **38.1 %**

**Ingest**
- fitted heights mean −17.34 m, spread 0.89 m, std 0.32 m, six scenes at five incidence angles
- G1 footprint IoU against vendor preview **0.9964–0.9992**
- G2 co-registration over the farm window: T3 0.06, T4 0.06, T6 0.13, T2 0.23, **T5 1.48 m**
  (the vendor's own inter-date disagreement, for the record: up to 7.14 m)
- G3 radiometry: all six pass; NESZ margins 3.6–7.9 dB
- co-valid mask **72.2 %** of the AOI on all six dates; 314 invariant targets of 313,161 blocks
- held-out T4 vs T6 **4.01 dB → 0.27 dB**; T6 offset **+4.28 dB**; T5 residual **−3.54 to +2.31 dB**
- T5 sits **5.4 dB below** the dimmest left-looking date on the invariant targets
- bare-soil drift on **16,473,273** non-farm pixels: **T6 +1.65 dB** vs T1
- data quality: **813 measured / 82 interpolated / 71 imputed** = 153 of 966 (15.8 %)

**Season context**
- kharif 2025 rainfall **1098.5 mm** vs a 1995–2024 mean of 923.1 (median 905.8, sd 266.6) —
  **119.0 % of mean, z = +0.66**
- API14 by pass: T1 26.5, T2 86.9, T3 5.1, T4 11.9, **T5 53.1**, T6 12.2 mm
- `Y_ref` 2025-26 kg/ha: Rice 1675, Maize 2035, Bajra 1362, Groundnut 2734, Cotton 551 lint →
  **1621** seed cotton at 34 % ginning outturn

**Phenology and labels**
- peak canopy median **0.77 dB** (p10 0.00, p90 2.26); peak DOY median 286
- plots with a canopy episode above 0.5 dB: **588 (60.9 %)**
- cleared fraction by 12 Nov: median 0.63, p10 0.00, p90 1.00
- 9 clusters over 20 seeds on 915 plots; silhouette 0.188; consensus stability median 0.84
- tier 1 **170 farms / 118.5 ha / 26.5 %**; tier 2 796 / 329.1 / 73.5 %
- between-crop spread in peak-canopy gamma0 **4.26 dB** against farm-level speckle **0.094 dB**
- non-crop screen removed 51 plots (34.3 ha, 7.7 %); 12 long-duration parcels screened
- dark-flood rice rule: **−0.32 dB median where +6 dB is needed** — not usable, third round running

**The sign and the integral**
- differenced rho **+0.569**, n = 813, p = 8.11e-71; block bootstrap **[+0.508, +0.618]**, 50 blocks
- integral variants: signed **+0.564** · clipped +0.472 · absolute **−0.085**
- clipped puts **80.6 % of bajra** on the cohort median; signed puts 0.7 %
- `cleared_fraction` vs optical change **rho = −0.529**, n = 479, p = 6.85e-36
- `t5_anomaly` vs optical change rho = −0.186; vs 13 Oct NDVI rho = −0.007

**Validation**
- back-test B4 **−0.119 [−0.280, +0.022]**; where the rule fires (n = 732) **−0.216**
- B5 decaying limb **+0.284 → −0.409** under the drift control
- horizon: **+0.140 [+0.071, +0.202]** at 60 d · **−0.180 [−0.330, −0.056]** at 30 d
- reserved 12 Dec cotton **0.690** vs 0.474–0.532, one-sided **p = 1.26e-11**
- negative control: cleared plots 0.488 vs population median 0.520 — under rabi, not bare
- long-duration parcels 10 Jun **0.247 vs 0.397**, p = 1.1e-04 — falsified
- C-band: cotton **+0.985 dB** vs annual median −0.020 · cross-band rho **+0.248** ·
  6-vs-13 passes rho **+0.915**, n = 956, median diff 0.27 dB
- look direction rho **−0.051**, p = 0.195, n = 650
- Moran's I: forecast +0.279 · integral +0.187 · **within-crop residual +0.151**, all p < 0.001
- ANOVA tier 2 η² 0.0023, F 0.847, **p = 0.43**; tier-1 control F 8.109, **p = 0.005**
- null ablation **910.1 t** (−1.78 %); median plot **11.8 %**, p90 30.0 %, 734/966 move > 5 %
- ACCUM_SPAN 0.15→0.45: 902.0 → 885.8 t, **±0.9 %**
- budget: `Y_ref` **±89.4** · district mix **±61.5** · labels ±6.8 · speckle ±2.7 · ties ±0.0 t →
  **external 150.9 t vs radar 9.5 t**
- label sensitivity: 893.9 t on Round 3 labels vs **880.3 t** on Round 2's, **+1.5 %**;
  agreement 40.9 % overall, **91 % on rice**

**Reproduction**
- **8 Kaggle runs**, the eighth matching **51 of 51** signature lines
- 53 tests collected by `pytest`; the write-up is 1999 words
- one `try/except` across 16 modules, and it is not on a data path

---

# PART B — THE SLIDE SCRIPT

**What already exists.** `Sokhda_Goa_Finals.pptx` holds **11 slides**, built by
`build_deck.py` from the figures in `figures/`. Every image on a slide is a file written by
`figures.py` from the delivered CSVs, so **a slide cannot disagree with the run** the way a
hand-built deck eventually does. The speaker notes below are the ones already in the file, and
they are sized for a ten-minute talk. Slides 1–11 are **built**; the three at the end are
**suggestions, not in the file** — adding one means adding a `dict` to `SLIDES` in
`build_deck.py` and re-running it.

The bullets under each slide are new here. The current slides carry a title, a kicker and a
figure and nothing else, which is the right density for a room; the bullets are for you, in case
you want them on the face, and for whoever is not presenting.

**Timing.** `build_deck.py` prints the notes word count against 150 and 140 wpm on every build,
measured against the 10-minute slot. Check it after any edit rather than estimating.

---

### Slide 1 — `cover.png` · "Sokhda kharif 2025 — final yield forecast"

**Kicker:** 966 plots · six Capella X-band passes · no ground truth · 893.9 t over 447.5 ha,
2.00 t/ha

**Bullets**
- One village, Sokhda, Vadodara. 966 plots, median a quarter of a hectare.
- Six Capella X-band HH passes, June to November. No labels, no leaderboard.
- The brief says an expanded set of villages; the shapefile holds one polygon.
- The brief says the crop classification is carried forward; the shapefile has no crop field.
- 17 predictions written down before the data. Nine were contradicted.

**Notes.** One village, Sokhda in Vadodara district. 966 plots, median a quarter of a hectare.
Six Capella X-band HH passes, June to November. No labels, no leaderboard. Two things the brief
says that the files do not. It says an expanded set of villages; the village shapefile holds one
polygon. It says the crop classification is carried forward; the farm shapefile has five fields
and none is a crop. So we re-derived the labels. There is nothing to fit, so validation is the
deliverable. Seventeen predictions were written down before the data that could test them was
opened, and nine were contradicted.

---

### Slide 2 — `sar_composite.png` · "What the radar actually sees"

**Kicker:** Three dates in three colour channels. No model, no classifier, no fitted number.

**Bullets**
- June red, August green, November blue — calibrated gamma-nought, nothing else done to it.
- Green: a canopy that peaked in August and was gone by November.
- Blue and magenta: still bright on the 12th — cotton and the long-duration parcels.
- Grey: roads, bunds, the village. Unchanged.

**Notes.** Before any method, this. June in red, August in green, November in blue — the same
calibrated gamma-nought, nothing else done to it. The field pattern falls out of the colour.
Green is a canopy that peaked in August and was gone by November. Blue and magenta are still
bright on the twelfth — cotton, and the twelve long-duration parcels. Grey did not change: roads,
bunds, the village. If X-band could not see this season plot by plot, it would be grey
throughout.

---

### Slide 3 — `trajectories.png` · "The stack, and the pass that fights you"

**Kicker:** T5 is right-looking, pre-dawn, and follows 63 mm of rain. Its level is never used.

**Bullets**
- Five passes look left from ~135°. T5 looks right from 318°.
- Also 01:37 IST at maximum canopy dew, three days after 63 mm of rain.
- It reported a 108 m shift. Diagnosed, not clamped: the correlation peak is flat.
- Its residual changes sign with brightness, so no constant fixes it — the level is replaced
  by the T4–T6 interpolation.

**Notes.** Five passes look left from about 135 degrees. T5, the 29th of October, looks right
from 318 — shadow and layover fall on the opposite side of every bund. It is also a 01:37 pass at
maximum canopy dew, following 63 millimetres of rain in three days. It broke the co-registration
matcher, reporting a 108 metre shift. We diagnosed instead of clamping: its correlation peak is a
third of the stack's and nearly flat, the reversed look expressed as a statistic. Its residual is
not a constant offset — it changes sign with brightness — so T5's level is replaced by the T4-T6
interpolation. Only the residual survives, as a weak covariate.

---

### Slide 4 — `canopy_sign.png` · "We pre-registered the canopy sign. We were wrong."

**Kicker:** Predicted attenuation on four of five crops. Measured +1 on all five, rho = +0.569,
n = 813.

**Bullets**
- The constant sits above the code that opens the optical file, and has not been edited since.
- Differenced on both instruments, so plot size, soil texture and row orientation cancel.
- Sign-agnostic design scored −0.085 — empty. Signed scores +0.564. The module was rebuilt.
- The arbiter existed by luck: cloud-free optical hit a Capella date twice in six.
- The same test refused the per-plot harvest date, so we deleted it.

**Notes.** Four of the five crops are darkest at what looks like peak canopy, which reads as the
canopy attenuating the surface return. We wrote that into a module constant above the code that
opens the optical file, and it has not been edited since. Sentinel-2 lands on a Capella date
twice. We difference both instruments, so plot size, soil texture and row orientation cancel. The
answer is positive on all five crops. Greener is brighter here. Our sign-agnostic design scored
minus 0.085; the signed form scores plus 0.564. It was not conservative, it was empty, and we
rebuilt the module rather than patch it. And where that arbiter came from: luck. Cloud-free
optical coincided with a Capella pass twice in six, and T5's only candidate was 79 percent cloud,
which is why the T5 control does not exist. The one thing the radar could not settle alone needed
a second instrument on the same day, and we got one by coincidence rather than design. The same
test refused the per-plot harvest date we promised, and we deleted it: three canopy observations
with a sixty-day gap cannot locate a transition.

---

### Slide 5 — `crop_type_map.png` · "Crop labels, re-derived from six dates"

**Kicker:** Tier-1 coverage fell to 26.5 % — the target was missed, and stability roughly doubled.

**Bullets**
- Two November acquisitions add the discriminator four dates could not: harvest timing.
- Cotton does not cluster, so its rule is per plot and in absolute decibels.
- 26.5 % against Round 2's 31.6 %: a missed target, recorded as missed.
- Tier 1 is 100 % stable across every clustering setting; Round 2's could halve.
- Two defects found — one by Kaggle, one by an audit of ourselves.

**Notes.** Two November acquisitions add the discriminator four dates could not: bajra off the
field by late September, maize in October, groundnut lifted October-November, cotton still
standing. Cotton does not cluster, so its rule is per plot and in absolute decibels. We aimed to
raise tier-1 coverage above Round 2's 31.6 percent. We did not: 26.5, a missed target. What
improved is stability — tier-1 is 100 percent stable across every clustering setting, where Round
2's could halve. Two defects, one found by Kaggle and one by an audit of ourselves. The ranking
axis for the allocated remainder was the November canopy clipped at zero, so 403 of 793 plots sat
at exactly zero and sort order decided the bajra-maize cut. Two machines, same code, 39 plots
different. The signed departure separates that block across 392 values. We then reported the
re-ranking confirmed by optical data. It is not. Our own audit found the test still residualising
against the axis from before the fix. Corrected, tier-2 labels carry no optical information
beyond their own axis while the tier-1 control does. Tier 2 is an allocation, which is what this
slide has called it all along.

---

### Slide 6 — `model_chain.png` · "One measured term on a sourced reference"

**Kicker:** Y_final = Y_ref(crop, 2025) × a(season-complete canopy integral)

**Bullets**
- One modulation term, not three — Round 2's health index and yield estimate were one ranking
  under two names, correlated at exactly 1.000.
- The integral is signed, not clipped: clipping put 80.6 % of bajra on its cohort median.
- The response is centred, so the cohort median lands exactly on 1.0. It redistributes; it does
  not move the cohort.
- The reference is the season's own official estimate — and it inverted our assumption.

**Notes.** One modulation term, not three. Round 2 measured its own problem: within a cohort its
health index and yield estimate correlated at exactly 1.000 — one ranking under two names. The
reference yield inverted our planning assumption. Sokhda's monsoon was 119 percent of its
thirty-year mean, so we had planned to adjust last year's yield upward. The state estimate says
the opposite: Gujarat kharif rice and bajra hit five-year lows, minus 29 and minus 26 percent, in
an excess-rain season — the Narmada overflowed inside the paddy grain-fill window. Had we applied
our elasticity, rice would have been forecast above a reference the state measured 29 percent
below. That correction came from checking a source, not modelling.

---

### Slide 7 — `yield_forecast_map.png` · "The forecast, plot by plot"

**Kicker:** 893.9 t · 447.5 ha · 2.00 t/ha · ±151 t of that is external assumption, ±9.5 t is
the radar

**Bullets**
- The shipped table is 966 rows × 21 columns and carries the whole chain, not the answer alone.
- Every uncertainty row is the entire pipeline re-run under that one change.
- The district mix is the row we can score against itself: it overstates rice and cotton, and
  that disagreement sets the perturbation.
- Somebody else's numbers set where the line falls *and* how big three of five cohorts are.

**Notes.** Groundnut 341 plots and 332 tonnes, maize 313 and 274, rice 111 and 128, bajra 139 and
87, cotton 62 and 74. The shipped table is 966 rows and 21 columns and carries the whole chain,
not the answer alone. We priced the total by re-running the chain under each source. State
reference at a stated ten percent, plus or minus 89 tonnes. The district crop mix, which
allocates three of our five cohorts, 62. Round 2's labels 7, speckle 3, tie ordering zero. The
mix is the row worth explaining, because we can score it against itself. Rice and cotton are
assigned by threshold rules, not by the mix. The district says rice is 26 percent of area and
cotton 32; we measure 17 and 10. It overstates both, and that disagreement is what we use to
perturb the three crops we cannot check. External assumptions, 151 tonnes. Everything the radar
contributes, 9.5. Somebody else's numbers decide where the line is and how big three of the five
cohorts are.

---

### Slide 8 — `extrapolation.png` · "What makes it a forecast and not a restatement"

**Kicker:** Four crops closed by observation. Cotton alone is 56 % projection, and it says so.

**Bullets**
- Round 2 discounted the unobserved season with a hand-set constant. Round 3 measures it.
- Cotton is the only crop whose season runs past 12 November — 56 % of its canopy-days, shipped
  per plot.
- Nothing in our data observes that window, so we found 16 free Sentinel-1 passes that do.
- Cotton is the only cohort still above its own June soil, and it rises nearly a decibel to 21
  December. Written down before we looked.

**Notes.** Round 2 discounted the unobserved rest of the season with a hand-set constant. Round 3
replaces the discount with measurement, because the stack now contains the harvest for four of
the five crops. Cotton is the only crop whose season runs past the 12th of November, and the only
one with a projected share: 56 percent of its canopy-days. That ships per plot. Nothing in our
data observes that window, so we went and found something that does. Sixteen free Sentinel-1
passes, feeding no feature and no label. Cotton is the only cohort still above its own June bare
soil after the 12th of November, and it rises nearly a decibel through to the 21st of December.
The flat hold is not optimistic. That was written down before we looked. The projection is flat —
last observed canopy carried forward. That is not the rule we started with, and the next slide is
why.

---

### Slide 9 — `backtest.png` · "The back-test deleted our own rule"

**Kicker:** Shipped rule vs persistence: −0.119, 95 % interval [−0.280, +0.022]. It does not beat
persistence.

**Bullets**
- Fit T1–T4, predict the withheld 12 November pass, on Round 2's labels so nothing leaks.
- Our decaying limb first scored +0.284. We quote that nowhere.
- Hand every predictor the +1.65 dB district drift and it scores −0.409. Deleted.
- The shipped flat hold: −0.119, interval containing zero; −0.216 where the rule actually fires.

**Notes.** Fit on T1 to T4, predict the withheld 12th of November pass, on Round 2's four-date
labels so no November information leaks. Our decaying projection first scored plus 0.284 against
persistence. We quote that nowhere. It predicts a higher canopy, and the scene sits 1.65 decibels
above June, so it could be winning by offsetting a drift neither predictor models. Hand every
predictor that drift and it scores minus 0.409. We deleted it. The flat hold we shipped scores
minus 0.119, interval containing zero — and minus 0.216 on the 732 plots where the rule actually
fires, which is the fairer number and the worse one. The back-test's value was not certifying the
model. It was deleting a rule that looked principled, gave a favourable headline, and did not
survive a control built to break it.

---

### Slide 10 — `reserved_optical.png` · "Two scenes nothing upstream was allowed to read"

**Kicker:** Cotton's December NDVI 0.690 vs 0.474–0.532, one-sided p = 1.26e-11.

**Bullets**
- 12 December and 16 January reserved from the first fetch; an assertion fails the run if any
  module but the validator names them.
- That is a lint, not a proof, and our own audit says so.
- A SAR-only label picked the right plots on a scene it had never seen.
- The negative control matters as much: cleared plots are under rabi, not bare.
- One more falsification — the twelve "orchard" parcels were refused by their own June scene.

**Notes.** The 12th of December and the 16th of January were reserved from the first fetch, and an
assertion greps the source tree and fails the run if any module but the validator names them. That
is a lint, not a proof, and our own audit says so. Both dates sit inside the rabi window, so what
they test is which plots still carry a kharif crop after everything else has finished — and cotton
alone is picked into January. Cotton's December NDVI is 0.690 against 0.474 to 0.532. A SAR-only
label picked the right plots on a scene it never saw. The negative control matters as much:
cleared plots are under rabi, not bare, so this is not soil quality. One more falsification. Twelve
parcels we called an orchard were confirmed in December and January — and refused in June, 0.247
against 0.397. Bare in June, so a long-duration monsoon crop. We renamed the constant and kept the
finding.

---

### Slide 11 — `zone_map.png` · "Aggregation, and what we do not claim"

**Kicker:** 46 zones, 1.50–2.80 t/ha around a village 2.00. Relabelling moves the total by 1.5 %.

**Bullets**
- One village makes the required table one row; the 500 m grid is what makes it an aggregation.
- The village row is the sum of the shipped file, rounded once before aggregating.
- Gated on the village *geometry*, not its name: 962 of 966 agree, none disagree, 100.00 % of
  parcel area inside the boundary.
- What we do not claim: a missed coverage target, a 0.77 dB median canopy, irrigation not ruled
  out, and a projection no better than persistence.

**Notes.** One village makes the required village table a single row. The 500 metre grid is what
makes the aggregation an aggregation: 46 cells of at least five farms, 946 of the 966 plots,
spreading 1.50 to 2.80 tonnes per hectare around a village figure of 2.00. The village row is the
sum of the shipped plot file, rounded once before aggregating — our own cross-check caught a
0.0015 tonne discrepancy. The roll-up is gated on the village geometry, not the village name: 962
of 966 plots agree with the attribute, none disagree, and all 447 hectares sit inside a boundary
enclosing 1174. So we report 38 percent of Sokhda — its digitised farmland, not the village. What
we do not claim. Tier-1 covers a quarter of the area, below Round 2, a missed target. Median peak
canopy is 0.77 decibels: real, corroborated, small. X-band is supposed to saturate early, and that
is the first question we expect from this room — across six NDVI bins the departure rises
monotonically, so over the range these fields occupy it does not saturate. Plot-level irrigation
could produce the same green-and-bright correlation as canopy scattering. And our projection is no
better than persistence. Thank you.

---

## Three slides worth adding — not in the built deck

Each needs a `dict` appended to `SLIDES` in `build_deck.py`, then `python build_deck.py`.
Adding all three pushes past ten minutes, so treat them as candidates, not a list.

### Candidate A — `ledger.png` · "Seventeen predictions, nine wrong"

The judge report calls this the project's most under-surfaced asset: *"the falsification ledger
is buried in `docs/research_log.md`, which no judge opens"* (blind spot 9). The figure already
exists and the deck does not use it.

**Kicker:** Written before the data that could test them. Nine contradicted, one not met, seven
held. No entry edited afterwards.

**Say:** four of the contradicted claims deleted a term, a rule or a whole module — and the
twelfth deleted a result we had already published. The ledger lives in the source as
`validate.LEDGER`, is printed by every run, and the counts are computed from the tuple rather
than typed beside it, so an eighteenth claim cannot leave the sentence stale. **This is the
slide that makes the honesty checkable rather than claimed**, and it is the strongest thing in
the submission that the current deck only alludes to.

### Candidate B — `uncertainty_budget.png` · "What the total is worth"

Slide 7 currently speaks the budget without showing it. The figure exists and is unused.

**Kicker:** External assumptions 150.9 t. Everything the radar contributes, 9.5 t.

**Say:** each row is the whole chain re-run under that one change, not a formula propagated
through it. Pre-empting "your radar term is tiny" by putting it on a slide is far stronger than
conceding it under questioning — and the null ablation is the same statement from the other
side: take the radar out and the total moves 1.8 %, while the median plot moves 11.8 %. It
redistributes; it does not set the level.

### Candidate C — an origin slide (no figure, or `canopy_departure.png`)

The panel is judging Round 3, but the credibility is in the arc. One frame:

- **Round 1** — 29 villages, acreage, a leaderboard. Found the ceiling: at pixel level X-band HH
  cannot separate structurally similar dryland crops, and the cropland *mask*, not the
  classifier, was the only lever that ever moved the score. Sentinel-1 fusion measured negative.
- **Round 2** — 966 plots, yield-to-date. Moved the unit of analysis from pixel to plot, where
  speckle averages to 0.094 dB, and the Round 1 ceiling stopped binding. Then measured two
  defects in its own output: a health index and a yield estimate that were one ranking under two
  names, and a hand-set completeness constant.
- **Round 3** — the same plots, final yield. Deleted four modules rather than adding any, and
  replaced the hand-set constant with measurement.

**One line to land it:** *"Round 3 ships fewer modules than Round 2, not more."*

---

# APPENDIX 1 — The figure-to-slide map

All 15 PNGs in `figures/`, every one written by `figures.py` from the delivered CSVs. **A figure
that re-derives its own number will eventually print a different one from the log** — that
happened twice, and both times it was caught by looking rather than by a gate, so the figures now
call the modules instead. All 15 are padded to 16:9 because Kaggle crops gallery thumbnails to
that ratio and once cut a negative-result annotation off `backtest.png`.

| figure | what it shows | the claim it carries | slide |
|---|---|---|---|
| `cover.png` | the deliverable, the physics behind it, and the check on it, in one frame | required gallery cover | **1** |
| `sar_composite.png` | three dates as R/G/B on the calibrated stack, no model | the season is visible in the raw data | **2** |
| `trajectories.png` | farm-mean gamma0 per crop across all six dates | the crops separate in time, and T5 is anomalous | **3** |
| `canopy_sign.png` | the differenced sign test, drawn from `canopy_sign` itself | the sign is +1 on all five crops — four pre-registrations wrong | **4** |
| `crop_type_map.png` | the two-tier labels over the parcels | tier 1 is measured, tier 2 is allocated, and the map says which | **5** |
| `model_chain.png` | `Y_ref` → integral → cohort-centred response → forecast, as one chain | the whole model is two terms | **6** |
| `yield_forecast_map.png` | the per-plot forecast choropleth | 893.9 t, plot by plot, with the imputed plots outlined | **7** |
| `extrapolation.png` | how much of each crop is projected rather than observed | four crops closed by observation, cotton alone at 56 % | **8** |
| `backtest.png` | fit T1–T4, predict the withheld 12 Nov pass | **the shipped rule does not beat persistence** | **9** |
| `reserved_optical.png` | the held-out December and January scenes | a SAR-only label picked the right plots on an unseen scene | **10** |
| `zone_map.png` | the 500 m grid, 46 cells | where the spatial part of the aggregation actually lives | **11** |
| **`ledger.png`** | 17 pre-registered claims and their outcomes | the honesty is checkable, not claimed | **unused — Candidate A** |
| **`uncertainty_budget.png`** | what the village total is worth, and which term owns the width | external 150.9 t vs radar 9.5 t | **unused — Candidate B** |
| **`canopy_departure.png`** | the actual model input: each plot measured against itself, drift removed | the frame everything is computed in | **unused — Candidate C, or a backup** |
| `village_summary.png` | the village aggregation, as a chart and as the table that ships | the required village rollup by crop | **unused — backup for questions** |

**Three are unused by the deck and two of them are the strongest unclaimed material**
(`ledger.png` and `uncertainty_budget.png`). `village_summary.png` is worth having open in the
back pocket: it is the literal deliverable table, and it is the fastest answer to "show me the
village rollup."

---

# APPENDIX 2 — Gaps, and what is honestly weak

## What the project does not claim

These are on the record already, in `writeup.md`, `docs/submission.md:148-157` and
`docs/validation_strategy.md`. **Say them before you are asked.** Every one of them has been
survivable so far precisely because it was volunteered.

- **No accuracy against true yield.** There is none to measure against, for anyone, in this AOI.
  The strongest single sentence in the judge report's own verdict is that *"no experiment in this
  submission tests a yield prediction against a yield observation, because none exists — and that
  is a property of the competition, not of the work."*
- **No skill claim stronger than "not worse than persistence."** The back-test is negative
  (−0.119, and −0.216 where the rule fires) and is quoted as negative.
- **Tier-2 labels — 73.5 % of area — are allocated from a district prior, not measured.** The
  shipped tables mark which is which, and the ANOVA says plainly that those labels carry no
  optical information beyond their own ranking axis (p = 0.43).
- **Plot-level irrigation is not separable from plot-level canopy** in the sign measurement.
  Only the scene-level version of that confound is ruled out.
- **One village, not the "expanded set" the Overview describes.** The village table is one row.
- **The reserved-scene guard is a lint, not an enforcement.** It greps the source tree; it does
  not prevent a determined leak. The docs now say so rather than describing it as enforcement.
- **T5 remains the weakest registration** in the stack (1.48 m, weakest correlation peak).
- **Median peak canopy is 0.77 dB** — real, corroborated and small, against a 0.094 dB farm-mean
  speckle floor.
- **`Y_ref` is a state figure with no district correction**, because no district 2025-26 estimate
  is published. Vadodara ranks 1st in Gujarat for maize yield and 2nd for cotton, so those two
  are conservative by a **known sign** — stated rather than corrected for.
- **Part of Moran's positive I is the imputation.** The back-test scores only the 813 measured
  plots; Moran's I runs on all 966, so some of the spatial autocorrelation is imputation putting
  neighbours' values onto neighbours.
- **The season integral's *form* was chosen by scoring against 13 Oct and 12 Nov optical**, so
  those two scenes cannot also validate it. That is what the reserved December and January scenes
  exist for, and the leakage document was wrong about this until 2026-08-31.

## Two things still open in the judge report

From `docs/judge_report.md:668-671`, listed as not closed:

- **§4.5 — the back-test's information asymmetry between B1 and B4 is still there.** The write-up
  and deck now quote the fairer, worse −0.216 alongside the −0.119 headline, which is a partial
  answer, not a full one.
- **§10 — `gates.py` duplicates its G1 threshold as a bare literal; 12 dead columns; no test
  coverage of `gates`, `s2_ndvi` or `farm_features`.** None of these affects a reported number,
  which is why they are open.

## Documentation drift found while writing this brief

None of these changes a result. All of them are findable by a judge in under a minute, and the
first one is the one that matters.

| where | says | actually |
|---|---|---|
| ~~`writeup.md`, `build_deck.py`, `validate.py`, `validation_strategy.md`, `research_log.md`, `checkin.html`~~ | cotton's December NDVI was quoted as *"0.690 against **0.499–0.532**"* (or 0.495–0.532) | **FIXED 2026-09-03.** The shipped run prints the other four cohorts at **Bajra 0.474**, Rice 0.502, Maize 0.505, Groundnut 0.532, so the floor is **0.474**. Corrected at every live site, `ledger.png` and the notebook regenerated, the deck and the check-in PDF rebuilt. `docs/judge_report.md:147` is left as written (audit snapshots are not rewritten) with a §23 status row added, and `AGENTS.md` §S9 carries a correction note beneath the original line. See below for how it survived. |
| **`AGENTS.md:13`** (the preface, the first thing a reader sees) | *"Eight of thirteen pre-registered claims were contradicted"* | **9 of 17 contradicted, 1 not met, 7 held.** A mid-project count from before S32 and S33 added claims 14–17. It contradicts `README.md`, `docs/research_log.md`, `figures/ledger.png` and the shipped log — all four of which are right. |
| `README.md:84` | `AGENTS.md` is "S0-S33" | the log runs to **S36** |
| `README.md:65, 77, 78` | "50 tests" | `pytest` collects **53** |
| `docs/submission.md:104, 126` | "37 tests, all passing" | same — **53** |
| `docs/model_architecture.md:4` | `Y_final = Y_ref(crop, 2025-26) · a(...)` | agrees with the code; `writeup.md:79` writes it as `Y_ref(crop, 2025)`. Cosmetic, but the two forms appear on different pages of the same submission |
| `CLAUDE.md` | lists CHIRPS among the external sources | `grep` finds no CHIRPS reference anywhere in `src/`. It is not used, and listing it invites a question with no answer |
| `Round 3/AGENTS.md` | — | the **Midnight Check-in PDF** built 2026-09-02 (`checkin/Midnight_Checkin_Sokhda.pdf`, 2 pages) had no log entry, which breaks the repo's own rule that every stage ends with a measurement recorded in the log. Fixed in §S37. |

**The December-NDVI floor was the most consequential of these, because of *how* it got there.**
`logs/writeup_trace.txt:36` traces the write-up's `0.499` to this line:

```
0.499  B2 cohort mean at T4   813   1.229   1.589  -0.694   -0.310  [-0.499 -0.141]
```

That is a back-test confidence interval. The tracer matched a substring and passed it. **This is
exactly the defect class §S18 was built to catch** — a number in the write-up that no run ever
printed, waved through by a coincidental match — and it is still live in six places, including
the pre-registered ledger string in `validate.py:183`. The likely origin is benign: cohort
membership moved when 185 tier-2 labels were re-ranked in §S15, which changed bajra's December
mean from 0.495 to 0.474, and the prose was never re-derived. **The claim itself is unaffected**
— cotton at 0.690 is still the highest by a wide margin and the p-value is unchanged — but the
floor quoted beside it is not a number this run prints.

**Fixed 2026-09-03.** The ledger entry's fourth field is the *outcome* — what the measurement
said — not the pre-registered claim in field three, so correcting it is a bug fix rather than a
rewrite of a prediction, and the claim string was not touched. `figures/ledger.png` was rebuilt
from `validate.LEDGER`, `sokhda_yield_forecast.ipynb` regenerated from `src/`, and both
`Sokhda_Goa_Finals.pptx` and the check-in PDF re-rendered. Two files were deliberately **not**
edited: `docs/judge_report.md`, because §23 says the audit is not rewritten as findings close —
it gets a status row instead — and the §S9 entry in `AGENTS.md`, which keeps its original line
with a correction recorded beneath it.

**The `AGENTS.md:13` line is worth fixing before the finale.** It sits in the preface of the file
whose entire purpose is to let a judge check whether the discipline is real, and it is the one
number in that file that disagrees with the run.

## The strongest attack, and the honest adjudication

`docs/judge_report.md:487-520` states it as forcefully as a panellist would, and then adjudicates
it. Worth reading in full before the finale. Compressed:

> *"You have built an elaborate validation apparatus around a measurement the literature says
> cannot carry the information you need. X-band interacts with the topmost leaves and saturates
> early. Your median peak canopy is 0.77 dB. Your model's only per-plot term is the season
> integral of that quantity, and its functional form was selected by maximising its correlation
> against the optical scenes you then cite as validating it. Strip that away and what remains is
> a state-level average redistributed by noise — which your own uncertainty budget concedes when
> it prices every radar term at 9.5 t against 89.4 t for the reference."*

**Valid:** the saturation literature is real, the circular selection of the integral's form is
confirmed, and 0.77 dB against a 0.094 dB speckle floor is a real but small signal.

**Not valid:** the criticism assumes the project claims to *retrieve* biomass from X-band. It
does not — it claims to **rank plots within a cohort** around an externally supplied level.
Saturation degrades a ranking far less than a retrieval, and the ranking has independent support
the critic ignores: a SAR-only cotton label predicted the right plots on a December scene it had
never seen, at p = 1.26e-11, and the same cohort separates again on a different sensor.

**And the 9.5-vs-89.4 line is not a concession extracted under questioning — it is the
submission's own headline.** Saying it first is the difference between an admission and a
finding.
