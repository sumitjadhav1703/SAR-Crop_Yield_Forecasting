# PROJECT JUDGE REPORT

**Adversarial audit of the ANRF AISEHack 2.0 Round 3 submission.** Produced 2026-08-31,
against `logs/pipeline_clean.log` (678 lines, EXIT 0) and the tree as of that date. Deadline
2026-09-03 07:00 UTC — **roughly three days.**

**How this was produced, and its limits.** Three independent read-only auditors covered
statistical rigour, leakage/circularity, and reproducibility. A planned adversarial refutation
pass did **not** run (the workflow died on a session limit), so findings were verified by hand
instead of by independent skeptics. Every CRITICAL and HIGH below carries a `file:line` or log
line that was personally re-checked; anything not re-checked is marked. That is weaker than the
intended design and this report says so rather than implying a verification that did not happen.

External sources cited here were retrieved in-session and are listed in §21. No citation in
this report is invented.

---

## 1. Executive Verdict

The engineering is genuinely strong and the internal consistency is real: the notebook is
byte-in-sync with `src/`, the shipped CSVs reproduce the write-up's headline exactly, there is
one `try/except` in 16 modules, and the pipeline has now reproduced across two platforms. That
is better discipline than most competition submissions ever reach. The problem is not the code.

The problem is that **the project's central claim — that its validation is independent — is
contradicted by its own source files in at least three places.** `docs/leakage_analysis.md`
lists the season integral and `COTTON_NOV_DB` under "what optical did NOT touch, and can
therefore test it"; `phenology.py:64-81` and `crop_type.py:234-237` both say the opposite. A
judge who reads the leakage document and then the modules finds the submission contradicting
itself on precisely the axis it claims as its strength. Separately, the ANOVA that scores the
project's own pre-registered prediction residualises against a variable that stopped being the
ranking axis in §S15, so the "CONFIRMED" verdict printed in the write-up, the deck, `AGENTS.md`
and `docs/research_log.md` is not measuring what its own output line says.

Biggest opportunity: these are **text and one-line code fixes**, not method failures. The
underlying work survives correction; what does not survive is the current wording. Largest
competition risk: an expert panel spot-checks one leakage claim, finds it false, and discounts
every other validation claim in a submission whose whole pitch is validation discipline.

Is the approach strong enough? For a finalist placing, yes. For winning, the honesty framing
has to be *accurate* as well as brave, and right now it is brave but locally inaccurate.

---

## 2. Competition Scorecard — `INTERNAL ESTIMATE`

Official rubric weights; scores are mine and no panel has seen this work.

| Category | Max | Score | Basis | Biggest deduction |
|---|---:|---:|---|---|
| Technical Soundness | 25 | **20** | Full physical calibration chain, RPC geocoding validated by a look-direction sign flip, three blocking gates, held-out radiometric scoring. | The one per-plot term is X-band HH at a 0.77 dB median, a band the literature says saturates early (§15). `ACCUM_SPAN = 0.30` is unswept. |
| Creativity | 15 | **12** | Pre-registration ledger, reserved scenes, leave-future-out back-test, uncertainty budget by chain re-run. Genuinely unusual for a hackathon. | The *model* is deliberately minimal; a panel scoring "novel modelling approach" may not credit validation architecture as creativity. |
| Plausibility & Defensibility | 25 | **17** | Sourced `Y_ref`, centred cohort factor, per-crop bands, four-source uncertainty budget, degeneracy controls. | **The leakage document contradicts the modules (§3.1, §3.3).** Moran's `p = 0.005` is a resolution floor quoted as a measurement (§4.1). |
| Aggregation | 15 | **14** | Village row is the exact sum; rounding-order defect found and fixed; 46-zone grid; roll-up now gated on the village polygon with 100.00 % containment. | Three of five cohort areas are set by a district prior, and that prior is not a row in the uncertainty budget. |
| Documentation & Presentation | 20 | **15** | 2000-word write-up with every number traced, 9 docs, 14 figures, generated notebook, 11-slide deck. | No `README`, no dependency manifest, no data-acquisition instructions. Dev scratch (`AGENTS.md`, 3 logs, `NEXT_SESSION.md`) ships to judges. |
| **Total** | **100** | **78** | | |

A corrected version of this submission — same method, accurate claims — plausibly scores 86-88.
The gap is almost entirely wording and packaging.

---

## 3. Critical Findings

### 3.1 The leakage document states the season integral was untouched by optical; the code says its form was chosen by scoring against optical

**Problem.** `docs/leakage_analysis.md:22` lists, under **"What optical did NOT touch, and can
therefore test it"**: *"the season integral, the accumulation response, and the forecast
itself."*

**Evidence.** `src/phenology.py:68-72`, verbatim:

> *"the season INTEGRAL uses the signed departure… Scored against optical the signed form
> reaches rho=+0.564 against +0.472 for the clipped-positive form, and it is the better of the
> two on four of the five crops (bajra 0.417 vs 0.376, maize 0.526 vs 0.451, rice 0.780 vs
> 0.704, groundnut equal; only cotton prefers clipping, 0.275 vs 0.312)."*

The functional form of the **only** per-plot term in the forecast was selected by comparing
candidate forms against the optical reference. `canopy_sign.report()` then prints that same
correlation (log lines 198-199) as evidence supporting the choice.

**Why it matters.** This is selection on the validation set, and the project's own leakage
document denies it. The `+0.564` figure is quoted in `writeup.md` as the term's independent
external support.

**Potential consequence.** A judge who reads `leakage_analysis.md` and then `phenology.py`
concludes the leakage analysis is unreliable. Every other independence claim in the submission
is then discounted, including the ones that are sound.

**Recommended action.** Correct `docs/leakage_analysis.md` — move the season integral out of the
"untouched" list and state plainly that its form was selected against T4/T6 NDVI, which is why
the reserved December/January scenes exist. The write-up already discloses the three numbers
(−0.085 / +0.472 / +0.564); it needs one clause saying the choice was *made* on them. This is a
documentation fix, not a method change, and it converts a discoverable contradiction into
another recorded finding — the pattern the project already uses well.

### 3.2 The ANOVA scoring the project's own pre-registered prediction residualises against the wrong variable

**Problem.** `s2_ndvi.label_information_test` removes `g0_db_filled_T4` before testing whether
tier-2 labels carry information "beyond the axis that assigned them". The axis that assigns them
is `departure_T6`.

**Evidence.**
- `src/s2_ndvi.py:413-414` — `def label_information_test(df, mask, groups, axis: str = "g0_db_filled_T4", target: str = "ndvi_T4")`
- `src/s2_ndvi.py:572` — the only call site: `label_information_test(df, ok, groups)` — **no `axis` argument**, so the default is used.
- `src/crop_type.py:264` — `TIER2_AXIS = "departure_T6"` (changed in §S15).
- `src/s2_ndvi.py:417` — docstring still says *"Tier-2 labels are cut from a ranking on `g0_db_filled_T4`"* — stale by one revision.
- `logs/pipeline_clean.log:364` prints *"residualised against gamma0 T4, the tier-2 ranking axis"*.

**Why it matters.** `crop_type.TIER2_PREREGISTERED` registers prediction 1 as *"the tier-2
cohorts separate better on optical NDVI residualised against the ranking axis"*. The shipped run
reports it CONFIRMED (η²_resid 0.0274 → 0.03017, F 11.387, p 1.35e-05), and that verdict appears
in `writeup.md`, the deck, `AGENTS.md` §S15, and `docs/research_log.md` claim 12.

**Precision matters here, and the finding is narrower than it first looks.** The 0.0274 baseline
and the 0.0302 result come from the *same* mis-specified test applied to two label sets, so the
**comparison** is internally valid — the new labels really do separate better on this statistic.
What is not valid is the **interpretation**: the test does not residualise against the ranking
axis, so it cannot establish that the labels carry information *beyond* that axis. Because tier-2
labels are a monotone quantile partition of `departure_T6`, which survives the residualisation
untouched, between-group variance is partly guaranteed by construction.

**Potential consequence.** A reviewer who opens `s2_ndvi.py:413` sees the default argument
immediately. The claim is then not merely unsupported but visibly mis-specified, in the one test
the project nominated in advance.

**Recommended action.** Either pass `axis=crop_type.TIER2_AXIS` at the call site and re-run —
which may weaken or kill the result, and that outcome should be recorded either way as the
project records everything else — or, if there is no time to re-run, restate the claim in the
write-up as the narrower thing the test actually shows and log the defect. Do **not** leave the
current wording standing.

### 3.3 `COTTON_NOV_DB` is listed as optical-untouched; `crop_type.py` discloses that it is not

**Problem.** `docs/leakage_analysis.md:21` lists `COTTON_NOV_DB = 1.5` under "what optical did
NOT touch".

**Evidence.** `src/crop_type.py:234-237` states the opposite in the project's own words:
*"Disclosure … the optical banding above was inspected before this constant was fixed. The
optical agreement at 1.5 dB specifically is therefore corroboration, not an independent test of
that value."*

**Why it matters.** Cotton assigned by this constant is the subject of the **only** pre-registered
reserved-scene hypothesis (`validate.py:102-105`), and `validate.py:104-105` describes the label
as *"came from SAR at 12 November with no optical input at all."* The strongest clean result in
the submission — cotton's December NDVI 0.690 vs 0.499-0.532, p = 1.26e-11 — rests on a label
whose threshold was set after looking at optical banding.

**Potential consequence.** The reserved-scene test is the submission's best evidence. If its
subject's threshold was optically informed, the test is corroboration rather than prediction, and
the write-up currently sells it as prediction.

**Recommended action.** `crop_type.py` already has the honest sentence. Propagate it: fix
`leakage_analysis.md:21`, fix `validate.py:104-105`, and add one clause to the write-up's
reserved-optical paragraph. The result stays impressive — a threshold informed by *banding* is
not the same as a threshold fitted to December NDVI, and the December scene was still never seen.
Say exactly that.

---

## 4. High-Priority Findings

### 4.1 Moran's I `p = 0.005` is the floor of a 199-permutation null, reported as a measurement

**Evidence.** `src/validate.py:288-294`, verified verbatim:
```python
def _i_with_p(v, n_perm=199):
    obs = morans_i(v, xy)
    good = np.isfinite(v)
    null = np.array([morans_i(rng.permutation(v[good]), xy[good]) for _ in range(n_perm)])
    return obs, float(null.mean()), (1.0 + np.sum(null >= obs)) / (n_perm + 1.0)
```
With `n_perm = 199` and the add-one estimator, p ∈ {1/200, 2/200, …} so the **minimum
attainable p is exactly 0.005**. All three reported values are `p=0.005` (log 568-570), i.e.
zero null exceedances in every case. The supported statement is **p < 0.005**;
`writeup.md` states *"a within-crop residual of +0.151, p = 0.005"*.

**Why it matters.** Any statistician on the panel recognises 1/(n_perm+1) on sight. It reads as
either not understanding the estimator or reporting a floor as a result — in a submission whose
pitch is statistical care. It is also the cheapest possible fix.

**Recommended action.** Change the reported form to `p < 0.005`, or raise `n_perm` to 999 and
report the real value. The second is better and costs one line plus a re-run.

### 4.2 The submission cannot be reproduced on a clean machine

**Evidence.** No `requirements.txt`, `environment.yml`, `pyproject.toml`, `Pipfile` or lockfile
exists — verified by direct `ls`. No `README`. `.venv/pyvenv.cfg` sets
`include-system-site-packages = true`, so numpy, pandas, scipy, scikit-learn, GDAL and pytest all
resolve to the author's global environment, not to the shipped venv. `src/geocode.py:130` executes
`DATA_DIR = _data_dir()` at **import** time and the competition data lives at
`Hackathon/Data/` — one level *above* the repo. `src/farm_features.py:55-56` resolves the
shapefiles at import too. Consequence: `import geocode` fails on a clean machine, which takes 12
of 16 modules and the entire test suite with it.

**Why it matters.** Rubric line "Documentation & Presentation" and the winner's obligation to
supply *"a link to a reproducible code repository"*. The Kaggle notebook does run — but the
repository, which is what a winner must deliver, does not.

**Recommended action.** A `requirements.txt` with pinned versions and a 20-line `README` naming
the data path and `SAR_DATA_DIR`. Under an hour, and it moves a rubric category.

### 4.3 The "runs offline from the shipped cache" claim is false

**Evidence.** `src/s2_ndvi.py:359` calls `search(window)` unconditionally inside the window loop;
the cache check is downstream at `s2_ndvi.py:206`, inside `fetch_native`. With internet disabled
the first iteration raises. The claim appears in three places: `src/pipeline.py:30-31`,
`src/s2_ndvi.py:201-203`, `docs/submission.md:134-135`.

**Recommended action.** Either cache the STAC response or delete the claim from all three. The
honest offline path, `--no-s2`, already exists and is described accurately.

### 4.4 `round2_crops.csv` is not at any path the resolver probes, while an unreferenced copy ships in the repo

**Evidence.** `geocode.round2_crops_path()` probes `ROUND2_CROPS`, the sibling `Round 2/`, six
`/kaggle/input/` globs, and `work/round2_crops.csv`. `grep -n "kaggle_dataset" src/*.py` returns
**nothing** — yet `Round 3/kaggle_dataset/round2_crops.csv` exists with exactly the right three
columns. The resolver walks past the file sitting in the repo.

**Why it matters.** Without it the run aborts at CANOPY SIGN, before the forecast. A judge who
downloads the repo and follows `docs/submission.md` hits this.

**Recommended action.** Add `kaggle_dataset/round2_crops.csv` to the candidate list. Two lines.

### 4.5 The back-test's headline comparison is not information-fair

**Evidence.** `src/backtest.py:66-91`. B1 persistence uses `d4` only. B4, the shipped rule, uses
`d4` **plus** the crop label, **plus** the `HARVEST_DOY` agronomic calendar, **plus** a
non-negativity clip. Because `HARVEST_DOY ≤ 316` for bajra, maize, groundnut and rice, B4
collapses to a constant 0 for four of five crops — so much of the measured skill is "knowing
which crops are already harvested", not the projection rule the module says is under test.

**Nuance the project already has.** `shipped_configuration` (`backtest.py:208-234`) restricts to
where the rule actually fires and reports skill −0.216 on n=732, which is the fairer number and
is *worse*. The write-up quotes the headline −0.119, not this.

**Recommended action.** Quote the rule-fires number alongside the headline. It strengthens the
project's honesty position rather than weakening it, and pre-empts the question.

### 4.6 `ACCUM_SPAN = 0.30` — the largest single lever on every reported yield — has no sensitivity sweep

**Evidence.** `src/yield_forecast.py:86`, with a documented *justification* at lines 77-85
("wider than Round 2's 0.20 because this is now the ONLY per-plot term") but no derivation and no
sweep. It sets the entire per-plot spread: cohort p05 → 1−0.30, p95 → 1+0.30, and therefore the
1.50-2.80 t/ha zone range and every p10/p90 in `outputs/village_summary.csv`.
`COTTON_NOV_DB` and `MIN_CANOPY_DB` both ship sweeps; this one does not.

**Why it matters.** The write-up criticises Round 2 for a *"hand-set 0.45"*. An `ACCUM_SPAN` with
no sweep is open to exactly that charge, and the panel can make it in one sentence.

**Recommended action.** Run the sweep (0.15 / 0.30 / 0.45) and print it, the way
`cotton_sensitivity` is printed. Half a day including the re-run. This is the highest-value
*technical* item on the list.

### 4.7 The tier-1 positive control failed

**Evidence.** `src/s2_ndvi.py:428-429` docstring: *"Tier 1 is the positive control -- it must
pass, or the test itself is not sensitive enough to trust when tier 2 fails."* Shipped run
(log 367): tier 1 `F 0.015, p 9.03e-01`.

**Stated fairly, because the auditor overstated this.** The docstring's condition is scoped to
*"when tier 2 fails"* — and tier 2 passed. A test that were simply insensitive could not have
produced tier 2's p = 1.35e-05. So this is not a fatal invalidation. It is still an unexplained
result printed without comment: tier-1 labels (Rice, Cotton), the ones the project is most
confident in, carry *no* NDVI information beyond the axis, with lower raw η² (0.0071) than tier 2
(0.0335). That is odd and a judge may well ask.

**Recommended action.** One sentence in the log or the docs acknowledging the control's outcome
and why it does not invalidate tier 2. Do not leave it printed and unremarked.

---

## 5. ML / Data Science Audit

There is no trained model, no fitted parameters, and no train/test split — by design, because
there is no label. That removes whole categories of risk (overfitting, target leakage, weak
baselines in the usual sense) and concentrates all the risk in **constant selection**, which is
where the findings above land.

Data quality is disclosed: 813 measured / 82 interpolated / 71 imputed (log 116). But **16 % of
plots carry partly synthetic features** and the write-up does not say so. `outputs/farm_forecast.csv`
does carry `data_quality` per plot, so a judge *can* tell — the disclosure exists in the artefact
and not in the prose.

The imputation interacts with a headline statistic: `validate.report` runs Moran's I on all 966
plots with no `data_quality` filter (`validate.py:285`), and `farm_features.py:310-312` fills
imputed plots with the median of their 8 nearest neighbours. Roughly 16 % of the values entering a
spatial-autocorrelation test are literal spatial smooths of their neighbours. Positive I is
therefore **partly manufactured**. The permutation null does not model this. `NOT INDEPENDENTLY
RE-VERIFIED` beyond reading the cited lines, but the mechanism is plain.

---

## 6. Validation & Leakage Audit

The submission's genuinely clean validation surfaces, after everything above:

1. **The reserved December / January scenes** (`validate.py:213-228`) — subject to §3.3.
2. **The look-direction control** (`validate.py:159-173`) — uses parcel geometry no optical scene
   touched. Clean.
3. **Moran's I** — tests spatial structure, not correctness, and is affected by §5.

Everything routed through `ndvi_T4` / `ndvi_T6` is **diagnostic, not held out**. `s2_ndvi.py:488-491`
says exactly that for T4. Nothing says it for T6, and T6 is dual-use too: it sets `CANOPY_SIGN`
via the differenced test *and* scores `observed_integral`, `cleared_fraction` and `t5_anomaly` in
`canopy_sign.py:198-223`.

**The reserved-date guard is weaker than "enforced".** `validate.assert_reserved_unread`
(`validate.py:176-196`) is a regex over `src/*.py` source text for `ndvi_R1|ndvi_R2`. It does not
catch: f-string column access (`df[f"ndvi_{RESERVED[0]}"]` — which `validate.py` itself uses),
the unprotected `ndvi_cov_R1` / `ndvi_date_R1` / `ndvi_scene_R1` columns, whole-frame reads
(`canopy_sign.load()` returns a frame physically containing the reserved columns), or
`work/farm_joined.csv`. It runs at step 12 of 14, *after* every upstream module has executed, and
is skipped entirely under `--no-s2`. `docs/leakage_analysis.md:24-27` calls this *"enforced, not
promised"*. It is a useful lint, not an enforcement.

**Round 2's T1-T4 claim: VERIFIED.** `Round 2/farm_crops.csv` contains `cov_frac_T1..T4` and
`g0_db_filled_T1..T4` and **no T5 or T6 column**; `Round 2/farm_ndvi.csv` has no November scene.
The claim at `backtest.py:173` is confirmed for T6. It does **not** make those labels
optical-independent — Round 2's axis was shaped by `ndvi_T4` — so `canopy_sign.py:136-140`, which
strata by Round 2 labels and scores against T4/T6 NDVI, remains partly circular.

**Two smaller routes, both confirmed by reading the cited lines:** back-test inclusion requires
`data_quality == "measured"`, which requires all six dates including T6 (`farm_features.py:284-287`)
— a filter conditioned on the withheld date; and `DRIFT_T6_DB = 1.65` (`backtest.py:57-60`) is
measured on T6 and handed to every predictor in the control variant that decided the shipped rule.
Both are disclosed in the code and neither is large, but `docs/leakage_analysis.md:45-47`'s
"no T6 information reaches a predictor" is not strictly true.

---

## 7. Model & Experiment Audit

**What the experiments prove:**
- The geocoding height is terrain, not a fitting artefact (the right-looking scene reverses sign — a genuinely elegant control).
- T6 carries a scene-wide radiometric offset and T5 does not (flat vs sign-changing across brightness deciles).
- Greener is brighter on all five crops in this stack, differenced, n=813.
- Tier-1 labels are stable across clustering settings; tier-2 labels are not the arbitrary sort order they were before §S15.
- Cotton labels predict December greenness on a scene never read.
- The forecast has spatial structure beyond the crop label.

**What they do not prove:**
- **Anything about yield.** No experiment in this submission tests a yield prediction against a yield observation, because none exists. The back-test target is *backscatter*, not yield.
- That the season integral measures canopy rather than surface moisture or roughness (§15).
- That the tier-2 crop *names* are right — only that the cohorts differ on NDVI.
- That the shipped projection rule beats persistence. It does not: −0.119 [−0.280, +0.022], and −0.216 where the rule actually fires.

**Missing ablation that a reviewer will ask for:** a null model where `a() ≡ 1`, i.e. every plot
receives its cohort's `Y_ref` unmodified. That single number would quantify what the radar
contributes to the plot-level answer. It is a one-line experiment and its absence is conspicuous
given the uncertainty budget already implies the answer (radar terms sum to 9.5 t against 89.4 t).

---

## 8. Data & External Data Audit

**Rules compliance: no violation found.** External sources are Sentinel-2 L2A via Earth Search,
NASA POWER, and DA&FW published estimates — all free and equally available, as
Section 2.6 requires. The Round 2 labels shipped as a Kaggle dataset are this team's own model
output (`farm_id`, `crop_type`, `crop_confidence`), not competition data.

**The district crop mix is the largest un-priced assumption.** `crop_type.py:412` uses
`CROP_MIX_REFERENCE` as the `weights` for tier-2 allocation, which sets the areas of Bajra, Maize
and Groundnut — 793 of 966 plots, ~326 of 447 ha. The uncertainty budget has four rows
(`Y_ref`, label swap, speckle, tie ordering) and **the district mix is not one of them.** The log
is honest that agreement is "by construction", but the budget presents itself as pricing the
village total and omits the prior that sets three of five cohort areas.

`crop_type.py:193-194` says the mix is *"used ONLY to report against the result -- never as an
input"*, contradicted by line 412. A stale comment rather than a hidden practice — `docs/submission.md`
discloses the allocation — but a reader who greps the constant gets the wrong answer.

**Reproducibility of external data is weak.** Cache keys are `s2_{date}_{band}.tif` — date only, no
scene ID, no checksum. `ndvi_scene_*` is written (`s2_ndvi.py:402`) and never read by anything.
If ESA reprocesses a scene, a judge with the cache and a judge without it silently get different
numbers. And the R2 reserved date is chosen from **three candidates all at 0.0 % cloud**
(log 142-147) by stable-sort order, i.e. by whatever order Earth Search returned them — a
different reserved scene could win on a future run.

---

## 9. Reproducibility Audit

Covered in §4.2 and §4.3. Summary of what a judge on a clean machine hits, in order:

1. No `README`, no dependency manifest, no data-acquisition instructions.
2. `import geocode` fails — data is outside the repo and resolved at import.
3. If data is placed correctly: `import` succeeds, `pytest` fails (pytest is not in the venv).
4. If dependencies are installed: the run aborts at CANOPY SIGN — `round2_crops.csv` is not at a probed path.
5. If `ROUND2_CROPS` is set by hand: the run needs internet, contrary to the offline claim.

`MISSING EVIDENCE`: no library versions recorded in the shipped log (the notebook prints GDAL's
version at runtime but that line is absent from `pipeline_clean.log`, so the log cannot be
attributed to an environment); no git history (the tree is not a repository); no golden-output
regression test pinning 893.9 t.

---

## 10. Code & Architecture Audit

Strong, and this should be said plainly because the findings above are all negative. **One
`try/except` in 16 modules** (`pipeline.py:66-71`, `/proc` on macOS, affecting a log banner only).
Everything else raises. 45 real assertions, several of which are anti-staleness guards on the
source text itself. Zero uncalled functions across the tree — the four deleted modules were
actually deleted.

Defects worth fixing:
- `gates.py:110,112` — the G1 threshold `0.95` is an unnamed literal duplicated twice, in a **blocking** gate, while its three sibling thresholds are named constants.
- `np.trapezoid` has a numpy-2.0 fallback at four sites but is called unguarded at `canopy_sign.py:149` — the fallback protects nothing.
- `yield_forecast.py:300` uses `include_groups=False`, pinning pandas to [2.2, 3.0).
- `farm_features.py:260-261` and `phenology.py:190` use `offsets.get(code, 0.0)`, which reintroduces exactly the silent zero `scene_diagnostics.py:352-355` promises is impossible — the guarantee holds at file granularity and fails at key granularity.
- 12 per-farm feature columns computed every run and never read (`farm_features.py:372-394`).
- Zero test coverage of `gates.py` (blocking), `s2_ndvi.py` (network), `farm_features.py`, `figures.py`.
- `docs/submission.md:127` claims 37 tests; 45 collect.

---

## 11. Innovation Audit

**Strongest genuinely innovative aspect: the pre-registration ledger.** Thirteen claims written
before the data that could test them, seven contradicted, and the model changed to match rather
than the text edited. `EXPECTED_SIGN` is still in the source, still wrong, still uncorrected. That
is rare in a hackathon and hard for a competitor to fake retroactively.

**Weakest innovation claim: the multitemporal RGB composite.** It is a well-known visualisation,
not a contribution. Present it as communication, never as method.

**Second-weakest: "one modulation term, not three."** Simplification justified by a measurement is
good engineering, but a panel scoring *Creativity* may read a one-term model as an absence of
modelling rather than a decision.

**Three realistic ways to increase meaningful innovation, in the time available:**
1. **Price the district-mix prior** and add it to the uncertainty budget (§8). Nobody else will have decomposed a no-ground-truth forecast into assumption-vs-measurement this way.
2. **Publish the falsification ledger as an artefact** — the 13 claims and their outcomes as a table in the write-up or as a figure. The discipline exists; it is currently buried in `docs/research_log.md`.
3. **State the X-band saturation limit and test it** (§15, §17). Turning the strongest attack into a measured result is worth more than any new feature.

---

## 12. Documentation Audit

Nine `docs/*.md`, a 2000-word write-up with a numeric audit, and a generated notebook that is
verifiably in sync. This is above the bar. Three problems:

1. **`leakage_analysis.md` contains two false claims** (§3.1, §3.3). The most load-bearing document is the least accurate one.
2. **No `README`, no install instructions, no data-acquisition step.** `docs/submission.md:122-129` gives two commands and no way to obtain the data.
3. **Development scratch ships to judges**: `AGENTS.md` (98 KB), `NEXT_SESSION.md`, and three pipeline logs with no marker saying which is current. `AGENTS.md` is genuinely impressive evidence of process — but it is 98 KB and a judge will not read it. It needs a two-paragraph preface saying what it is, or it reads as clutter.

---

## 13. Presentation / Demo Audit

The deck is 11 slides, 1552 words of notes, 10.3 min against a 10-minute slot — over, and the
overrun is in the notes rather than the slides.

**The three hardest questions a GalaxEye / IIT-Madras panellist will ask, and whether the material answers them:**

1. *"X-band saturates early with biomass. What is your 0.77 dB actually measuring?"* — **Not answered anywhere.** See §15.
2. *"Your back-test says your rule doesn't beat persistence. Why should I believe the forecast?"* — Partly answered. The answer is that the forecast's level comes from `Y_ref` and the radar only ranks within cohorts, but the deck does not connect these two slides explicitly.
3. *"Three of your five crop areas come from a district prior. What happens if the prior is wrong?"* — **Not answered.** No number exists.

**On foregrounding failure.** The write-up leads with "the four predictions the data contradicted"
and heads the back-test "the headline, and it is negative". Both sides of this are real: a
scientific panel rewards it, and a panel scoring *Technical Soundness* out of 25 may simply read
"negative result" as "weak model". **My judgement: keep it, but re-order.** Lead with what the
method *establishes* — 100.00 % containment, the terrain-height sign flip, the cotton December
prediction at p = 1.26e-11 — then present the contradicted predictions as the reason to trust
those results. Same content, same honesty; the failures land as rigour rather than as apology.

---

## 14. Blind-Spot Analysis — the 10 most important

1. **The leakage document is the least accurate document in the project.** Effort went into the analysis; nothing re-checked it against the modules after §S15 moved the axis.
2. **`p = 0.005` three times is a resolution floor.** Reported as a measurement in the write-up.
3. **A default argument silently invalidated a pre-registered test.** Changing `TIER2_AXIS` in one module did not update the test that scores it in another. Nothing detects that class of drift; the tests check source text elsewhere but not this.
4. **The district crop mix sets three of five cohort areas and is not in the uncertainty budget** — which is otherwise the most sophisticated thing in the submission.
5. **16 % of plots have partly synthetic features and feed a spatial-autocorrelation test**, which partly manufactures the positive Moran's I.
6. **The repository is not reproducible even though the notebook is.** The winner's obligation is a reproducible repository, not a notebook.
7. **X-band saturation** — the single strongest external attack, unaddressed. §15.
8. **`ACCUM_SPAN` is the exact thing the write-up criticises Round 2 for**, and a judge can make that point in one sentence.
9. **`AGENTS.md` at 98 KB is evidence nobody will read.** Its best content — the falsification ledger — should be surfaced where a judge actually looks.
10. **The reserved-scene guard is a lint, not an enforcement**, and is described in the docs as enforcement.

---

## 15. Strongest Counterargument

**Stated as forcefully as a panellist would state it:**

> *"You have built an elaborate validation apparatus around a measurement that the literature
> says cannot carry the information you need. X-band at 3 cm interacts with the topmost leaves
> and does not penetrate the canopy; crop-parameter retrieval from X-band backscatter has been
> reported as very low because the signal saturates early, and in rice the backscatter peaks near
> 60 cm plant height — well before the ~100 cm maximum — so the response is not even monotone
> with growth. Your own median peak canopy is 0.77 dB. Your model's only per-plot term is the
> season integral of that quantity, and its functional form was selected by maximising its
> correlation against the optical scenes you then cite as validating it. Strip that away and what
> remains is a state-level average redistributed by noise — which your own uncertainty budget
> concedes when it prices every radar term at 9.5 t against 89.4 t for the reference."*

**Adjudication: partly valid, and the valid part is serious.**

*Valid:* the saturation and non-monotonicity literature is real and the submission never addresses
it. The circular selection of the integral's form is confirmed (§3.1). A 0.77 dB median against a
0.094 dB speckle floor is a real but small signal, and the project says so.

*Not valid:* the criticism assumes the project claims to *retrieve* biomass from X-band. It does
not. It claims to **rank plots within a cohort** around an externally supplied level, and it
prices that claim honestly — the 9.5 t vs 89.4 t line is not a concession the critic extracted, it
is the submission's own headline. Saturation degrades a ranking far less than a retrieval, and
the ranking has independent support the critic ignores: a SAR-only cotton label predicted the
right plots on a December scene it never saw, at p = 1.26e-11.

*What this means practically:* the counterargument cannot be defeated but it can be pre-empted, and
pre-empting it converts the project's biggest vulnerability into another demonstration of the
discipline it is selling. See §17, experiment 1.

---

## 16. Biggest Opportunities — ranked by Impact × Feasibility

| # | Opportunity | Impact /5 | Feasibility /5 | Product |
|---|---|---:|---:|---:|
| 1 | Fix the two false claims in `leakage_analysis.md` (§3.1, §3.3) | 5 | 5 | **25** |
| 2 | `p < 0.005`, or `n_perm = 999` | 4 | 5 | **20** |
| 3 | `requirements.txt` + `README` + data-acquisition step | 4 | 5 | **20** |
| 4 | Resolver probes `kaggle_dataset/` (2 lines) | 4 | 5 | **20** |
| 5 | Pre-empt X-band saturation in write-up + deck (§17.1) | 5 | 4 | **20** |
| 6 | Fix or restate the ANOVA axis claim (§3.2) | 5 | 3 | **15** |
| 7 | `ACCUM_SPAN` sensitivity sweep, printed | 4 | 3 | **12** |
| 8 | Price the district-mix prior into the uncertainty budget | 4 | 3 | **12** |
| 9 | Null-model ablation, `a() ≡ 1` | 3 | 4 | **12** |
| 10 | Re-order the write-up to lead with what is established (§13) | 3 | 4 | **12** |

Items 1-5 are all `HIGH BENEFIT / LOW EFFORT` and together are under a day.

---

## 17. Experiment Plan

Only experiments completable in under a day each.

**1. X-band saturation, tested on the shipped data.**
*Hypothesis:* canopy departure saturates against NDVI above some NDVI level.
*Experiment:* regress `season_integral_db` (and peak departure) on NDVI in bins from
`work/farm_joined.csv`; fit linear vs saturating (log or asymptotic) forms; compare on held-out
plots. *Metric:* per-bin slope; ΔAIC between forms. *Interpretation:* a flattening slope at high
NDVI confirms saturation. *Decision rule:* if saturation is present, say so in the write-up and
state that it bounds the ranking's dynamic range at the top end — which is a limitation the
uncertainty budget already absorbs. **Reporting the saturation is a win either way**; the loss
condition is being asked about it and having no number.

**2. `ACCUM_SPAN` sweep.**
*Hypothesis:* the village total is insensitive to `ACCUM_SPAN`; the per-plot spread is not.
*Experiment:* re-run `yield_forecast` at 0.15 / 0.30 / 0.45. *Metric:* village total, per-crop
t/ha, zone spread. *Decision rule:* if the total moves <1 %, print the table and the criticism is
answered permanently. If it moves more, that is a finding and belongs in the budget.

**3. Null-model ablation.**
*Hypothesis:* `a() ≡ 1` changes the village total negligibly and the plot ranking entirely.
*Experiment:* one run with the response forced to 1.0. *Metric:* Δ village total; Spearman between
ranked plot forecasts with and without. *Interpretation:* quantifies exactly what the radar buys.
*Decision rule:* report it regardless. It is the ablation a reviewer will ask for.

**4. ANOVA with the correct axis.**
*Experiment:* pass `axis="departure_T6"` at `s2_ndvi.py:572` and re-run.
*Decision rule:* whatever it returns, record it. If the result weakens, that is the fourteenth
entry in the ledger and it costs less than being caught.

---

## 18. Do Not Waste Time On

- **Adding model capacity.** No labels; a CNN has nothing to regress onto. This was closed in Round 3 planning and it is still right.
- **Chasing district-level yield numbers from `data.desagri.gov.in`.** The portal refused machine fetch twice in-session; the state-level `Y_ref` is defensible, and the rank-based statement about Vadodara already covers the direction.
- **Raising tier-1 coverage.** Recorded as a missed target and defended well. Loosening a threshold now would undo the strongest stability result.
- **Re-running the Kaggle notebook again for cosmetics.** It already reproduces. Only re-run if a *number* changes.
- **Rewriting `figures.py`.** 68 KB, zero test coverage, and none of it affects a reported number. Leave it.
- **Adding more `docs/`.** Nine files is already at the point where volume hurts. Fix the two false claims in the one that matters instead.
- **Re-deriving the deck from scratch.** Trim the notes, re-order two slides, done.

---

## 19. Final Priority Matrix

Ordered by ROI. Roughly three days remain.

| Priority | Action | Expected Impact | Effort | Risk | Reason |
|---|---|---|---|---|---|
| 1 | Correct `leakage_analysis.md` §3.1 and §3.3 | Removes the only self-contradiction a judge can catch | 1 h | None | Plausibility is 25 pts and this is the claim it rests on |
| 2 | `p < 0.005` in write-up and log (or `n_perm=999`) | Removes an instant statistical tell | 15 min (+re-run if 999) | Low | Cheapest credibility gain available |
| 3 | `requirements.txt` + `README` + data step | Moves Documentation; satisfies the winner's obligation | 1 h | None | Currently un-reproducible off Kaggle |
| 4 | Resolver probes `kaggle_dataset/` | Repo actually runs for a judge | 10 min | None | File already ships; resolver ignores it |
| 5 | Fix or restate the ANOVA axis claim (§3.2) | Removes a visibly mis-specified pre-registered test | 2 h + re-run | **Medium** — result may weaken | Record either outcome; being caught is worse |
| 6 | Pre-empt X-band saturation (write-up + 1 deck paragraph) | Defuses the strongest attack | 2 h | Low | §15 |
| 7 | `ACCUM_SPAN` sweep, printed by the run | Closes the "hand-set constant" charge | 4 h | Low | §4.6 |
| 8 | Quote the rule-fires back-test number (−0.216, n=732) | Pre-empts an obvious question | 30 min | None | Already computed, not quoted |
| 9 | Price the district mix into the budget | Genuine differentiator | 4 h | Medium | §8 |
| 10 | Re-order write-up to lead with established results | Better first impression | 2 h | Low — word budget is at 2000/2000 | §13 |

**If only three things get done: 1, 2, 3.** They are under three hours together and they remove
every finding a judge can verify without running anything.

---

## 20. Final Judge Verdict

**Current Level: Strong Competition Project**, at the boundary of Finalist-Level.

It is not yet Finalist-Level for one reason: the submission's distinguishing claim is validation
integrity, and its validation document contains claims its own modules contradict. That is
recoverable in an afternoon, and until it is, the strongest thing about the project is also its
most falsifiable.

**Evidence required to justify Finalist-Level:**
- `leakage_analysis.md` accurate against every module it describes, with the season integral's selection and `COTTON_NOV_DB`'s optical informing both stated openly (§3.1, §3.3).
- The pre-registered ANOVA either corrected or its claim narrowed to what the test shows (§3.2).
- `p < 0.005` stated correctly (§4.1).
- A cloned repository that runs (§4.2, §4.4).

**Evidence required to justify Winner-Contender, beyond the above:**
- A measured answer to the X-band saturation question rather than silence (§17.1).
- `ACCUM_SPAN` swept and printed, so no constant in the model is hand-set without a sweep (§17.2).
- The district-mix prior priced in the uncertainty budget, making the budget a complete decomposition of assumption versus measurement (§8) — no competitor is likely to have that.
- The null-model ablation, so the question "what does the radar actually buy you" has a number (§17.3).

The distance to Winner-Contender is roughly two days of work, and none of it is modelling.

---

## 21. Sources

External sources retrieved in-session. No other external claim appears in this report.

- Crop parameter estimation from ground-based X-band (3-cm wave) radar backscattering data — *Remote Sensing of Environment*, 1991. https://www.sciencedirect.com/science/article/abs/pii/003442579190081G
- Comparing the relationship between NDVI and SAR backscatter across different frequency bands in agricultural areas — *Remote Sensing of Environment*, 2025. https://www.sciencedirect.com/science/article/pii/S0034425725000161
- Relating X-band SAR Backscattering to Leaf Area Index of Rice in Different Phenological Phases — *Remote Sensing* 11(12):1462. https://doi.org/10.3390/rs11121462
- GalaxEye Mission Drishti (world's first OptoSAR satellite, launched 3 May 2026). https://galaxeye.space/mission-drishti-launch

## 22. Verification status

- **Personally re-verified against the cited lines:** §3.1, §3.2, §3.3, §4.1, §4.2, §4.3, §4.4, §4.7, §8 (`crop_type.py:412` comment contradiction), §12.2.
- **Cited from an auditor and read but not independently re-derived:** §4.5, §4.6, §5 (imputation-into-Moran mechanism), §6 (Round 2 header verification, guard-defeat routes), §10 (all items).
- **Not verified, flagged as such in place:** the effective-sample-size argument in §5.
- **The adversarial refutation pass did not run.** Findings here have not been attacked by an independent skeptic, so treat MEDIUM and LOW severities as less filtered than CRITICAL and HIGH.

---

## 23. Status of these findings (updated 2026-09-01)

The audit above is a snapshot taken on 2026-08-31 and is **not** rewritten as findings are
closed — a report that quietly edits itself is worth nothing. This section records what has
been actioned since, with the section that covers it.

| § | Finding | Status |
|---|---|---|
| 3.1 | `leakage_analysis.md` claimed the season integral was optically untouched | **Fixed.** Corrected in place under a heading saying so; the run now prints all three integral variants (signed +0.564, clipped +0.472, absolute −0.085) instead of two, and the row mislabelled `(clip>=0)` is corrected. `AGENTS.md` S23a. |
| 3.2 | ANOVA residualised against a variable that stopped being the ranking axis | **Fixed, and the result did not survive.** `axis` is now required. Corrected, tier-2 labels carry no NDVI information beyond their axis (p = 0.43) while the tier-1 control passes (p = 0.005). Pre-registered claim 12 is now **contradicted** in the ledger. `AGENTS.md` S24. |
| 3.3 | `COTTON_NOV_DB` listed as optically untouched | **Fixed** in the document; the pre-registered string in `validate.RESERVED_TEST` is left standing with the correction recorded beneath it. `AGENTS.md` S23a. |
| 4.1 | Moran's `p = 0.005` was the floor of 199 permutations | **Fixed.** 999 permutations, exceedance count printed, `p<` printed when it means `<`. Still zero exceedances, so `p < 0.001`. `AGENTS.md` S23b. |
| 4.2 | No dependency manifest, no README, repo unreproducible | **Fixed.** `requirements.txt` pinned to the shipped run, `README.md` with the data-acquisition step. `AGENTS.md` S23c. |
| 4.4 | `round2_crops.csv` not at any probed path | **Fixed.** Resolver probes `kaggle_dataset/`; two new tests. |
| 4.5 | Back-test headline not information-fair | **Partly addressed.** The write-up and deck now quote −0.216 on the 732 plots where the rule fires alongside the −0.119 headline. The information asymmetry between B1 and B4 is still there and still worth stating in the docs. |
| 4.6 | `ACCUM_SPAN` had no sensitivity sweep | **Fixed.** Swept 0.15–0.45 and printed; the village total moves ±0.9 % across a 3× range. `AGENTS.md` S25. |
| 4.7 | Tier-1 positive control failed | **Resolved by 3.2.** Under the correct axis the control passes at p = 0.005. It had been failing *because* of the axis defect. |
| 8 | District crop mix not priced in the uncertainty budget | **Fixed, and it was the largest omission.** ±61.5 t, second only to the state reference and nine times every radar term. Scale calibrated from how wrong the mix is on Rice and Cotton. `AGENTS.md` S26. |
| 15 | X-band saturation unaddressed | **Fixed by measurement.** Across six NDVI bins the departure is monotone increasing and the increment does not collapse; over the range these fields occupy it does not saturate. `AGENTS.md` S25. |
| 4.3 | "Runs offline from cache" claim false | **Fixed, by making the claim true.** `s2_ndvi.search` is now cache-first; six `stac_*.json` files ship. Demonstrated with every `urlopen` raising: the step completes and picks the identical dates, both reserved scenes included. `AGENTS.md` S27. |
| 8 (tie-break) | R2 reserved scene chosen by API return order among three 0.0 %-cloud candidates | **Fixed** as a side effect of 4.3 — the cached response pins the choice. |
| 5 | 16 % of plots have partly synthetic features, undisclosed in prose | **Fixed.** The write-up now states 153 of 966 (82 interpolated from their own dates, 71 imputed from neighbours) and attaches the consequence: the back-test uses only the 813 measured, Moran's I does not, so part of its positive I is the imputation. `AGENTS.md` S28. |
| 6 | Reserved-date guard is a lint, not enforcement | **Documented, not strengthened.** `leakage_analysis.md` now says what it is and what defeats it. |
| 10 | `gates.py` G1 threshold duplicated as a bare literal; 12 dead columns; no coverage of `gates`/`s2_ndvi`/`farm_features` | **Open.** None affects a reported number. |

| 12.3 | Dev scratch ships to judges: `NEXT_SESSION.md`, unmarked logs, an unexplained 120 KB `AGENTS.md` | **Fixed.** `NEXT_SESSION.md` deleted — it still stated 898.3 t against the shipped 893.9 t, a self-contradiction a judge finds in thirty seconds. `logs/README.md` names the shipped run. `AGENTS.md` opens with a preface saying what it is and where to read instead. |
| 17.3 | Null-model ablation `a() ≡ 1` never run | **Fixed.** Reported as the span-0 row of the existing sweep, so it runs through the shipped code path rather than a re-implementation: **910.1 t against 893.9 t, −1.8 % on the total, while the median plot moves 11.8 % and 734 of 966 move over 5 %.** The radar redistributes and does not set the level, which is what the uncertainty budget says from the other side. `AGENTS.md` S32. |
| 4.1 (second) | The headline rho quotes `p = 8.11e-71` on 813 spatially autocorrelated plots | **Fixed.** A 500 m block bootstrap over 50 cells, resampling whole cells: rho = +0.569, **95 % [+0.508, +0.618]**. The analytic p assumed independent plots and this project's own Moran's I says they are not. Both are printed, and the interval is named as the honest statement. |
| 11.2 / 14.9 | The falsification ledger is buried in `docs/research_log.md`, which no judge opens | **Fixed.** The ledger is now `validate.LEDGER` in the source, printed by every run, and drawn as `figures/ledger.png` in the gallery. The counts are derived from the tuple, and a test fails if they are typed anywhere else. |
| 4.5 | Back-test is one point, and the information asymmetry is unstated | **Addressed.** `backtest.horizon_curve` runs every split the six dates admit. **The pre-registration was contradicted**: +0.140 [+0.071, +0.202] at 60 days against −0.180 [−0.330, −0.056] at 30 — positive at the *longer* horizon. The driver is phenology, not horizon length, and it is the first evidence the crop calendar earns its place. `AGENTS.md` S32. |
| 13.2 / 15 | "Your rule doesn't beat persistence — why believe the forecast?" and the flat hold over cotton's 56 % projected share are unobserved | **Addressed by measurement.** 16 free Sentinel-1 RTC passes as a validation-only witness. Cotton is the only cohort above its own June bare soil after 12 November and **rises +0.985 dB to 21 December**, so the flat hold is not optimistic. Also: a 6-pass season integral ranks plots like a 13-pass one at **rho = +0.915**, which prices the competition's own six-date premise. Three pre-registered claims, all held, and the run says plainly that confirmations are worth less than contradictions. `AGENTS.md` S33. |
| 15 (second) | X-band saturation answered only by our own measurement, with no literature anchor | **Fixed.** `sar_research.md` now cites Inoue, Sakaiya & Wang 2014 (*Remote Sensing* 6(7):5995) — panicle biomass is the canopy variable best correlated with X-band σ⁰, and the paper's within-image "water-point" differencing is a published antecedent for our own bare-soil anchor — and Prashnani & Justice 2026 (*Remote Sensing* 18(8):1238), whose Central-India kharif result puts SAR-only multiclass accuracy at 48.3 % with rice and cotton the only transferable crops. Those are exactly our two tier-1 crops. |
| 8 (second) | Should `Y_ref` use a newer official estimate? | **Checked and closed.** Verified 2026-09-02: DA&FW publishes 1st/2nd/3rd Advance Estimates for 2025-26 and Final Estimates only for 2024-25. The 3rd AE already in use is the latest published, and the write-up now says so. |
| 3.3 (second) | The number this finding quotes, `0.690 vs 0.499-0.532`, is itself wrong | **Fixed 2026-09-03, and it was found by cross-checking the deck brief rather than by any gate.** The shipped run prints the other four cohorts at Bajra 0.474, Rice 0.502, Maize 0.505, Groundnut 0.532 — the floor is **0.474**. `logs/writeup_trace.txt` had matched `0.499` to a substring of a back-test confidence interval, `[-0.499 -0.141]`, which is the §S18 defect class recurring inside the document the tracer exists to protect. The claim is unaffected: cotton 0.690, p = 1.26e-11. Corrected in `validate.LEDGER`, `writeup.md`, `build_deck.py`, `validation_strategy.md`, `research_log.md` and the check-in HTML; §3.3 above is left as written, per the rule at the head of this section. `AGENTS.md` S38. |

**Scorecard after these changes**, on the same `INTERNAL ESTIMATE` basis as §2: Technical
Soundness 22 (+2, the saturation and `ACCUM_SPAN` measurements), Creativity 13 (+1, the
calibrated district-mix scenario), Plausibility & Defensibility 22 (+5, the leakage
contradictions removed and the budget completed), Aggregation 14 (unchanged), Documentation &
Presentation 17 (+2, `README` and `requirements.txt`). **Total 88, from 78.**

The gap to a higher score is no longer documentation. It is that no experiment in this
submission tests a yield prediction against a yield observation, because none exists — and
that is a property of the competition, not of the work.
