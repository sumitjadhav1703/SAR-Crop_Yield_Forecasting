"""End-to-end run: raw Capella SLC -> outputs/farm_forecast.csv. One entry point.

Order matters and is enforced. The Phase 1 gates run between geocoding and everything else,
and a gate failure raises rather than warns -- Round 1's rule, that every "graceful
fallback" is somewhere a validation gate can silently stop running.

    geocode           calibrate, NESZ-correct, geocode and co-register six SLCs
    gates             G1 footprint / G2 co-registration / G3 radiometry   [BLOCKING]
    scene_diagnostics scene-level bare-soil drift, measured off non-farm ground
    farm_features     per-farm statistics on the eroded polygon cores
    s2_ndvi           Sentinel-2 on the SAR dates and two reserved dates    [NETWORK]
    canopy_sign       the pre-registered optical arbitration of the canopy sign
    phenology         departures from each plot's own June soil, season integral
    crop_type         two-tier six-date classification
    season_context    rainfall anomaly and the 2025-26 state reference yield
    yield_forecast    Y_ref(crop, season) * a(season-complete canopy integral)
    backtest          leave-future-out skill against four baselines
    validate          reserved optical, look-direction control, Moran's I
    submit            village + zone aggregation, schema-gated outputs
    figures           the media gallery

Round 3 deliberately ships FEWER modules than Round 2, not more. `health_index`,
`yield_estimate`, `benchmark` and `feature_audit` were ported, run, and then deleted:
the vigour index would have counted the same six departures the season integral already
integrates, `benchmark`'s ladder was replaced by a real leave-future-out back-test, and
`feature_audit`'s pre-registered sign audit was replaced by `canopy_sign`, which registers
its prediction before the measurement instead of alongside it. Only `morans_i` survived,
and it moved into `validate`.

The Sentinel-2 step is the only one that needs a network. Both halves of it are cached to
`work/s2_cache/` -- the STAC search responses AND the rasters -- so a Kaggle notebook without
internet enabled can ship the cache and still run. Until 2026-09-01 only the rasters were
cached and this sentence was false: the first window issued a search and an offline run died
before reaching a single cached file. `with_s2=False` skips the step entirely: the forecast
consumes no optical data, so the pipeline still completes -- what is lost is every external
validation, and the run says so out loud.
"""

from __future__ import annotations

import gc
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import backtest
import crop_type
import farm_features
import figures
import gates
import geocode
import phenology
import scene_diagnostics
import season_context
import submit
import validate
import yield_forecast


def _root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _rss_mb() -> float:
    """Resident set size in MB, or 0.0 where /proc is unavailable (macOS)."""
    try:
        with open("/proc/self/status") as fh:
            for line in fh:
                if line.startswith("VmHWM:"):        # peak RSS, not current
                    return int(line.split()[1]) / 1024.0
    except OSError:
        pass
    return 0.0


def _phase(title: str) -> None:
    """Phase banner carrying peak RSS.

    A Kaggle kernel dies on OOM with no traceback and no indication of which allocation
    lost, so the phase that reports the death is only the one that happened to ask last --
    twice now the failure moved a phase later after upstream memory was reduced. VmHWM is
    the high-water mark, which is what actually matters: it is what fragments the heap and
    what the kernel limit is compared against.
    """
    gc.collect()
    hwm = _rss_mb()
    print("\n" + "=" * 78)
    print(f"{title}" + (f"   [peak RSS {hwm:,.0f} MB]" if hwm else ""))
    print("=" * 78, flush=True)


def run(with_s2: bool = True, make_figures: bool = True) -> pd.DataFrame:
    root = _root()
    work = os.path.join(root, "work")
    out_dir = os.path.join(root, "outputs")
    os.makedirs(work, exist_ok=True)
    os.makedirs(out_dir, exist_ok=True)

    _phase("PHASE 1  calibration, geocoding, co-registration  (6 scenes)")
    geocode.process(os.path.join(work, "gamma0"))

    _phase("PHASE 1 GATES  (blocking)")
    if not gates.run():
        raise RuntimeError("Phase 1 gates failed; refusing to compute farm statistics "
                           "on an unverified warp")

    # Every `report()` below is called here rather than left in a module's `__main__`.
    # Round 2 hit the same defect three separate times: `pipeline.run()` never executes a
    # `__main__` block, so the shipped run printed nothing for a phase while the write-up
    # quoted its numbers. Every number the write-up uses has to come off this log.
    #
    # This runs BEFORE the farm statistics, not after. It reads only the gamma0 rasters, and
    # `farm_features` raises if `scene_offsets.json` is missing rather than defaulting the
    # offsets to zero -- so with the two phases the other way round the pipeline completed
    # only when a previous run had left the file behind, and died on a clean `work/`. The
    # ordering defect was invisible for exactly as long as nobody started from empty.
    _phase("PHASE 2  scene-level bare-soil drift, measured off non-farm ground")
    # Runs on the gamma0 rasters, not on `work` -- and it writes `scene_offsets.json`,
    # which `farm_features` and `phenology.bare_soil_drift` both read.
    wet = season_context.scene_wetness(os.path.join(work, "context"))
    offsets = scene_diagnostics.report(os.path.join(work, "gamma0"), wet)
    print("\nwrote", scene_diagnostics.write_offsets(work, offsets))

    _phase("PHASE 2b  farm-level features, six dates")
    feats = farm_features.build(os.path.join(work, "gamma0"))
    feats.to_csv(os.path.join(work, "farm_features.csv"), index=False)
    print(f"{len(feats)} farms; data quality: "
          + ", ".join(f"{k}={v}" for k, v in feats.data_quality.value_counts().items()))
    # The derived count, printed because the write-up quotes it and every number the write-up
    # quotes has to come off this log. `interpolated` fills a plot's missing date from its OWN
    # remaining dates; `imputed` fills it from the median of its eight nearest MEASURED
    # neighbours, so an imputed plot's observation is partly a neighbour's.
    partial = int((feats.data_quality != "measured").sum())
    print(f"{partial} of {len(feats)} plots are not fully observed on all six dates "
          f"({100.0 * partial / len(feats):.1f} %)")

    if with_s2:
        # Fetch only. The validation report needs `non_crop_flag`, which does not exist
        # until crop_type has run, so it is called further down rather than here.
        _phase("SENTINEL-2  same-day optical, plus two reserved dates  [NETWORK]")
        import s2_ndvi
        s2_ndvi.run()
    else:
        print("\nSENTINEL-2 STEP SKIPPED — the forecast is unchanged (it consumes no "
              "optical data),\nbut the canopy-sign arbitration and every external "
              "validation are not produced.")

    _phase("PHASE 3  phenology: departures, season integral, cleared fraction")
    phen, drift = phenology.run(work)
    phen.to_csv(os.path.join(work, "farm_phenology.csv"), index=False)
    phenology.report(phen, drift)

    if with_s2:
        # The sign the whole model rests on. It runs AFTER phenology because it scores the
        # departures phenology builds, and BEFORE crop_type because the labels use them.
        _phase("CANOPY SIGN  pre-registered optical arbitration")
        import canopy_sign
        canopy_sign.report()

    _phase("PHASE 4  crop type, six dates")
    features = os.path.join(work, "farm_phenology.csv")
    res = crop_type.run(features)
    crops = res[0]
    crops.to_csv(os.path.join(work, "farm_crops.csv"), index=False)
    crop_type.report(features, *res)
    print("\nsensitivity of the cotton area to COTTON_NOV_DB:")
    print(crop_type.cotton_sensitivity(res[0], res[6]).to_string(index=False))

    if with_s2:
        _phase("SENTINEL-2 VALIDATION  against the labels it never entered")
        import s2_ndvi
        ndvi = pd.read_csv(os.path.join(work, "farm_ndvi.csv"))
        joined = crops.merge(ndvi, on="farm_id", how="left")
        joined.to_csv(os.path.join(work, "farm_joined.csv"), index=False)
        s2_ndvi.report_validation(joined)

    _phase("PHASE 5  season context and the reference yield")
    season_context.report(work)

    _phase("PHASE 6  the forecast")
    fc = yield_forecast.forecast(crops)
    fc.to_csv(os.path.join(work, "farm_forecast_raw.csv"), index=False)
    yield_forecast.report(fc)
    yield_forecast.report_label_sensitivity(crops)
    # The one constant in this model that had a justification and no sweep, until an audit
    # pointed out that is exactly what Round 2 was criticised for. See judge_report.md 4.6.
    yield_forecast.report_accum_span(crops)
    # Four sources priced by re-running the chain under each. Called here rather than left
    # in `__main__` for the same reason every other `report()` is.
    yield_forecast.report_uncertainty(crops, work)

    if with_s2:
        _phase("BACK-TEST  fit on T1-T4, predict the withheld 12 November pass")
        bt = backtest.frame()
        backtest.report(bt)
        # The headline back-test is one point. This is the same experiment at every split
        # the six dates support, and it contradicted its own pre-registration.
        backtest.report_horizons(bt)

        _phase("VALIDATION  reserved optical, look-direction control, spatial coherence")
        ndvi = pd.read_csv(os.path.join(work, "farm_ndvi.csv"))
        validate.report(fc.merge(ndvi, on="farm_id", how="left"))

        # An independent instrument, used as a witness and never as a feature. It runs
        # AFTER the forecast on purpose: everything above has already been computed, so if
        # a column from here ever reached the model the village total would move and the
        # `test_s1_audit_is_not_imported` gate would not be the only thing that noticed.
        _phase("SENTINEL-1 AUDIT  an independent C-band witness, validation only  [NETWORK]")
        import s1_audit
        s1_audit.report(work)

        # The ledger last, because it is the summary of everything above it. Printed from
        # here so `audit_writeup.py` can trace the write-up's "eight of thirteen" to a log
        # line rather than to a document that could drift away from the constant.
        _phase("PRE-REGISTRATION LEDGER")
        validate.report_ledger()

    _phase("PHASE 7  aggregation and the shipped tables")
    farms, village, zones = submit.run(os.path.join(work, "farm_forecast_raw.csv"))
    farms.to_csv(os.path.join(out_dir, "farm_forecast.csv"), index=False)
    village.to_csv(os.path.join(out_dir, "village_summary.csv"), index=False)
    zones.to_csv(os.path.join(out_dir, "zone_summary.csv"), index=False)
    submit.report(farms, village, zones)

    if make_figures:
        _phase("FIGURES")
        figures.run()
    print(f"\nDONE   peak RSS {_rss_mb():,.0f} MB")
    return fc


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--no-s2", action="store_true",
                    help="skip Sentinel-2 (no network); every external validation is lost")
    ap.add_argument("--no-figures", action="store_true")
    args = ap.parse_args()
    run(with_s2=not args.no_s2, make_figures=not args.no_figures)
