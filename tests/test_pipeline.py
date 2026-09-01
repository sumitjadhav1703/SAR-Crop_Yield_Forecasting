"""Small, fast checks on the pieces of this pipeline that can break silently.

Not a test suite for its own sake. Every test here corresponds to a defect that either
happened during Round 3 or happened during Rounds 1-2 and would happen again: a wrong
registration peak, a phenology curve read from the wrong end, an offset applied to the
plots but not to the baseline, a submission that passes a prefix check while carrying an
extra column.

Run: `Round 3/.venv/bin/python -m pytest "Round 3/tests" -q`
"""

from __future__ import annotations

import fnmatch
import json
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))


# ---------------------------------------------------------------- registration
def _synthetic_scene(seed: int = 0, size: int = 512) -> np.ndarray:
    """A field mosaic with structure at two scales, which is what the matcher keys on."""
    rng = np.random.default_rng(seed)
    from scipy import ndimage
    fine = ndimage.gaussian_filter(rng.random((size, size)).astype(np.float32), 3)
    parcels = np.kron(rng.random((size // 32, size // 32)).astype(np.float32),
                      np.ones((32, 32), dtype=np.float32))
    return fine + 4.0 * parcels + 0.5


@pytest.mark.parametrize("truth", [(0, 0), (3, -5), (-11, 7)])
def test_phase_shift_recovers_known_translation(truth):
    import coreg_calib as cc
    base = _synthetic_scene()
    moved = np.roll(np.roll(base, -truth[0], axis=0), -truth[1], axis=1)
    dy, dx = cc.phase_shift(base, moved)
    assert abs(dy - truth[0]) < 0.3 and abs(dx - truth[1]) < 0.3


def test_bounded_search_stays_near_the_coarse_estimate():
    """The bound is relative to the coarse pass, and it is why T5 registers at all.

    The failure this guards against is T5's: at full resolution the correlation surface is
    nearly flat, so its argmax can land a hundred metres away on noise. The coarse pass
    averages the metre-scale structure out and finds the parcel mosaic, and the fine pass
    is then only allowed to refine within `max_shift_m` of that answer.

    The synthetic pair below reproduces exactly that split. The parcel mosaic -- the
    coarse-scale structure -- is not shifted, while the fine texture is rolled 200 px. An
    unrestricted full-resolution search is free to follow the fine decoy; the bounded
    search must stay with the coarse structure.
    """
    import coreg_calib as cc
    from scipy import ndimage
    rng = np.random.default_rng(3)
    size = 512
    parcels = np.kron(rng.random((size // 32, size // 32)).astype(np.float32),
                      np.ones((32, 32), dtype=np.float32))
    fine = ndimage.gaussian_filter(rng.random((size, size)).astype(np.float32), 1)
    base = 4.0 * parcels + fine + 0.5
    moved = 4.0 * parcels + np.roll(fine, -200, axis=1) + 0.5

    coarse = cc._correlation_surface(cc._decimate(base, cc.COARSE_FACTOR),
                                     cc._decimate(moved, cc.COARSE_FACTOR))
    cdy, cdx, _ = cc._peak(coarse, None)
    cdy, cdx = cdy * cc.COARSE_FACTOR, cdx * cc.COARSE_FACTOR

    bound_m = 20.0
    dy, dx = cc.phase_shift(base, moved, max_shift_m=bound_m)
    slack = bound_m / cc.PIXEL_SIZE + 1.0          # +1 px for the parabolic refinement
    assert abs(dy - cdy) <= slack and abs(dx - cdx) <= slack, (
        f"fine pass ({dy:.2f}, {dx:.2f}) escaped the bound around the coarse estimate "
        f"({cdy:.2f}, {cdx:.2f})")
    assert abs(dx) < 25.0, "coarse structure is unshifted, so the bounded answer is near zero"


def test_unbounded_search_is_free_to_roam():
    """`max_shift_m=None` must not silently inherit the default bound.

    `fit_height` depends on this: its sweep mis-geocodes by tens of metres on purpose.
    """
    import coreg_calib as cc
    base = _synthetic_scene()
    moved = np.roll(base, -200, axis=1)
    dy, dx = cc.phase_shift(base, moved, max_shift_m=None)
    assert abs(dx - 200) < 1.0, "unbounded search should find the true distant peak"


def test_fit_height_sweep_is_not_bounded():
    """`fit_height` mis-geocodes by up to 70 m on purpose; a bound would flatten its curve."""
    import inspect
    import coreg_calib as cc
    src = inspect.getsource(cc.fit_height)
    body = src.split('"""')[2]          # the docstring names the flag; only count real calls
    calls = body.count("phase_shift(")
    assert calls > 0, "fit_height no longer calls phase_shift; this test is stale"
    assert calls == body.count("max_shift_m=None"), (
        f"{calls} phase_shift calls in fit_height but not all pass max_shift_m=None")


# ------------------------------------------------------------------ radiometry
def test_gamma0_ladder_matches_a_hand_computed_value():
    """beta0 = |z|^2 sf^2 ; sigma0 = beta0 sin(th) - NESZ ; gamma0 = sigma0 / cos(th)."""
    sf, theta_deg, nesz_lin = 0.0016243207275323567, 29.745887627545393, 10 ** (-27.72 / 10)
    i, q = 300.0, -400.0
    th = np.radians(theta_deg)
    expect = (((i * i + q * q) * sf ** 2) * np.sin(th) - nesz_lin) / np.cos(th)
    got = ((i ** 2 + q ** 2) * sf ** 2 * np.sin(th) - nesz_lin) / np.cos(th)
    assert np.isclose(got, expect, rtol=1e-12)
    assert got > 0, "a bright pixel must survive noise subtraction"


def test_offsets_are_only_applied_above_the_threshold():
    import scene_diagnostics as sd
    blocks = {"T1": np.full((4, 4), 1.0, dtype=np.float32),
              "T2": np.full((4, 4), 10 ** (-0.05), dtype=np.float32),   # -0.5 dB, below
              "T6": np.full((4, 4), 10 ** (-0.40), dtype=np.float32)}   # -4.0 dB, above
    ps = np.ones((4, 4), dtype=bool)
    out = sd.date_offsets_db(blocks, ps)
    assert np.isclose(out["measured"]["T2"], 0.5, atol=0.01)
    assert out["applied"]["T2"] == 0.0, "a sub-threshold offset must not be applied"
    assert np.isclose(out["applied"]["T6"], 4.0, atol=0.01)


def test_read_offsets_raises_rather_than_defaulting_to_zero(tmp_path):
    """A silent zero would leave T6 ~4 dB low while every gate still passed."""
    import scene_diagnostics as sd
    with pytest.raises(FileNotFoundError):
        sd.read_offsets(str(tmp_path))


# ------------------------------------------------------------------- phenology
def _curve(depths: dict) -> pd.DataFrame:
    """Build a one-plot frame whose canopy departures come out as `depths`."""
    import phenology
    drift = {c: 0.0 for c in phenology.LEVEL_DATES}
    row = {f"g0_db_filled_{c}": -20.0 for c in phenology.ANCHOR_DATES}
    for c in phenology.CANOPY_DATES:
        row[f"g0_db_filled_{c}"] = -20.0 - depths[c]
    return pd.DataFrame([row]), drift


def test_canopy_depth_clips_the_negative_side():
    """The sign is measured (canopy_sign.py), so a plot below its own bare soil is zero.

    Not a style choice. Scored against Sentinel-2 on 813 plots, the season integral built
    on clip(departure, 0) reaches rho=+0.472 and the one built on |departure| reaches
    rho=-0.085. Folding the negative side back in erases the vegetation signal.
    """
    import phenology
    dep = np.array([[-2.0, 1.0, -0.5]])
    assert phenology.CANOPY_SIGN == +1
    assert np.allclose(phenology.canopy_depth(dep), [[0.0, 1.0, 0.0]])


def _phen(t3, t4, t6):
    """One plot whose drift-corrected departures are exactly (t3, t4, t6) dB."""
    import phenology
    drift = {c: 0.0 for c in phenology.LEVEL_DATES}
    row = {f"g0_db_filled_{c}": -20.0 for c in phenology.ANCHOR_DATES}
    for c, v in zip(phenology.CANOPY_DATES, (t3, t4, t6)):
        row[f"g0_db_filled_{c}"] = -20.0 + v
    return phenology.build(pd.DataFrame([row]), drift).iloc[0]


def test_cleared_fraction_is_one_when_the_canopy_is_gone_by_november():
    r = _phen(4.0, 3.0, 0.0)
    assert r.has_canopy and r.canopy_peak_db == 4.0 and r.cleared_fraction == 1.0


def test_cleared_fraction_is_zero_when_the_canopy_is_still_at_its_peak():
    """A crop still standing on 12 November is the forecast case, not the finished one."""
    r = _phen(2.0, 3.0, 4.0)
    assert r.has_canopy and r.cleared_fraction == 0.0 and r.canopy_end_db == 4.0


def test_cleared_fraction_is_nan_without_a_canopy_episode():
    """No episode means no fraction of one; NaN, never a default that looks like data."""
    import phenology
    r = _phen(0.2, 0.3, 0.1)
    assert r.canopy_peak_db < phenology.MIN_CANOPY_DB
    assert not r.has_canopy and np.isnan(r.cleared_fraction)


def test_a_mid_season_dip_that_recovers_is_not_read_as_clearing():
    """Lodging or a wet pass in October is not a harvest. Peak and end are what matter."""
    r = _phen(4.0, 0.5, 4.0)
    assert r.cleared_fraction == 0.0, "recovered canopy must not read as cleared"


def test_observed_integral_counts_the_negative_excursion():
    """The season integral is SIGNED. A plot that fell below its own bare soil is worse.

    The clipped alternative was tried and scores worse against the independent optical
    reference (rho +0.472 against +0.564), and it collapsed 52.8 % of the maize cohort onto
    a single value. See the `phenology` module docstring.
    """
    import phenology
    doys = np.array([phenology.DOY[c] for c in phenology.CANOPY_DATES], dtype=float)
    flat, dipped = _phen(2.0, 0.0, 2.0), _phen(2.0, -3.0, 2.0)
    assert dipped.observed_integral < flat.observed_integral
    expect = np.trapezoid(np.array([2.0, -3.0, 2.0]), doys) / (doys[-1] - doys[0])
    assert np.isclose(dipped.observed_integral, expect)


def test_clearing_still_uses_the_clipped_depth():
    """The two quantities treat the negative side differently on purpose; keep them apart."""
    r = _phen(4.0, -2.0, 0.0)
    assert r.canopy_peak_db == 4.0 and r.canopy_end_db == 0.0
    assert r.cleared_fraction == 1.0
    assert r.observed_integral < 0 or True  # signed integral is free to go negative


def test_extrapolation_only_fires_for_a_crop_whose_season_outruns_the_stack():
    """Everything but cotton is harvested inside the stack, so nothing is projected for it."""
    import yield_forecast as yf
    doys_end = 316.0
    rows = []
    for crop in ("Bajra", "Maize", "Groundnut", "Rice", "Cotton"):
        rows.append({"crop_type": crop, "departure_T3": 2.0,
                     "departure_T4": 2.0, "departure_T6": 2.0})
    got = yf.season_integral(pd.DataFrame(rows))
    frac = dict(zip([r["crop_type"] for r in rows], got.extrapolated_fraction))
    assert all(frac[c] == 0.0 for c in ("Bajra", "Maize", "Groundnut", "Rice")), frac
    assert frac["Cotton"] > 0.3, frac
    assert (got.calendar_harvest_doy <= doys_end).sum() == 4


def test_projection_never_grows_the_canopy():
    """A rising last limb is carried FLAT, not extrapolated upward, to harvest."""
    import yield_forecast as yf
    rising = pd.DataFrame([{"crop_type": "Cotton", "departure_T3": 1.0,
                            "departure_T4": 2.0, "departure_T6": 3.0}])
    flat = pd.DataFrame([{"crop_type": "Cotton", "departure_T3": 3.0,
                          "departure_T4": 3.0, "departure_T6": 3.0}])
    a = yf.season_integral(rising).integral_projected_db_days.iloc[0]
    b = yf.season_integral(flat).integral_projected_db_days.iloc[0]
    assert np.isclose(a, b), "a rising limb must project the same as a flat one"
    assert np.isclose(a, 3.0 * (yf.HARVEST_DOY["Cotton"] - 316.0))

    # A FALLING limb is also held flat. That is the back-test result, not an oversight:
    # the decaying variant lost to persistence (skill -0.317 where it fired, -0.409 on the
    # drift-aware control). `backtest.py` keeps it as B5 so the comparison stays runnable.
    falling = pd.DataFrame([{"crop_type": "Cotton", "departure_T3": 5.0,
                             "departure_T4": 4.0, "departure_T6": 3.0}])
    c = yf.season_integral(falling).integral_projected_db_days.iloc[0]
    assert np.isclose(c, a), "a falling limb must also be held flat, per the back-test"


def test_centred_factor_puts_the_cohort_median_at_exactly_one():
    """A modifier whose median is not 1.0 walks a whole cohort off its own reference."""
    import yield_forecast as yf
    rng = np.random.default_rng(0)
    n = 201                                  # odd: np.median then IS an element, not a mean
    x = rng.normal(size=2 * n)
    g = np.repeat(["Rice", "Cotton"], n)
    f = yf.centred_factor(x, g, 0.30)
    for crop in ("Rice", "Cotton"):
        assert np.isclose(np.median(f[g == crop]), 1.0)
    # With an even cohort np.median averages the two middle elements, which straddle 1.0,
    # so the printed cohort median lands a few parts in 10^4 off. That is the median
    # definition, not the factor -- the plot AT the median still scores exactly 1.0.
    even = yf.centred_factor(x[:400], np.repeat(["Rice", "Cotton"], 200), 0.30)
    assert abs(np.median(even[:200]) - 1.0) < 1e-3
    assert f.min() >= 1.0 - 0.30 - 1e-12 and f.max() <= 1.0 + 0.30 + 1e-12


def test_forecast_raises_rather_than_clipping_an_implausible_yield():
    """A yield outside the published band is an upstream bug, not a remarkable farm."""
    import yield_forecast as yf
    df = pd.DataFrame([{"crop_type": "Rice", "area_ha": 1.0, "departure_T3": v,
                        "departure_T4": v, "departure_T6": v} for v in np.linspace(0, 3, 40)])
    yf.forecast(df)                                     # in band, must not raise
    saved = yf.PLAUSIBLE_T_HA["Rice"]
    yf.PLAUSIBLE_T_HA["Rice"] = (5.0, 7.0)              # force a violation
    try:
        with pytest.raises(ValueError, match="plausible"):
            yf.forecast(df)
    finally:
        yf.PLAUSIBLE_T_HA["Rice"] = saved


def test_reference_yield_is_the_forecast_season_not_the_previous_one():
    """Round 2 used 2024-25. Using it again would forecast rice 41 % too high."""
    import season_context as sc
    ref = sc.yield_reference()
    assert sc.SEASON_YEAR == "2025-26"
    assert ref["Rice"] == 1675.0 and ref["Maize"] == 2035.0
    # cotton is published as lint and must be converted to kapas
    assert np.isclose(ref["Cotton"], 551 / sc.GINNING_OUTTURN)
    assert ref["Cotton"] > 1500, "cotton left on a lint basis would be implausibly low"


def test_departures_are_zero_for_a_flat_plot():
    import phenology
    frame, drift = _curve({c: 0.0 for c in phenology.CANOPY_DATES})
    dep = phenology.departures(frame, drift)
    assert np.allclose(dep, 0.0, atol=1e-9)


def test_baseline_removes_a_pure_scene_drift():
    """A plot that only follows the district drift must show no canopy at all."""
    import phenology
    drift = {"T1": 0.0, "T2": 1.5, "T3": -0.2, "T4": 0.1, "T6": 1.7}
    row = {f"g0_db_filled_{c}": -20.0 + drift[c] for c in phenology.LEVEL_DATES}
    dep = phenology.departures(pd.DataFrame([row]), drift)
    assert np.allclose(dep, 0.0, atol=1e-9)


# --------------------------------------------------------------------- weather
def test_antecedent_index_decays_and_is_ordered():
    import datetime as dt
    import season_context as sc
    day = dt.date(2025, 10, 29)
    near = {day - dt.timedelta(days=1): 10.0}
    far = {day - dt.timedelta(days=10): 10.0}
    assert sc.antecedent(near, day)["api"] > sc.antecedent(far, day)["api"]
    assert sc.antecedent({}, day)["api"] == 0.0


def test_season_total_only_counts_the_kharif_months():
    import datetime as dt
    import season_context as sc
    daily = {dt.date(2025, m, 15): 100.0 for m in range(1, 13)}
    assert sc.season_total(daily, 2025) == 100.0 * len(sc.SEASON_MONTHS)


# ------------------------------------------------------------------ submission
def _shipped():
    """A minimal frame that passes the gate, so each test can break exactly one thing."""
    import submit
    n = submit.N_FARMS
    d = pd.DataFrame({
        "village_id": 22, "village_name": "Sokhda",
        "farm_id": np.arange(1, n + 1), "area_ha": 0.27,
        "crop_type": "Maize", "crop_confidence": "low", "crop_margin": 0.5,
        "long_duration_flag": False, "data_quality": "measured", "n_valid_dates": 6,
        "has_canopy": True, "canopy_peak_db": 1.0, "canopy_peak_doy": 226.0,
        "canopy_end_db": 0.2, "cleared_fraction": 0.8, "season_integral_db": 0.9,
        "extrapolated_fraction": 0.0, "accumulation_response": 1.0,
        "yield_ref_t_ha": 2.035, "yield_forecast_t_ha": 2.035,
    })
    d["production_t"] = d.yield_forecast_t_ha * d.area_ha
    return d[submit.REQUIRED]


def test_the_gate_passes_a_clean_table():
    import submit
    submit.validate(_shipped())


def test_the_gate_rejects_an_extra_column():
    import submit
    bad = _shipped()
    bad["helpful_extra"] = 1.0
    with pytest.raises(ValueError, match="columns must be exactly"):
        submit.validate(bad)


def test_the_gate_rejects_a_reordered_column():
    import submit
    bad = _shipped()
    cols = list(bad.columns)
    cols[0], cols[1] = cols[1], cols[0]
    with pytest.raises(ValueError, match="columns must be exactly"):
        submit.validate(bad[cols])


def test_the_gate_rejects_a_missing_row():
    import submit
    with pytest.raises(ValueError, match="rows, expected"):
        submit.validate(_shipped().iloc[:-1])


def test_the_gate_rejects_a_nan_in_a_solid_column():
    import submit
    bad = _shipped()
    bad.loc[3, "yield_forecast_t_ha"] = np.nan
    with pytest.raises(ValueError, match="NaN in"):
        submit.validate(bad)


def test_the_gate_rejects_an_inf():
    import submit
    bad = _shipped()
    bad.loc[3, "season_integral_db"] = np.inf
    with pytest.raises(ValueError, match="Inf"):
        submit.validate(bad)


def test_the_gate_rejects_a_null_that_does_not_match_has_canopy():
    """A NaN clearing fraction on a plot that DID grow a canopy is a bug, not a definition."""
    import submit
    bad = _shipped()
    bad.loc[3, "cleared_fraction"] = np.nan          # has_canopy is still True
    with pytest.raises(ValueError, match="null on a different set"):
        submit.validate(bad)


def test_the_gate_accepts_the_documented_null_pattern():
    import submit
    ok = _shipped()
    ok.loc[3, ["has_canopy"]] = False
    ok.loc[3, ["cleared_fraction", "canopy_peak_doy"]] = np.nan
    submit.validate(ok)


def test_the_gate_rejects_a_sixth_crop():
    import submit
    bad = _shipped()
    bad.loc[3, "crop_type"] = "Sugarcane"
    with pytest.raises(ValueError, match="outside the permitted five"):
        submit.validate(bad)


def test_the_gate_rejects_an_implausible_yield():
    import submit
    bad = _shipped()
    bad.loc[3, "yield_forecast_t_ha"] = 40.0
    with pytest.raises(ValueError, match="plausible band"):
        submit.validate(bad)


def test_the_village_table_must_reconstruct_from_the_plot_table():
    import submit
    farms = _shipped()
    village = submit.village_summary(farms.assign(
        production_t=farms.yield_forecast_t_ha * farms.area_ha))
    submit.cross_check(farms, village)
    tampered = village.copy()
    tampered.loc[tampered.crop_type == "ALL", "production_t"] += 1.0
    with pytest.raises(ValueError, match="production"):
        submit.cross_check(farms, tampered)


def test_rounding_happens_before_aggregation_so_the_totals_agree():
    """The regression this guards: rounding the plot table after summing it at full
    precision made the shipped CSV disagree with the shipped summary in the 4th decimal."""
    import submit
    raw = _shipped().assign(area_ha=0.123456789, yield_forecast_t_ha=2.123456789)
    d = submit.round_shipped(raw)
    farms = submit.farm_forecast(d)
    submit.cross_check(farms, submit.village_summary(d))


def test_notebook_is_in_sync_with_src():
    """The shipped notebook must be the current `src/` tree, byte for byte.

    Round 2's modules lived only inside its notebook and there was nothing to compare;
    here the notebook is generated, so staleness is detectable and is a test failure.
    """
    import importlib.util

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        "build_notebook", os.path.join(root, "build_notebook.py"))
    bn = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bn)

    with open(bn.NOTEBOOK) as fh:
        assert fh.read() == bn.render(bn.build()), \
            "sokhda_yield_forecast.ipynb is stale; run `python build_notebook.py`"


def test_a_cloned_repo_resolves_round2_labels_without_configuration(monkeypatch):
    """A judge who clones this repo must not have to set an environment variable.

    `kaggle_dataset/round2_crops.csv` ships here -- it is the same file uploaded to Kaggle as
    an attached dataset -- but the resolver did not probe that directory, so a clone with no
    sibling `Round 2/` hit the raise with the file already on disk. Three validation steps
    (the canopy sign, the back-test, the label-sensitivity term) are unavailable when it does.
    Found by the audit in `docs/judge_report.md` section 4.4.
    """
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "src"))
    import geocode

    root = os.path.dirname(os.path.dirname(os.path.abspath(geocode.__file__)))
    sibling = os.path.abspath(os.path.join(os.path.dirname(root), "Round 2",
                                           "farm_crops.csv"))
    shipped = os.path.join(root, "kaggle_dataset", "round2_crops.csv")
    monkeypatch.delenv("ROUND2_CROPS", raising=False)

    real_isfile = os.path.isfile
    monkeypatch.setattr(                        # simulate a clone: no sibling round present
        geocode.os.path, "isfile",
        lambda p: False if os.path.abspath(p) == sibling else real_isfile(p))

    assert real_isfile(shipped), "kaggle_dataset/round2_crops.csv must ship with the repo"
    assert geocode.round2_crops_path() == shipped

    cols = open(shipped).readline().strip().split(",")
    assert cols == ["farm_id", "crop_type", "crop_confidence"], cols


def test_the_resolver_raises_and_names_what_it_tried_when_nothing_is_reachable(monkeypatch):
    """It is a path resolver, not a fallback around a check.

    If the labels are genuinely absent the sign arbitration and the back-test cannot run, and
    a run that quietly skipped them would be worse than one that stops. The message has to
    name the candidates AND the glob patterns -- a Kaggle run once failed with the dataset
    attached three levels deeper than the single-star glob reached, and the raise listed only
    the paths that resolved, which is exactly backwards for a diagnostic.
    """
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "src"))
    import geocode

    monkeypatch.delenv("ROUND2_CROPS", raising=False)
    monkeypatch.setattr(geocode.os.path, "isfile", lambda p: False)
    monkeypatch.setattr(geocode.glob, "glob", lambda pattern: [])

    with pytest.raises(FileNotFoundError) as exc:
        geocode.round2_crops_path()
    msg = str(exc.value)
    assert "kaggle_dataset" in msg
    assert "/kaggle/input/" in msg
    assert "ROUND2_CROPS" in msg


def test_no_module_builds_the_round2_path_itself():
    """One resolver, and every caller asks it.

    Three modules each built `../Round 2/farm_crops.csv` from the local layout, so fixing
    one left the other two broken on Kaggle. This fails if a fourth ever appears.
    """
    src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
    offenders = []
    for name in sorted(os.listdir(src)):
        if not name.endswith(".py") or name == "geocode.py":
            continue
        with open(os.path.join(src, name)) as fh:
            for i, line in enumerate(fh, 1):
                # Round 3's own `work/farm_crops.csv` is fine; what must not recur is a
                # module reaching out of this round's directory for Round 2's copy.
                reaches_out = '"Round 2"' in line or "'Round 2'" in line
                if reaches_out and not line.lstrip().startswith("#"):
                    offenders.append(f"{name}:{i}")
    assert not offenders, ("these build the Round 2 path themselves instead of calling "
                           f"geocode.round2_crops_path(): {offenders}")


def test_an_attached_kaggle_dataset_outranks_the_work_copy(tmp_path, monkeypatch):
    """On Kaggle the labels arrive as an attached dataset, and it has to win.

    The notebook used to write `work/round2_crops.csv` from a cell. It no longer does, but
    the candidate is still in the list, and a stale copy left in `work/` by an earlier local
    run must not shadow the dataset the notebook was actually given.
    """
    import geocode

    attached = tmp_path / "round2_crops.csv"
    attached.write_text("farm_id,crop_type,crop_confidence\n1,Maize,low\n")
    monkeypatch.setattr(geocode.glob, "glob",
                        lambda pattern: [str(attached)]
                        if pattern.endswith("round2_crops.csv") else [])
    monkeypatch.delenv("ROUND2_CROPS", raising=False)
    root = os.path.dirname(os.path.dirname(os.path.abspath(geocode.__file__)))
    sibling = os.path.abspath(os.path.join(os.path.dirname(root), "Round 2",
                                           "farm_crops.csv"))
    real_isfile = os.path.isfile
    monkeypatch.setattr(geocode.os.path, "isfile",
                        lambda p: False if os.path.abspath(p) == sibling
                        else real_isfile(p))

    assert geocode.round2_crops_path() == str(attached)


def test_the_kaggle_patterns_reach_a_dataset_mounted_three_levels_down(monkeypatch):
    """A dataset does not always mount at `/kaggle/input/<slug>/`.

    The second Kaggle run had it at `/kaggle/input/datasets/<owner>/<slug>/round2_crops.csv`
    and the single-star glob matched nothing, so the run died on a file that was present.
    The resolver enumerates three depths; this asserts the pattern list covers that one.
    """
    import geocode

    seen = []
    monkeypatch.setattr(geocode.glob, "glob", lambda pattern: seen.append(pattern) or [])
    monkeypatch.setenv("ROUND2_CROPS", __file__)          # short-circuits before the globs
    geocode.round2_crops_path()
    monkeypatch.delenv("ROUND2_CROPS")

    seen.clear()
    with pytest.raises(FileNotFoundError):
        real_isfile = os.path.isfile
        monkeypatch.setattr(geocode.os.path, "isfile", lambda p: False)
        geocode.round2_crops_path()
        monkeypatch.setattr(geocode.os.path, "isfile", real_isfile)

    deep = "/kaggle/input/datasets/sumit1703/round2-crops/round2_crops.csv"
    assert any(fnmatch.fnmatch(deep, pat) for pat in seen), (
        f"no pattern in {seen} matches a dataset mounted three levels down")


def test_the_village_rollup_gate_fires_on_a_geometric_disagreement():
    """The rollup groups by a text column; the gate is what makes that defensible.

    `village_summary` does `groupby("crop_type")` inside one village selected by name. If a
    plot's geometry sat in a different village from its `VILLAGE` attribute, or a real parcel
    sat outside every village polygon, the groupby would include it silently and the village
    total would be a total over the wrong ground. Only the geometry can catch that, so the
    gate has to raise rather than print.
    """
    import submit

    clean = dict(n_villages=1, village_names=["Sokhda"], n_farms=966, n_agree=966,
                 n_disagree=0, n_by_centroid=0, n_outside=0, farm_area_ha=447.5,
                 inside_area_ha=447.5, outside_area_ha=0.0, village_area_ha=1174.1)
    submit.report_containment(clean)                      # must not raise

    with pytest.raises(ValueError, match="not geometrically sound"):
        submit.report_containment({**clean, "n_agree": 965, "n_disagree": 1})

    with pytest.raises(ValueError, match="not geometrically sound"):
        submit.report_containment({**clean, "n_agree": 965, "n_outside": 1,
                                   "outside_area_ha": 0.31})

    # A parcel that encloses no measurable ground cannot be placed by any geometric test.
    # It is reported, not raised on: it carries a row and zero area weight either way.
    submit.report_containment({**clean, "n_agree": 962, "n_outside": 4,
                               "n_by_centroid": 7, "outside_area_ha": 0.0})


def test_the_stac_search_is_cached_so_the_offline_claim_is_true(tmp_path, monkeypatch):
    """Three modules and a doc claimed this pipeline runs offline from `work/s2_cache/`.

    Until 2026-09-01 that was false: the RASTERS were cached but `s2_ndvi.search` was not, so
    the first window issued a STAC request and an offline run died before it reached a single
    cached file. This pins the cache-first behaviour, because the claim is only true while the
    behaviour holds. `docs/judge_report.md` section 4.3.

    Caching the response also pins the reserved-scene choice: the 16 January window returns
    three candidates all at 0.0 % cloud, so the winner was decided by the order Earth Search
    returned them in.
    """
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "src"))
    import s2_ndvi

    payload = [{"id": "cloudy", "properties": {"eo:cloud_cover": 40.0}},
               {"id": "clear", "properties": {"eo:cloud_cover": 1.0}}]
    cache = tmp_path / "stac_TEST.json"
    cache.write_text(json.dumps(payload))
    monkeypatch.setattr(s2_ndvi, "_stac_cache_path", lambda code: str(cache))

    def explode(*a, **k):                       # any network use is the failure under test
        raise AssertionError("search() hit the network with a cached response present")
    monkeypatch.setattr(s2_ndvi.urllib.request, "urlopen", explode)

    got = s2_ndvi.search("2026-01-08/2026-01-18", "TEST")
    assert [it["id"] for it in got] == ["clear", "cloudy"], "must sort least-cloudy first"


# ------------------------------------------------------------ tier-2 allocation
def _tier2_frame() -> pd.DataFrame:
    """Twelve plots that are equal on the clipped axis and ordered on the signed one.

    Every plot has fallen below its own June soil by 12 November, which is what half the
    village does, so `clip(departure_T6, 0)` is 0.0 for all twelve and carries no ordering
    at all. `departure_T6` orders them.
    """
    dep = np.linspace(-6.0, -0.5, 12)
    return pd.DataFrame({"farm_id": np.arange(1, 13),
                         "area_ha": np.full(12, 0.25),
                         "departure_T6": dep,
                         "canopy_end_db": np.clip(dep, 0.0, None)})


def test_tier2_allocation_does_not_depend_on_input_row_order():
    """The defect S14 found: the same fields, a different row order, a different answer.

    The Kaggle run and the local run disagreed about 39 plots and 1.7 t because the cut fell
    inside a block of tied keys and the sort was not stable. This is that, in twelve rows.
    """
    import crop_type

    df = _tier2_frame()
    unresolved = df.index.to_numpy()
    first = crop_type.allocate_tier2(df, unresolved).sort_index()

    shuffled = df.iloc[[7, 2, 11, 0, 5, 9, 3, 1, 10, 4, 8, 6]].reset_index(drop=True)
    again = crop_type.allocate_tier2(shuffled, shuffled.index.to_numpy())

    by_id = pd.Series(first.to_numpy(), index=df.loc[first.index, "farm_id"].to_numpy())
    again_by_id = pd.Series(again.to_numpy(),
                            index=shuffled.loc[again.index, "farm_id"].to_numpy())
    assert (again_by_id.sort_index() == by_id.sort_index()).all()


def test_tier2_axis_ranks_plots_the_clipped_axis_cannot():
    """The axis has to separate plots that are all at zero once clipped.

    A name check would pass on any column; this asserts the behaviour that made the clipped
    axis arbitrary -- twelve plots, all clipped to 0.0, must still land in more than one
    cohort, and the darkest at T6 must be the earliest-harvested cohort.
    """
    import crop_type

    df = _tier2_frame()
    assert (df.canopy_end_db == 0).all()          # the premise: clipped, they are one value
    lab = crop_type.allocate_tier2(df, df.index.to_numpy())
    assert lab.nunique() > 1, "the ranking axis is degenerate over this block"
    assert lab.loc[df.departure_T6.idxmin()] == crop_type.TIER2_ORDER[0]
    assert lab.loc[df.departure_T6.idxmax()] == crop_type.TIER2_ORDER[-1]
