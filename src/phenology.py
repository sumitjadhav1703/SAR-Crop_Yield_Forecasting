"""Per-plot growth curve, harvest date, and the season integral the forecast is built on.

This is the module Round 3 exists for. Round 2 had four acquisitions ending on 13 October
and had to discount the unobserved rest of the season with a hand-set per-crop constant --
`COMPLETENESS`, running from 1.00 for bajra down to 0.45 for cotton. Round 3 has two more
passes, 29 October and 12 November, which straddle the kharif harvest in central Gujarat.
That means the discount can be **measured per plot** instead of assumed per crop, and for
the plots whose crop is still standing on 12 November it means there is a real forecast to
make rather than an estimate to report.

=== THE BASELINE, AND WHY IT IS NOT A DATE ===

Every quantity here is a departure from the plot's own bare soil, never an absolute level.
Absolute levels are not comparable between neighbouring fields: two adjacent parcels differ
by several dB purely through soil roughness, tillage direction and texture, and none of
that is yield.

Round 2 referenced each field to `max(T1, T2)`, the brighter of the two June acquisitions.
That worked for a stack that ended in October. It does not work here, because the same
field is bare at BOTH ends of this stack -- T1 on 6 June is pre-sowing and T6 on 12
November is after most of the kharif harvest -- and the two bare states are two months of
weather apart. Referencing November canopy against a June soil level charges the plot for
the seasonal drying of its own soil.

So the baseline is the plot's own T1 level, carried across the season by a **scene-level
bare-soil drift** measured on ground that never had a crop on it: AOI pixels outside every
farm polygon and outside the built-up tail. That keeps what is specific to the plot (its
own soil brightness) and removes what is common to the date (how wet the district was).

=== THE SIGN, AND HOW IT WAS SETTLED ===

Whether a canopy makes a plot brighter or darker at X-band HH is not decidable from theory
here, and it is not a detail: a sign-agnostic design reads a harvested field with bright
rough stubble as though it were peak canopy, and every integral downstream inherits that.

This module was first written sign-agnostic, on `|departure|`, with the direction deferred.
That was wrong, and it was wrong in a way that only an independent instrument could show.
`canopy_sign.py` pre-registered the expectation -- attenuation for four crops, volume
scattering for rice -- and then tested it against Sentinel-2 on the two dates where an S2
acquisition falls on the same day as a Capella pass, 13 October and 12 November. The
decisive form is the difference between those two dates on both instruments, because every
time-invariant property of a plot (size, soil texture, row orientation, position) is the
same on both dates and cancels.

The measurement, on 813 plots with clear optical cover on both dates:

    rho(dDeparture, dNDVI) = +0.569 overall, and POSITIVE on all five crops --
    rice +0.55, cotton +0.57, maize +0.65, bajra +0.33, groundnut +0.71, every one
    significant. Slope +4.9 dB per NDVI unit.

The pre-registered expectation was contradicted for four of the five crops. Greener plots
are BRIGHTER, not darker. The sign is therefore positive, uniformly, and it is a
measurement rather than an assumption.

Two consequences follow directly, and both are visible in the numbers:

  * `|departure|` is not usable for anything. Scored against optical, a season integral
    built on it reaches rho=-0.085 overall and is NEGATIVE for three of five crops. That
    is the difference between a feature and a number.
  * A NEGATIVE departure is not "canopy of the other sign". It is a plot darker than its
    own bare June soil -- smoother, drier or emptier -- and on the measured sign that means
    LESS vegetation, which is information and not noise.

    Two quantities are therefore built from the departures and they treat the negative side
    differently, on purpose, because they are different kinds of quantity:

      the season INTEGRAL uses the signed departure. A sum over the season should count a
      plot that fell below its own bare soil as worse than one that merely sat at it. Scored
      against optical the signed form reaches rho=+0.564 against +0.472 for the
      clipped-positive form, and it is the better of the two on four of the five crops
      (bajra 0.417 vs 0.376, maize 0.526 vs 0.451, rice 0.780 vs 0.704, groundnut equal;
      only cotton prefers clipping, 0.275 vs 0.312).

      the CLEARING FRACTION uses the clipped-positive depth, because it is a ratio of
      canopy remaining to canopy at peak and both must be non-negative for that ratio to
      mean anything.

    Clipping the integral was tried first and was an over-correction. It also made the
    maize cohort degenerate: 50.6 % of maize plots landed on exactly the cohort median of
    zero, so a downstream centred factor could not rank them at all. The signed form puts
    that at 0.4 %.

The caveat that survives: soil moisture also brightens X-band, and a field being irrigated
for rabi sowing between the two optical dates would green and brighten together without any
canopy volume scattering. What removes the scene-level version of that objection is that
the two dates have essentially the same antecedent wetness -- 14-day API 11.9 mm at T4 and
12.2 mm at T6 (`season_context`) -- so district rainfall cannot be the common driver.
Plot-level irrigation remains a real contributor and is stated as such rather than excluded.

=== WHAT SIX DATES DO NOT SUPPORT ===

An earlier version of this module assigned every plot a harvest DOY and a three-way
harvested / standing / no_canopy status. That has been removed, because it did not survive
the same optical test that settled the sign. Plots it called "standing" on 12 November were
the LEAST green of any group on that date (median NDVI 0.482 against 0.560 for the ones it
called harvested), the one-sided test that they should be greener returned p=1.00, and
stratifying by detected harvest date produced no separation in the optical change at all.

The reason is structural, not a bug to be patched. A canopy episode is observed on three
dates -- DOY 226, 286 and 316 -- with a sixty-day gap across the whole of September. Three
irregular samples cannot locate a transition to better than the sampling, and a date
inferred from them is a free parameter, not a measurement.

What the same three samples DO support is a continuous statement of how much of the canopy
signal a plot has already lost by 12 November, and that one validates: `cleared_fraction`
correlates with the optical change between the two dates at rho=-0.512, in the direction it
should -- the plots the radar says have cleared more are the plots that lost more greenness.
So the continuous quantity is kept and the categorical one is not.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

from geocode import DOY, SCENES

# T5 is excluded from every level-based quantity here. `farm_features` has already replaced
# its level with the T4-T6 interpolation, and re-deriving that interpolation from a curve
# that already contains it would make the point count look larger than the information is.
LEVEL_DATES = [c for _, c, _ in SCENES if c != "T5"]

# THE ANCHOR AND THE CANOPY WINDOW ARE DIFFERENT SETS OF DATES.
#
# T1 (6 June) is pre-sowing and T2 (19 June) is at or just after sowing: monsoon onset over
# central Gujarat was around 19 June and the T2 scene shows the wetting directly. Neither
# date can contain a canopy, for any of the five crops grown here. Round 2 used exactly
# this argument to pick its bare-soil reference.
#
# It follows that a departure measured at T2 is soil, not crop -- and that matters, because
# T2 is the most VARIABLE date in the stack at plot level (inter-quartile departure -0.79
# to +1.14 dB, against -0.58 to +0.76 at T6). Fields differ in drainage, tillage and sowing
# date, so they take up the first monsoon rain differently. Left in the canopy search, that
# soil heterogeneity was being read as a canopy peak for 37 % of plots and it put the median
# maize "harvest" in mid-August.
#
# So the two June dates ANCHOR the baseline -- their drift-corrected mean, which halves the
# anchor noise against using either alone -- and the canopy episode is searched only over
# the dates when a canopy can exist.
ANCHOR_DATES = ["T1", "T2"]
CANOPY_DATES = ["T3", "T4", "T6"]

# The canopy signal is the positive part of the departure. See the sign section above:
# this is measured against Sentinel-2, not assumed, and the sign-agnostic alternative was
# tested against the same reference and carries no vegetation information (rho -0.085).
CANOPY_SIGN = +1

# A plot needs a canopy episode before "how much of it has gone" means anything. Below this
# peak positive departure the ratio is dividing noise by noise and is left as NaN.
#
# The farm-mean speckle floor is 4.34/sqrt(2100) = 0.09 dB, so this is not what sets the
# threshold. What sets it is plot-level soil variability: the June anchor dates, which
# cannot contain a canopy, still show an inter-quartile departure spread of about 1.9 dB
# at T2. 0.5 dB is a judgement, roughly a quarter of that soil spread, and
# `clearing_sensitivity` reports 0.25 / 0.5 / 1.0 so a reader can see how much of the
# answer is this number rather than the data.
MIN_CANOPY_DB = 0.5


def bare_soil_drift(work: str, labels: np.ndarray, built_up: np.ndarray | None = None) -> dict:
    """Scene-level bare-soil level per date, dB, measured off ground that has no crop.

    `labels` is the rasterised farm-core label image from `farm_features.rasterise_cores`;
    zero means the pixel belongs to no farm. Excluding the built-up tail keeps the estimate
    on soil rather than on roofs, which respond to nothing.

    Returned relative to T1, so it is a drift and not a level.
    """
    from gates import read_aoi
    import glob

    import scene_diagnostics

    # The geocoded rasters on disk are UNCORRECTED -- the per-date offsets are applied
    # downstream, in `farm_features`. So they must be applied here too, or the baseline is
    # measured on one radiometric scale and the plots on another. Getting this wrong is
    # not subtle in its effect and is completely silent in its symptoms: with T6's +4.28 dB
    # applied to the plots and not to the baseline, every plot in the village reads as
    # 4 dB above bare soil in November and 97.7 % of them come out "still standing".
    offsets = scene_diagnostics.read_offsets(os.path.dirname(os.path.abspath(work)))["offsets_db"]

    stack = {}
    for _folder, code, _date in SCENES:
        hits = glob.glob(os.path.join(work, f"gamma0_lin_{code}_*.tif"))
        if not hits:
            raise FileNotFoundError(f"missing geocoded gamma0 for {code}")
        arr = read_aoi(hits[0])
        gain = 10.0 ** (offsets.get(code, 0.0) / 10.0)
        if gain != 1.0:
            np.multiply(arr, gain, out=arr, where=arr > 0)
        stack[code] = arr

    valid = np.logical_and.reduce([stack[c] > 0 for c in stack])
    off_farm = valid & (labels[:valid.shape[0], :valid.shape[1]] == 0)
    if built_up is None:
        # Drop the brightest 1 % of off-farm pixels: settlement, roads and field-edge
        # structures, none of which track soil moisture the way a field does.
        ref = np.minimum.reduce([stack[c] for c in LEVEL_DATES])
        cut = np.percentile(ref[off_farm], 99.0)
        off_farm &= ref <= cut
    else:
        off_farm &= ~built_up

    levels = {c: float(np.median(10.0 * np.log10(np.maximum(stack[c][off_farm], 1e-12))))
              for c in LEVEL_DATES}
    base = levels["T1"]
    drift = {c: levels[c] - base for c in LEVEL_DATES}
    drift["_n_pixels"] = int(off_farm.sum())
    drift["_levels_db"] = levels
    del stack
    return drift


def departures(df: pd.DataFrame, drift: dict, dates=None) -> np.ndarray:
    """Per-plot departure from its own drifting bare-soil baseline, dB.

    The anchor is the mean of the drift-corrected June dates -- each plot's own bare soil,
    with the district-wide moisture drift taken out first so the two are comparable before
    they are averaged.
    """
    dates = dates or CANOPY_DATES
    anchor = np.mean(
        [df[f"g0_db_filled_{c}"].to_numpy(dtype=float) - drift[c] for c in ANCHOR_DATES],
        axis=0)
    curve = df[[f"g0_db_filled_{c}" for c in dates]].to_numpy(dtype=float)
    baseline = anchor[:, None] + np.array([drift[c] for c in dates])[None, :]
    return curve - baseline


def canopy_depth(dep: np.ndarray) -> np.ndarray:
    """Canopy present, clipped at zero. For ratios -- peak, end, cleared fraction.

    NOT for the season integral: see the docstring. The integral uses `signed_departure`,
    which scores better against the optical reference and does not collapse the maize
    cohort onto a single value.
    """
    return np.clip(CANOPY_SIGN * dep, 0.0, None)


def signed_departure(dep: np.ndarray) -> np.ndarray:
    """Departure on the measured sign, negative side kept. For the season integral."""
    return CANOPY_SIGN * dep


def build(df: pd.DataFrame, drift: dict) -> pd.DataFrame:
    """Attach the phenology descriptors. No crop knowledge is used or required."""
    doys = np.array([DOY[c] for c in CANOPY_DATES], dtype=float)
    dep = departures(df, drift)
    depth = canopy_depth(dep)

    out = df.copy()
    for j, code in enumerate(CANOPY_DATES):
        out[f"departure_{code}"] = dep[:, j]
    # The June departures are reported too, as the soil control they are: a plot with a
    # large June departure is one whose soil behaved unusually, and `feature_audit` uses
    # that as a negative control rather than as a feature.
    june = departures(df, drift, ANCHOR_DATES)
    for j, code in enumerate(ANCHOR_DATES):
        out[f"soil_departure_{code}"] = june[:, j]

    peak_i = depth.argmax(axis=1)
    peak = depth[np.arange(len(depth)), peak_i]
    out["canopy_peak_db"] = peak
    out["canopy_end_db"] = depth[:, -1]
    out["has_canopy"] = peak >= MIN_CANOPY_DB
    # argmax over a curve that never leaves zero returns index 0, which would report a
    # canopy peak on 14 August for a plot that never grew one. Null it instead: the date of
    # a peak that does not exist is not a date.
    out["canopy_peak_doy"] = np.where(out["has_canopy"], doys[peak_i], np.nan)

    # Season integral of the canopy signal in dB, divided by the span so it reads as a mean
    # departure over the observed window rather than as an area whose units depend on the
    # calendar. This is the Monteith analogue Round 2 introduced as `accumulated_canopy`,
    # rebuilt on the drifting baseline, on six dates instead of four, and on the measured
    # sign. SIGNED, not clipped -- see the docstring for the measurement that settled it.
    trapz = getattr(np, "trapezoid", None) or np.trapz
    out["observed_integral"] = trapz(signed_departure(dep), doys, axis=1) / (doys[-1] - doys[0])

    # How much of its own canopy signal a plot has already lost by 12 November. Continuous,
    # bounded 0..1, NaN where there was no canopy episode to lose. This is what replaced
    # the harvest date: it is the quantity that survives the optical test (rho -0.512
    # against the 13 Oct -> 12 Nov NDVI change) where the date did not.
    with np.errstate(invalid="ignore", divide="ignore"):
        cleared = 1.0 - depth[:, -1] / peak
    out["cleared_fraction"] = np.where(out["has_canopy"], np.clip(cleared, 0.0, 1.0), np.nan)

    # Rate of change of the canopy signal on the last observed limb, dB/day. Negative means
    # still falling on 12 November; this is the slope the forecast extrapolates along for
    # the plots that have not finished.
    out["late_slope_db_day"] = (depth[:, -1] - depth[:, -2]) / (doys[-1] - doys[-2])
    return out


def clearing_sensitivity(df: pd.DataFrame, drift: dict,
                         minima=(0.25, 0.5, 1.0)) -> pd.DataFrame:
    """How much of the answer is the 0.5 dB in `MIN_CANOPY_DB`?

    Printed rather than argued. A threshold nobody has stress-tested is a free parameter
    wearing the clothes of a constant.
    """
    depth = canopy_depth(departures(df, drift))
    peak = depth.max(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        cleared = np.clip(1.0 - depth[:, -1] / peak, 0.0, 1.0)
    rows = []
    for m in minima:
        has = peak >= m
        c = np.where(has, cleared, np.nan)
        rows.append({"min_canopy_db": m,
                     "with_canopy": int(has.sum()),
                     "no_canopy": int((~has).sum()),
                     "median_cleared": float(np.nanmedian(c)),
                     "frac_over_0.8_cleared": float(np.nanmean(c > 0.8)),
                     "frac_under_0.2_cleared": float(np.nanmean(c < 0.2))})
    return pd.DataFrame(rows)


def report(df: pd.DataFrame, drift: dict) -> None:
    print("bare-soil drift, measured off %d AOI pixels that belong to no farm polygon "
          "and are not built-up" % drift["_n_pixels"])
    print("  date   level dB   drift vs T1 dB")
    for code in LEVEL_DATES:
        print(f"  {code}   {drift['_levels_db'][code]:8.2f}   {drift[code]:+13.2f}")
    print("  This is the part of every plot's change that the whole district shares, and "
          "it is removed before any plot is\n  compared with any other. What is left is "
          "the plot's own canopy.")

    print("\nper-plot canopy signal: clip(departure, 0), on the sign measured against "
          "Sentinel-2 (see canopy_sign.py)")
    print(f"  peak canopy     median {df.canopy_peak_db.median():5.2f} dB   "
          f"p10 {df.canopy_peak_db.quantile(.1):5.2f}   "
          f"p90 {df.canopy_peak_db.quantile(.9):5.2f}")
    counts = " ".join(f"{c}:{int((df.canopy_peak_doy == DOY[c]).sum())}" for c in CANOPY_DATES)
    print(f"  peak DOY        median {df.canopy_peak_doy.median():5.0f}   ({counts})")
    print(f"  canopy at T6    median {df.canopy_end_db.median():5.2f} dB")
    print(f"  season integral median {df.observed_integral.median():5.2f} dB "
          f"(signed mean departure over DOY 226-316)")
    n_no = int((~df.has_canopy).sum())
    print(f"\n  plots with a canopy episode above {MIN_CANOPY_DB} dB: "
          f"{int(df.has_canopy.sum())}  ({100 * df.has_canopy.mean():.1f} %); "
          f"below it {n_no}")
    c = df.cleared_fraction
    print(f"  cleared fraction by 12 Nov   median {c.median():.2f}   "
          f"p10 {c.quantile(.1):.2f}   p90 {c.quantile(.9):.2f}")
    print(f"    mostly cleared (>0.8)  {int((c > 0.8).sum()):4d}"
          f"     barely cleared (<0.2)  {int((c < 0.2).sum()):4d}")
    print("  No per-plot harvest DATE is reported. Three canopy samples with a sixty-day "
          "gap across September\n  cannot locate a transition, and the date this module "
          "used to emit failed the optical test that\n  the continuous cleared fraction "
          "passes. See the module docstring.")


def run(work: str | None = None) -> tuple:
    """Build the phenology table. Returns (frame, drift) so the caller can also report.

    Extracted out of `__main__` so `pipeline.run()` executes the same code path a manual
    `python src/phenology.py` does -- Round 2 shipped three phases whose reports lived only
    in a `__main__` the notebook never reached.
    """
    import glob

    from osgeo import gdal

    import farm_features

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    work = work or os.path.join(root, "work")
    frame = pd.read_csv(os.path.join(work, "farm_features.csv"))

    records, mem = farm_features.load_farms()
    ref = gdal.Open(sorted(glob.glob(os.path.join(work, "gamma0",
                                                  "gamma0_lin_T1_*.tif")))[0])
    labels = farm_features.rasterise_cores(mem, (ref.RasterYSize, ref.RasterXSize),
                                           ref.GetGeoTransform())
    ref = None
    mem = None

    drift = bare_soil_drift(os.path.join(work, "gamma0"), labels)
    return build(frame, drift), drift


if __name__ == "__main__":
    import farm_features

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    work = os.path.join(root, "work")
    frame = pd.read_csv(os.path.join(work, "farm_features.csv"))

    out, d = run(work)
    out.to_csv(os.path.join(work, "farm_phenology.csv"), index=False)
    report(out, d)
    print("\nsensitivity of the clearing measure to the minimum-canopy threshold:")
    print(clearing_sensitivity(frame, d).to_string(index=False))
