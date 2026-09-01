# The data, audited

Everything here was read off the distributed files. Nothing is carried over from the brief
without checking it.

## The stack

Six Capella X-band HH stripmap SLC acquisitions, `complex_int16` in slant range, each with
its own `_extended.json` carrying `scale_factor`, `radiometry: beta_nought`, a degree-3
NESZ polynomial and `calibration: full`.

| | date | local time (IST) | look | view azimuth | incidence |
|---|---|---|---|---|---|
| T1 | 2025-06-06 | 12:55 | left | 134.7° | 35.24° |
| T2 | 2025-06-19 | 07:44 | left | 135.1° | 28.77° |
| T3 | 2025-08-14 | 08:41 | left | 135.1° | 28.69° |
| T4 | 2025-10-13 | 07:56 | left | 135.0° | 31.53° |
| **T5** | **2025-10-29** | **01:37** | **right** | **318.4°** | **29.84°** |
| T6 | 2025-11-12 | 19:22 | left | 135.2° | 29.75° |

Two of these are new relative to Round 2 and both are awkward. **T5 is right-looking with
the opposite view azimuth**, so every shadow, layover and row-direction response flips, and
it is a pre-dawn pass at peak dew where T1 is midday. Neither effect exists in Round 2's
four-date stack and both would masquerade as crop signal if left alone.

The `20250619` folder contains a **byte-identical duplicate of the T1 SLC**. The filename is
built from the folder stem rather than globbed, which defeats it.

## Geometry

`gdal.Warp(rpc=True, errorThreshold=0.0)` against each scene's RPCs at a fitted terrain
height. The height is fitted per scene by sweeping and minimising the residual shift against
the T1 master:

```
T1 -17.15   T2 -17.61   T3 -17.62   T4 -17.41   T5 -16.73   T6 -17.54 m
mean -17.34   spread 0.89   std 0.32 m
```

Six scenes at four distinct incidence angles agreeing on one height to within a metre is the
check that this is terrain rather than a fudge factor: a per-scene fudge would have no
reason to agree.

Residual co-registration is then solved by two-scale bounded phase correlation — a coarse
8×-decimated unrestricted search, then a fine search bounded to 20 m of the coarse estimate.
Residuals land at 0.13–0.32 m against a 1 m pixel.

## The parcels

966 plots, **one village**: `Sokhda`, `ID_1 = 22` in `Sokhda_Farms.shp` and `ID = 22` in
`Sokhda_Village.shp`. The Overview's "expanded set of villages" is not what the shapefile
contains — it is the same single village and the same 966 plots as Round 2. Stated from the
village file rather than the farm attribute: **`Sokhda_Village.shp` holds exactly one
feature**, `{ID: 22, VILLAGE: 'Sokhda'}`, enclosing **1174.1 ha**. The 966 digitised parcels
total 447.5 ha, so the study area is **38.1 % of the village polygon** — the mapped farmland,
not the village. Everything else inside the boundary (the built-up core, roads, water, any
undigitised field) is not forecast and is not claimed.

The attribute table is close to useless. `id` is 1.0 on every row and one field has an empty
name and all-null values. **`FID` is the only stable key.**

**There is no crop attribute.** The five fields are `FID`, `id`, an unnamed all-null one,
`ID_1` and `VILLAGE`. The Overview says "the crop classification carried forward from prior
rounds"; it is not in the shipped shapefile, which is why `crop_type.py` exists and why the
canopy sign and the back-test score against *our own* Round 2 labels rather than a supplied
column. Worth stating plainly, because a reader who assumes labels were provided will read
the classification module as unnecessary work.

- median plot 0.27 ha, maximum 3.49 ha, total 447.5 ha
- **10 parcels have degenerate geometry under 1e-6 ha.** They still carry a row — the rubric
  wants all 966 — and area weighting is what keeps them from voting.
- **13 parcels are MULTIPOLYGON.** GDAL hands out borrowed references to sub-geometries;
  `.Clone()` on every one, always. Without it the run survives locally and segfaults Kaggle
  with no traceback.

## Radiometry

```
beta0  = |I + jQ|² · scale_factor²
sigma0 = beta0 · sin(theta) − NESZ(range)
gamma0 = sigma0 / cos(theta)
```

Per-farm statistics are taken on an **eroded** polygon core, so a plot's number is not
contaminated by its bund or by the next field. Validity policy is ≥4 measured dates of 6
(Round 2 used ≥3 of 4).

Coverage: 966 farms carry a row; the great majority are `measured` and the remainder are
imputed from the nearest measured donor, with the donor distance recorded per plot.

## The two things that make raw levels uncomparable across dates

**Scene-level bare-soil drift.** Measured on 16.47 M non-farm AOI pixels — ground that
cannot have grown a crop — the district bare-soil level is **+1.65 dB higher at T6 than at
T1**. Any model that compares a plot's November level to its June level without removing
that reads a district-wide radiometric shift as biomass. Every departure in this project is
computed after removing the scene offset.

**T5's geometry.** T5's level is never used. `farm_features` replaces it with the T4–T6
interpolation and keeps only the residual `t5_anomaly` as a weak covariate, and the
look-direction control in `validate.py` tests whether even that residual tracks parcel row
orientation. It does not: |rho| ≤ 0.051, p = 0.195, n = 650 elongated parcels.

## The consequence for the model

Because levels drift and each plot's soil differs, **every model input is a departure from
that plot's own June bare soil**, anchored on the mean of 6 and 19 June (both pre-sowing)
with the scene drift removed first. Zero means "this plot, at its own soil". That is the
only frame in which a 0.27 ha plot in one corner of the village is comparable to one in
another.
