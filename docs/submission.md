# Submission

## What ships

| file | rows | what it is |
|---|---|---|
| `outputs/farm_forecast.csv` | 966 | the plot forecast **and the chain that produced it** |
| `outputs/village_summary.csv` | 6 | five crops plus ALL, area-weighted |
| `outputs/zone_summary.csv` | 46 | 500 m cells with ≥ 5 farms |
| `figures/*.png` | 12 | media gallery, all 16:9, `cover.png` is the required cover |
| `sokhda_yield_forecast.ipynb` | — | the public notebook, generated from `src/` |

There is no prescribed schema this round — no `sample_submission.csv` exists. That removes a
constraint and adds an obligation: the columns are ours to choose, so they are the ones a
judge can check the work with rather than the smallest set a parser accepts.

### `farm_forecast.csv`

```
village_id  village_name  farm_id  area_ha
crop_type  crop_confidence  crop_margin  long_duration_flag
data_quality  n_valid_dates
has_canopy  canopy_peak_db  canopy_peak_doy  canopy_end_db  cleared_fraction
season_integral_db  extrapolated_fraction
accumulation_response  yield_ref_t_ha  yield_forecast_t_ha  production_t
```

Every column after `n_valid_dates` is a term in the model, so a judge can reconstruct any
plot's forecast by hand from its own row.

## The schema gate

`submit.validate()` raises on every failure. Nothing in it is a warning.

- **full column equality** against `REQUIRED`, not a prefix match — Round 2 used a prefix
  check and it let a stray column into a shipped file;
- exactly 966 rows, `farm_id` 1..966 unique;
- no NaN or Inf anywhere except the two documented-nullable columns;
- `crop_type` inside the permitted five;
- `extrapolated_fraction` and `cleared_fraction` inside [0, 1];
- every forecast inside its crop's `PLAUSIBLE_T_HA` band.

`PLAUSIBLE_T_HA` is duplicated in `submit.py` on purpose: this gate runs on the file that
ships, not on the frame that produced it, so it must not import its bound from the module it
is checking.

### The two nullable columns, and why the gate is stricter than "allow NaN"

`cleared_fraction` and `canopy_peak_doy` are null exactly where `has_canopy` is false (378
plots). This is a definition, not a gap: a plot that never rose 0.5 dB above its own bare
soil has no canopy episode, so there is nothing for a clearing fraction to be a fraction
**of**, and the date of a peak that does not exist is not a date. Writing 0.0 would claim
nothing was cleared and 1.0 would claim everything was.

The gate therefore asserts the null pattern **exactly** — null if and only if
`~has_canopy` — rather than tolerating NaN generally. A NaN clearing fraction on a plot that
did grow a canopy is a bug, and the gate says so.

## The geometric roll-up gate

`village_summary` groups plots by a text column inside one village. That is an aggregation
*assumption* until something checks it against the ground, and `Sokhda_Village.shp` is
shipped precisely so it can be.

`submit.village_containment()` reprojects both shapefiles to UTM 43N, intersects every plot
polygon with every village polygon, and assigns each plot to the village it shares the most
area with. Largest-shared-area rather than centroid-in-polygon: an edge parcel can have its
centroid outside the boundary while most of its ground is inside. `report_containment` then
**raises** if any plot's geometric village differs from its `VILLAGE` attribute, or if more
than 1e-6 ha of real parcel sits outside every village polygon.

On the shipped run:

```
Sokhda_Village.shp holds 1 polygon(s): Sokhda
962 of 966 plots assign to the same village by largest shared area as by attribute
0 disagree; 4 intersect no village polygon at all (0.0000 ha)
7 degenerate parcels had zero intersection with every polygon and were placed by centroid
parcel area inside the boundary 447.5 ha of 447.5 ha digitised (100.00 %)
the village polygon encloses 1174.1 ha, so the digitised parcels are 38.1 % of Sokhda
```

The four unplaceable plots are degenerate geometry — they enclose no measurable ground, so no
geometric test can place them, and the tolerance is the same 1e-6 ha the parcel audit uses.
They carry a row and zero area weight. **100.00 % of digitised parcel area is inside the
boundary**, which is the statement the village total actually rests on.

It runs *first* inside `submit.run()`, before any table is written: if the geometry and the
attribute disagree, every table below is aggregating over the wrong set.

## The cross-check

`submit.cross_check()` requires the village table to be **reconstructible from the plot
table**: total production, total area, and per-crop production must all match to 1e-6.

This caught a real defect. Rounding the plot table to four decimals *after* aggregating it
at full precision left the village total 0.0015 t away from the sum of the shipped CSV — a
judge adding up the file would have got a different number from the summary. Fixed by
rounding once, before anything is aggregated, so the village row is literally the sum of the
file that ships. There is a regression test for it.

## Tests

37 tests, all passing, on the pieces that break silently rather than loudly:

- calibration arithmetic β⁰ → σ⁰ → γ⁰ against a hand-computed value;
- bounded phase correlation stays near its coarse estimate, and the height sweep is
  **not** bounded (verified by counting real calls, excluding the docstring);
- clipped canopy depth, cleared fraction at 1 / 0 / NaN, a mid-season dip that recovers is
  not read as clearing, the signed integral counts the negative excursion;
- extrapolation only fires for a crop whose season outruns the stack, and the projection
  never grows a canopy — a falling limb is held flat;
- `centred_factor` puts the cohort median at exactly 1.0 (odd cohort), with the even-cohort
  tolerance asserted explicitly;
- the forecast **raises** rather than clipping an implausible yield;
- the reference yield is the forecast season, not the previous one;
- twelve schema-gate tests: extra column, reordered column, missing row, NaN in a solid
  column, Inf, a null that does not match `has_canopy`, the documented null pattern, a sixth
  crop, an implausible yield, the village cross-check, and the round-before-aggregate
  regression.

## Reproducing it

```
cd "Round 3"
.venv/bin/python -m pytest tests/ -q          # 37 passed
.venv/bin/python src/pipeline.py              # full chain, clean work/, ~10 min
```

Every number quoted in the write-up is printed by that run. This is enforced structurally:
every `report()` is called from `pipeline.run()`, never left in a module's `__main__`, which
`pipeline.run()` does not execute. Round 2 shipped that defect three separate times.

The Sentinel-2 step is the only one needing a network. `work/s2_cache/` holds both halves of
it — the STAC search responses (`stac_*.json`) and the mosaicked rasters — so a notebook with
internet disabled can ship the cache and still run.

**This was false until 2026-09-01 and is recorded rather than quietly fixed.** Only the
rasters were cached; `s2_ndvi.run` called `search()` before any cache was consulted, so an
offline run raised on the first window and never reached the files it shipped. Three places
claimed otherwise. Caching the search also pins the reserved-scene choice: the 16 January
window returns three candidates all at 0.0 % cloud and the winner was decided by whatever
order Earth Search returned them in, so a re-indexed catalogue could have handed a future run
a different held-out scene without saying so.

`--no-s2` completes the forecast without any external validation and says so out loud.

## Known limitations, stated on the record

- Tier-2 crop labels (74.3 % of area) are **allocated from the district mix**, not measured.
  The shipped tables mark which is which.
- The back-test does not show positive skill. The claim is "not worse than persistence".
- `Y_ref` is a state figure. No district correction is applied because no district 2025-26
  estimate is published; Vadodara ranks 1st in Gujarat for maize yield and 2nd for cotton,
  so those two are conservative by a known sign.
- Plot-level irrigation is not separable from plot-level canopy in the sign measurement.
- The AOI is **one village**, not the "expanded set of villages" the Overview describes.
