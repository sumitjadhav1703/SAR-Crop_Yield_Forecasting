"""What is different between the six acquisitions, and how much of it is not the crop.

This module measures. It deliberately does not correct.

Round 3 adds two acquisitions to Round 2's stack and both carry confounds that Round 2
never had to face: T5 is right-looking, pre-dawn and post-rain, and T6 is the first pass
after most of the kharif harvest. Every one of those changes backscatter by the same order
as the seasonal canopy signal the model is trying to read. The temptation is to build a
normalisation that flattens them away. That would be wrong twice over -- it would remove
real harvest signal along with the artefact, and it would hide the size of the problem
behind a correction nobody can audit.

So the job here is to put numbers on the confounds and hand them to the modules that have
to decide what to do. `feature_audit` consumes them as controls; `phenology` decides which
dates it trusts for level and which only for timing.

THE THREE MEASUREMENTS

1. PERSISTENT SCATTERERS.  Buildings, walls, metal roofs -- targets whose backscatter has
   nothing to do with the crop calendar. If the radiometry is consistent across dates,
   these are the pixels that show it.

   Selection has to avoid two traps. Thresholding a single single-look date selects
   speckle maxima, not structures: taking the brightest 0.01 % of T1 and reading the same
   pixels elsewhere gives a median 17-25 dB lower on every other date, because a
   single-look speckle maximum has no reason to recur. And selecting on all six dates
   biases the result, because requiring `min(all dates) > threshold` pushes the dimmest
   date up at the selection boundary by construction. So: select on one subset of dates,
   report on the dates held out of the selection.

2. THE LOOK-DIRECTION EFFECT.  A wall-ground dihedral returns energy to the side that
   forms the corner. Reverse the illumination and the same structure goes dark while its
   opposite face lights up. This is the cleanest test available of whether T5 can be
   compared with the rest at face value, and it is a categorical result rather than a
   calibration offset.

3. THE SCENE-LEVEL TWO-FACTOR STORY.  The AOI median over the pixels valid on all six
   dates is not a calibration statistic -- it is vegetation plus surface moisture, and it
   is *supposed* to move. Reported next to the antecedent rainfall from `season_context`
   so a reader can see which factor is driving which date.
"""

from __future__ import annotations

import json
import os

import numpy as np
from osgeo import gdal

from gates import read_aoi
from geocode import SCENE_GEOMETRY, SCENES

gdal.UseExceptions()

# Dates illuminated from the same side. T5 is the only exception in the stack and it is
# held out of every selection so that it is measured rather than assumed.
LEFT_LOOKING = [c for _, c, _ in SCENES if SCENE_GEOMETRY[c]["looking"] == "left"]
RIGHT_LOOKING = [c for _, c, _ in SCENES if SCENE_GEOMETRY[c]["looking"] == "right"]

# Dates used to CHOOSE the persistent scatterers, and dates kept back to score them on.
# The split is by acquisition order rather than by anything measured, so it cannot be
# tuned to make the answer come out well.
PS_SELECT = ["T1", "T2", "T3"]
PS_HOLDOUT = ["T4", "T6"]

# Persistent scatterers are selected on BLOCK-AVERAGED power, not on single pixels.
#
# At 1 m single-look the brightest 0.01 % of pixels are speckle maxima: the per-pixel
# difference between two dates on that population has an inter-quartile range of 8.4 dB
# and the two dates correlate at only 0.61. Averaging to 8 m first drops the IQR to
# 3.8 dB and lifts the correlation to 0.78, because a building is a cluster and a speckle
# maximum is not. Same multi-scale idea that fixed the registration.
PS_BLOCK_M = 8
PS_PERCENTILE = 99.9

# How far apart the held-out left-looking dates may sit on those targets before the
# radiometry is in question. Applied AFTER the offsets below are removed, which is the
# only order in which the number means anything.
PS_SPREAD_MAX_DB = 1.5

# The date every other date's radiometry is expressed relative to. T1 is the registration
# master as well, so one date anchors both geometry and radiometry.
RADIOMETRIC_MASTER = "T1"

# Only offsets larger than this are applied. Everything smaller is measured, printed, and
# left alone.
#
# The estimator reads built-up blocks, and built-up blocks are not perfectly inert: 8 m of
# ground around a wall contains soil, and soil responds to rain. T2 is the monsoon-onset
# pass with 87 mm of antecedent rain and it returns an offset of -1.70 dB -- plausibly
# instrumental, but equally plausibly the wet ground the buildings are standing on.
# Removing it would scrub a real soil-moisture signal out of the one date that most
# clearly carries it, to fix a bias that may not exist.
#
# T6 is a different case and the difference is measurable, not rhetorical. Its offset is
# +4.28 dB; it holds between +3.71 and +4.78 dB as the selection is tightened from the top
# 10 % of blocks to the top 0.01 %; it holds at +3.6 to +4.8 dB in three of four AOI
# quadrants; and its residual against the master is flat across the whole 39 dB brightness
# range of the scene. No surface process does that -- harvest darkens fields and leaves
# buildings alone, rain brightens soil and leaves roofs alone. A scene-wide radiometric
# bias is the only mechanism whose signature is flat.
#
# 2.0 dB sits well above the largest offset that the wetting of built-up surroundings
# could plausibly produce and far below T6's, so on this stack the rule selects T6 and
# nothing else. It is stated as a rule rather than as "correct T6" so that a future stack
# is handled by the same reasoning.
OFFSET_APPLY_MIN_DB = 2.0


def paths(work: str) -> dict:
    """Geocoded product per date code. Built from `SCENES`, never globbed -- the 20250619
    folder holds a byte-identical duplicate of the T1 SLC and a glob loads June 6 twice."""
    return {code: os.path.join(work, f"gamma0_lin_{code}_{date}.tif")
            for _, code, date in SCENES}


def load_stack(work: str) -> dict:
    return {code: read_aoi(path) for code, path in paths(work).items()}


def covalid_mask(stack: dict) -> np.ndarray:
    """Pixels the radar actually measured on every one of the six dates.

    Any cross-date comparison has to be made on one common set of pixels, or it is partly
    a comparison of swath footprints.
    """
    return np.logical_and.reduce([stack[c] > 0 for c in stack])


def block_mean(arr: np.ndarray, valid: np.ndarray, factor: int = PS_BLOCK_M) -> tuple:
    """Block-average linear power, and flag the blocks that are entirely valid.

    Averaging happens in power, never in dB -- the same rule that makes `geocode` warp
    with `average` on linear gamma0 and convert afterwards.
    """
    ny = (arr.shape[0] // factor) * factor
    nx = (arr.shape[1] // factor) * factor
    shape = (ny // factor, factor, nx // factor, factor)
    v = valid[:ny, :nx].astype(np.float32)
    total = (arr[:ny, :nx].astype(np.float32) * v).reshape(shape).sum(axis=(1, 3))
    count = v.reshape(shape).sum(axis=(1, 3))
    return (np.divide(total, count, out=np.zeros_like(total), where=count > 0),
            count == factor * factor)


def blocked_stack(stack: dict, mask: np.ndarray) -> tuple:
    """Every date block-averaged onto one grid, plus the blocks valid on all of them."""
    blocks, full = {}, None
    for code, arr in stack.items():
        blocks[code], ok = block_mean(arr, mask)
        full = ok if full is None else (full & ok)
    return blocks, full


def persistent_scatterers(blocks: dict, full: np.ndarray) -> np.ndarray:
    """Blocks bright on every date in `PS_SELECT`. `PS_HOLDOUT` and T5 are not consulted."""
    sel = np.minimum.reduce([blocks[c] for c in PS_SELECT])
    sel = np.where(full, sel, 0.0)
    thr = np.percentile(sel[sel > 0], PS_PERCENTILE)
    return sel > thr


def _median_db(values: np.ndarray) -> float:
    v = values[values > 0]
    return float(10.0 * np.log10(np.median(v))) if v.size else float("nan")


def date_offsets_db(blocks: dict, ps: np.ndarray) -> dict:
    """Per-date radiometric offset, dB, to be ADDED to bring a date onto the master's scale.

    Estimated as the median difference on built-up blocks, which have no crop calendar.
    Positive means the date reads low and must be raised.

    WHY THIS IS NEEDED AT ALL. Capella ship these products as `calibration: full` with a
    per-scene `scale_factor`, so in principle no such correction should be required. In
    practice T6 sits ~3 dB below T4 -- and it does so at EVERY level of brightness, from
    the darkest decile of the AOI to the built-up tail, drifting only ~1.5 dB across a
    39 dB range. A seasonal effect cannot do that: harvest darkens fields and leaves
    buildings alone. A scene-wide radiometric bias is the only explanation that fits the
    shape of the residual, and the raw SLC medians agree -- T6's uncalibrated intensity
    over comparable ground is ~3 dB under T4's, and the calibration only gives back 1.2 dB
    of it.

    WHY T5 IS EXCLUDED. Its residual against T4 is not flat: it runs -3.3 dB in the
    darkest decile and +9.9 dB in the brightest. Two mechanisms with opposite signs --
    63 mm of rain in the three days before the pass brightens rough dark surfaces, and the
    reversed look direction extinguishes the wall-ground dihedrals that make built-up
    areas bright. No single constant can undo that, and pretending one can would be worse
    than leaving the date alone. T5's LEVEL is therefore never used; its TIMING is.
    """
    master_db = 10.0 * np.log10(np.maximum(blocks[RADIOMETRIC_MASTER][ps], 1e-12))
    measured, applied = {}, {}
    for code in blocks:
        if code in RIGHT_LOOKING:
            continue
        code_db = 10.0 * np.log10(np.maximum(blocks[code][ps], 1e-12))
        value = float(np.median(master_db - code_db))
        measured[code] = value
        applied[code] = value if abs(value) >= OFFSET_APPLY_MIN_DB else 0.0
    return {"measured": measured, "applied": applied}


def brightness_profile(blocks: dict, full: np.ndarray, code: str,
                       reference: str = RADIOMETRIC_MASTER) -> list:
    """Median (reference - code) in dB, by decile of an independently-defined brightness.

    The deciles are cut on `min(PS_SELECT)`, so the axis is not defined by either of the
    dates being compared. This is the measurement that separates a scene-wide offset --
    flat across every decile -- from a surface change, which is not.
    """
    axis = 10.0 * np.log10(np.maximum(
        np.minimum.reduce([blocks[c] for c in PS_SELECT]), 1e-12))[full]
    a = 10.0 * np.log10(np.maximum(blocks[reference], 1e-12))[full]
    b = 10.0 * np.log10(np.maximum(blocks[code], 1e-12))[full]
    edges = np.percentile(axis, np.arange(0, 101, 10))
    out = []
    for i in range(10):
        lo, hi = edges[i], edges[i + 1]
        sel = (axis >= lo) & (axis <= hi if i == 9 else axis < hi)
        if sel.sum() >= 20:
            out.append((float(lo), float(hi), int(sel.sum()),
                        float(np.median(a[sel] - b[sel]))))
    return out


def measure(work: str) -> dict:
    stack = load_stack(work)
    mask = covalid_mask(stack)
    blocks, full = blocked_stack(stack, mask)
    ps = persistent_scatterers(blocks, full)

    ps_db = {code: _median_db(blocks[code][ps]) for code in blocks}
    aoi_db = {code: float(np.median(10.0 * np.log10(np.maximum(stack[code][mask], 1e-12))))
              for code in stack}
    off = date_offsets_db(blocks, ps)
    measured_off, offsets = off["measured"], off["applied"]

    corrected = {c: ps_db[c] + offsets[c] for c in offsets}
    holdout = [corrected[c] for c in PS_HOLDOUT]
    raw_holdout = [ps_db[c] for c in PS_HOLDOUT]
    result = {
        "covalid_fraction": float(mask.mean()),
        "n_ps": int(ps.sum()),
        "n_blocks": int(full.sum()),
        "ps_db": ps_db,
        "aoi_db": aoi_db,
        "offsets_db": offsets,
        "offsets_measured_db": measured_off,
        "ps_db_corrected": corrected,
        "ps_holdout_spread_db": float(max(holdout) - min(holdout)),
        "ps_holdout_spread_raw_db": float(max(raw_holdout) - min(raw_holdout)),
        "ps_left_min_db": min(ps_db[c] for c in LEFT_LOOKING),
        "ps_right_db": {c: ps_db[c] for c in RIGHT_LOOKING},
        "profiles": {c: brightness_profile(blocks, full, c)
                     for c in ("T6", "T5", "T4")},
    }
    result["look_penalty_db"] = {
        c: result["ps_left_min_db"] - ps_db[c] for c in RIGHT_LOOKING}
    del stack, blocks
    return result


def report(work: str, wetness: dict | None = None) -> dict:
    """Print the scene-difference table the write-up quotes."""
    m = measure(work)
    print(f"co-valid mask: {100 * m['covalid_fraction']:.1f} % of the AOI is measured on "
          f"all six dates. Every number below is computed on that mask only.")
    print(f"invariant targets: {m['n_ps']} of {m['n_blocks']} {PS_BLOCK_M} m blocks, the "
          f"top {100 - PS_PERCENTILE:.1f} % of min({', '.join(PS_SELECT)}).")
    print(f"{', '.join(PS_HOLDOUT)} and {', '.join(RIGHT_LOOKING)} take no part in the "
          f"selection, so they are scored on targets they did not help choose.")

    print("\n  code  look    incid   invariant dB   offset dB   corrected dB   AOI median"
          "   role")
    print(f"  (* = applied; offsets under {OFFSET_APPLY_MIN_DB:.1f} dB are measured, "
          f"printed and left alone)")
    for _folder, code, _date in SCENES:
        g = SCENE_GEOMETRY[code]
        role = ("selection" if code in PS_SELECT else
                "HELD OUT" if code in PS_HOLDOUT else "not consulted")
        off = m["offsets_db"].get(code)
        meas = m["offsets_measured_db"].get(code)
        offs = (f"{meas:+6.2f}{'*' if off else ' '}  " if meas is not None
                else "     —   ")
        corr = (f"{m['ps_db_corrected'][code]:+13.2f}" if off is not None
                else "            —")
        print(f"  {code}    {g['looking']:<6s}{g['incidence_deg']:5.1f}   "
              f"{m['ps_db'][code]:>12.2f}{offs}{corr}   {m['aoi_db'][code]:>10.2f}   {role}")

    spread_ok = m["ps_holdout_spread_db"] <= PS_SPREAD_MAX_DB
    print(f"\n  held-out left-looking dates: {m['ps_holdout_spread_raw_db']:.2f} dB apart "
          f"before the offsets, {m['ps_holdout_spread_db']:.2f} dB after "
          f"[{'PASS' if spread_ok else 'FAIL'}, tolerance {PS_SPREAD_MAX_DB:.1f} dB]")
    print("  That is the calibration statement, and it is made on targets with no crop "
          "calendar. The AOI median is NOT a calibration\n  statistic: it is vegetation "
          "and surface moisture, and it is supposed to move.")

    print("\n  is the residual a scene-wide offset or a surface change? "
          "median (T1 - date) by decile of min(T1,T2,T3):")
    print("    decile brightness dB      n      T6      T5      T4")
    prof = m["profiles"]
    for i in range(len(prof["T6"])):
        lo, hi, n, _ = prof["T6"][i]
        vals = [prof[c][i][3] for c in ("T6", "T5", "T4")]
        print(f"    {lo:8.1f}..{hi:7.1f} {n:8d}  " + "  ".join(f"{v:+6.2f}" for v in vals))
    print("    T6 is flat: the same deficit on the darkest fields and on the built-up "
          "tail. Harvest cannot do that -- it darkens\n    fields and leaves buildings "
          "alone -- so it is a scene-wide radiometric bias and a single constant removes "
          "it.")
    print("    T5 is not flat, and it changes sign. Rough dark surfaces read BRIGHTER "
          "(63 mm of rain in the three days before\n    the pass) while built-up reads "
          "far darker (the reversed look direction extinguishes the wall-ground "
          "dihedrals).\n    Two mechanisms with opposite signs: no constant can undo it, "
          "so T5's level is never used and only its timing is.")

    for code, penalty in m["look_penalty_db"].items():
        print(f"\n  {code} is {penalty:.1f} dB below the dimmest left-looking date on the "
              f"invariant targets.")

    if wetness is not None:
        print("\n  the AOI median against the two things that actually move it:")
        print("    code   AOI median dB   API14 mm   reading")
        notes = {
            "T1": "pre-monsoon, bare to sparse",
            "T2": "monsoon onset, wet soil, crop barely emerged",
            "T3": "mid-monsoon dry spell, full canopy",
            "T4": "post-monsoon, canopy senescing",
            "T5": "post-rain and pre-dawn, right-looking",
            "T6": "dry, and most of the crop is off the field",
        }
        for _folder, code, _date in SCENES:
            print(f"    {code}   {m['aoi_db'][code]:>13.2f}   {wetness[code]['api']:>8.1f}"
                  f"   {notes[code]}")
        print("    T2 is the brightest and the wettest. T3 is the driest pass in the "
              "stack and still sits 2.4 dB above T6, which is\n    drier only in soil -- "
              "the difference is the canopy T3 has and T6 does not.")

    m["ps_spread_pass"] = spread_ok
    return m


OFFSETS_FILENAME = "scene_offsets.json"


def offsets_path(work_root: str) -> str:
    return os.path.join(work_root, OFFSETS_FILENAME)


def write_offsets(work_root: str, result: dict) -> str:
    """Persist the offsets so the rest of the pipeline reads one measured set of numbers.

    Written by `report`, read by `farm_features`. `farm_features` raises if the file is
    absent rather than defaulting to zero: a silent zero would leave T6 4 dB low and every
    late-season feature wrong, and the run would look completely healthy.
    """
    path = offsets_path(work_root)
    os.makedirs(work_root, exist_ok=True)
    payload = {
        "offsets_db": result["offsets_db"],
        "offsets_measured_db": result["offsets_measured_db"],
        "apply_threshold_db": OFFSET_APPLY_MIN_DB,
        "no_offset": sorted(RIGHT_LOOKING),
        "master": RADIOMETRIC_MASTER,
        "n_invariant_blocks": result["n_ps"],
        "block_m": PS_BLOCK_M,
        "percentile": PS_PERCENTILE,
        "select_dates": PS_SELECT,
        "holdout_dates": PS_HOLDOUT,
        "holdout_spread_raw_db": result["ps_holdout_spread_raw_db"],
        "holdout_spread_corrected_db": result["ps_holdout_spread_db"],
    }
    with open(path, "w") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
    return path


def read_offsets(work_root: str) -> dict:
    path = offsets_path(work_root)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} not found. Run `scene_diagnostics.report()` first -- the per-date "
            "radiometric offsets are measured, not assumed, and defaulting them to zero "
            "would leave T6 about 4 dB low while every gate still passed.")
    with open(path) as fh:
        return json.load(fh)


if __name__ == "__main__":
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    import season_context
    wet = season_context.scene_wetness(os.path.join(root, "work", "context"))
    result = report(os.path.join(root, "work", "gamma0"), wet)
    print("\nwrote", write_offsets(os.path.join(root, "work"), result))
