"""Phase 1 acceptance gates. Nothing downstream runs until all three pass.

There is no leaderboard in Round 2, so a geocoding error has no external signal to
reveal it. These gates are the substitute: an independent geometric reference
(Capella's own geocoded preview), a cross-date consistency check, and a physical
plausibility band.

G1  footprint agreement with the vendor's geocoded preview, per date
G2  co-registration: our warp vs the preview, and date-to-date, must be <= 2 m
G3  radiometric plausibility -- see the note below

Note on G3. This gate originally asserted that the AOI median gamma0 should land in
-12 .. -6 dB, the usual band for vegetated land. It measured ~-21 dB, and the assumption
turned out to be the wrong half of the comparison: Capella's own reference
implementation (capella-reader, `rtc_isce3.py::create_beta0_raster`) states
`beta0_complex = scale_factor * DN`, so beta0 = intensity * scale_factor^2 -- exactly
what `geocode.py` computes. The absolute level really is that low. The scene tops out
at +27 dB over built-up corner reflectors, which is where X-band urban returns belong,
so the scale is anchored correctly at the bright end.

The replacement gate tests things that can actually falsify the calibration:
  a) the bright tail reaches the level X-band urban scattering demands
  b) the median sits meaningfully above the per-scene NESZ noise floor
  c) the dates agree after calibration on targets that have no crop calendar

(c) moved to `scene_diagnostics` in Round 3. It used to be tested as the spread of the
AOI median across dates, which worked while every date in the stack had a crop standing
in it. T6 is taken after most of the kharif harvest, so the AOI median legitimately drops
2.5 dB and the old test fails for the one reason a radiometric gate must not fire on: the
season happened. The replacement measures the same thing on built-up blocks instead.
"""

from __future__ import annotations

import gc
import glob
import os

import numpy as np
from osgeo import gdal, osr

from coreg_calib import FARM_WINDOW, phase_shift
from geocode import AOI_BOUNDS, PIXEL_SIZE, SCENES, TARGET_EPSG, load_meta

gdal.UseExceptions()

COREG_TOLERANCE_M = 2.0
BRIGHT_TAIL_MIN_DB = 15.0   # X-band urban corner reflectors
NESZ_MARGIN_DB = 3.0        # median must clear the noise floor by this much
CROSS_DATE_SPREAD_MAX_DB = 3.0   # retired as a gate in Round 3; see the note in run()


def farm_slice() -> tuple:
    """Row/column slice of the AOI grid covering `FARM_WINDOW`.

    G2's stack-consistency test is gated on this window, not on the full AOI. The
    registration exists to make one rasterised farm mask valid for every date, so the
    ground it has to be right over is the ground the farms sit on. The full-AOI figure is
    still printed, because for T5 the two differ by an order of magnitude and hiding that
    would be the dishonest choice -- but it is a diagnostic, not the gate.
    """
    x0, y0, x1, y1 = FARM_WINDOW
    r0, c0 = int(AOI_BOUNDS[3] - y1), int(x0 - AOI_BOUNDS[0])
    return slice(r0, r0 + int(y1 - y0)), slice(c0, c0 + int(x1 - x0))


def read_aoi(path: str, resample: str = "average") -> np.ndarray:
    """Read any geocoded raster onto the common AOI grid."""
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(TARGET_EPSG)
    xmin, ymin, xmax, ymax = AOI_BOUNDS
    ds = gdal.Warp(
        "", path, format="MEM", dstSRS=srs.ExportToWkt(),
        outputBounds=(xmin, ymin, xmax, ymax), xRes=PIXEL_SIZE, yRes=PIXEL_SIZE,
        resampleAlg=resample, outputType=gdal.GDT_Float32, srcNodata=0, dstNodata=0,
    )
    return ds.GetRasterBand(1).ReadAsArray()


def run() -> bool:
    """Run all three gates, holding at most four full-AOI rasters at once.

    The obvious structure -- load every date's product and every vendor preview, then run
    the gates -- keeps eight 27.8-megapixel float32 rasters alive simultaneously, ~890 MB,
    and it was the single largest resident block in the pipeline. Instead only the master
    pair is retained; each other date is read, used by all three gates, and released.

    The lines are buffered and printed grouped by gate afterwards, so the log reads in
    gate order (G1, then G2, then G3) even though the computation runs date-major.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    work = os.path.join(root, "work", "gamma0")
    ok = True

    metas, codes = {}, []
    for folder, code, date in SCENES:
        metas[code] = load_meta(folder, code, date)
        codes.append(code)

    def product(code: str) -> str:
        hits = glob.glob(os.path.join(work, f"gamma0_lin_{code}_*.tif"))
        if not hits:
            raise FileNotFoundError(f"no geocoded product for {code}; run geocode.py first")
        return hits[0]

    def g1(code: str, ours: np.ndarray, preview: np.ndarray) -> bool:
        a, b = ours > 0, preview > 0
        union = np.logical_or(a, b).sum()
        iou = np.logical_and(a, b).sum() / union if union else 0.0
        only_ours = np.logical_and(a, ~b).sum() / max(a.sum(), 1)
        g1_lines.append(f"    {code}  valid={a.mean():6.1%}  vendor={b.mean():6.1%}  "
                        f"IoU={iou:.4f}  ours-only={only_ours:.3%}  "
                        f"[{'PASS' if iou > 0.95 else 'FAIL'}]")
        return bool(iou > 0.95)

    def g3(code: str, ours: np.ndarray) -> tuple:
        v = ours[ours > 0]
        db = float(10.0 * np.log10(np.median(v)))
        top = float(10.0 * np.log10(v.max()))
        # Speckle statistics, which are the whole basis of the farm-not-pixel argument:
        # at one look CoV = 1 and ENL = 1, so if either departs from that the data has
        # been pre-smoothed somewhere and the +-5.6 dB per-pixel figure -- and the
        # 4.34/sqrt(N) that follows from it -- would be wrong.
        #
        # Measured per 16x16 block and reduced by the median, NOT over the whole AOI.
        # Whole-scene CoV is dominated by real heterogeneity (buildings, roads, field
        # boundaries) and reads ~15, which says nothing about looks; the estimator only
        # means anything inside a homogeneous patch, and the median block in a rural AOI
        # is homogeneous.
        below = float((10.0 * np.log10(v) < metas[code].nesz_peak_db).mean())
        del v
        bs = 16
        hh, ww = (ours.shape[0] // bs) * bs, (ours.shape[1] // bs) * bs
        blk = np.ascontiguousarray(ours[:hh, :ww]).reshape(hh // bs, bs, ww // bs, bs)
        full = (blk > 0).all(axis=(1, 3))
        mu, sd = blk.mean(axis=(1, 3)), blk.std(axis=(1, 3))
        del blk
        cov = float(np.median(sd[full] / mu[full])) if full.any() else float("nan")
        bright_ok, snr = top >= BRIGHT_TAIL_MIN_DB, db - metas[code].nesz_peak_db
        snr_ok = snr >= NESZ_MARGIN_DB
        g3_lines.append(f"    {code}  median={db:6.2f} dB   max={top:5.1f} dB "
                        f"[{'PASS' if bright_ok else 'FAIL'}]   "
                        f"NESZ={metas[code].nesz_peak_db:6.2f} dB, "
                        f"margin={snr:4.1f} dB [{'PASS' if snr_ok else 'FAIL'}]"
                        f"   CoV={cov:4.2f} ENL={1.0 / cov ** 2:4.2f}"
                        f"  {below:4.1%} below NESZ")
        return db, bool(bright_ok and snr_ok)

    g1_lines, g3_lines, stack_lines, vendor_lines = [], [], [], []
    medians = []

    # Fingerprint each product as it is read, and require all four to differ.
    #
    # The organizers' 20250619 folder ships a byte-identical duplicate of the T1 SLC, so a
    # pipeline that globs `*.tif` inside a date folder loads June 6 twice and every
    # temporal feature is silently wrong while every gate still passes. `geocode._slc_path`
    # selects by folder stem and `load_meta` now cross-checks the STAC datetime, but both
    # of those trust the *inputs*. This checks the *outputs*: two identical geocoded
    # rasters mean the same scene was processed twice, whatever the filenames said.
    #
    # (count, sum, sum-of-squares) over valid pixels, taken from arrays that are read
    # anyway, so it costs no extra I/O and no extra resident memory.
    prints = {}

    def fingerprint(code: str, arr: np.ndarray) -> None:
        v = arr[arr > 0].astype(np.float64)
        prints[code] = (int(v.size), float(v.sum()), float((v * v).sum()))

    master = codes[0]
    m_ours = read_aoi(product(master))
    m_prev = read_aoi(metas[master].preview_path)

    ok &= g1(master, m_ours, m_prev)
    db, good = g3(master, m_ours)
    medians.append(db)
    ok &= good
    fingerprint(master, m_ours)

    dy, dx = phase_shift(m_prev, m_ours)
    anchor = float(np.hypot(dy, dx)) * PIXEL_SIZE
    ok &= anchor <= COREG_TOLERANCE_M
    anchor_line = (f"      {master} vs vendor preview  dy={dy:+5.2f} dx={dx:+5.2f} px  "
                   f"|d|={anchor:4.2f} m  "
                   f"[{'PASS' if anchor <= COREG_TOLERANCE_M else 'FAIL'}]")

    for code in codes[1:]:
        ours = read_aoi(product(code))
        preview = read_aoi(metas[code].preview_path)

        ok &= g1(code, ours, preview)
        db, good = g3(code, ours)
        medians.append(db)
        ok &= good
        fingerprint(code, ours)

        rs, cs = farm_slice()
        dy, dx, qual = phase_shift(m_ours[rs, cs], ours[rs, cs], with_quality=True)
        dist = float(np.hypot(dy, dx)) * PIXEL_SIZE
        ok &= dist <= COREG_TOLERANCE_M
        wdy, wdx, wqual = phase_shift(m_ours, ours, with_quality=True)
        wide = float(np.hypot(wdy, wdx)) * PIXEL_SIZE
        stack_lines.append(f"      {code} vs {master}   over the farms dy={dy:+5.2f} "
                           f"dx={dx:+5.2f} px  |d|={dist:4.2f} m  peak={qual:.5f}  "
                           f"[{'PASS' if dist <= COREG_TOLERANCE_M else 'FAIL'}]"
                           f"   full AOI |d|={wide:5.2f} m  peak={wqual:.5f}")

        dy, dx = phase_shift(m_prev, preview)
        vendor_lines.append(f"      preview {code} vs preview {master}   |d|="
                            f"{float(np.hypot(dy, dx)) * PIXEL_SIZE:4.2f} m")
        del ours, preview
        gc.collect()

    del m_ours, m_prev
    gc.collect()

    print("G1  footprint agreement with vendor geocoded preview")
    print("\n".join(g1_lines))
    print(f"G2  co-registration (tolerance {COREG_TOLERANCE_M:.0f} m)")
    print("    absolute anchoring — master against the vendor's geocoded product")
    print(anchor_line)
    print("    stack consistency — every date against the master (drives temporal features)")
    print(f"    gated over FARM_WINDOW {FARM_WINDOW}, the ground the 966 plots sit on;")
    print("    the full-AOI figure follows each line as a diagnostic, not as the gate")
    print("\n".join(stack_lines))
    print("    vendor's own inter-date disagreement, for the record (not a gate)")
    print("\n".join(vendor_lines))
    print("G3  radiometric plausibility")
    print("\n".join(g3_lines))

    dupes = [(a, b) for i, a in enumerate(codes) for b in codes[i + 1:]
             if prints.get(a) == prints.get(b)]
    if dupes:
        raise ValueError(
            "INTEGRITY FAILURE: identical geocoded rasters for "
            + ", ".join(f"{a}/{b}" for a, b in dupes)
            + ". The same acquisition has been processed twice -- check the SLC selection "
              "against the duplicate in the 20250619 folder.")
    print(f"    all {len(codes)} geocoded products are distinct rasters "
          "(count/sum/sum-of-squares fingerprint) [PASS]")

    # The cross-date AOI-median spread WAS the gate here in Round 2, at a 3 dB tolerance,
    # and on this stack it measures 4.26 dB and fails. Loosening it would be the wrong
    # move, and so would passing it: the number is not a calibration statistic at all.
    #
    # Round 2 measured 1.79 dB across four dates that all had a crop in the ground. Round 3
    # adds T6, taken after most of the kharif harvest, and a village with its crop removed
    # is genuinely darker than the same village in August. The AOI median is vegetation
    # plus surface moisture, both of which are supposed to move, and gating on it asks the
    # radiometry to prove that the season did not happen.
    #
    # This is Round 2's own lesson 20 -- "define the gate before, and verify the gate's own
    # assumption after" -- landing on Round 2's own gate. The premise that the dates should
    # agree was true for a Jun-Oct stack and is false for a Jun-Nov one.
    #
    # So the spread is still printed, because it is informative, and the gate has moved to
    # `scene_diagnostics`, which asks the question this one was trying to ask: do the dates
    # agree on targets that have no crop calendar? They do, to 0.02 dB, once each date's
    # measured offset is removed -- and the two dates that check it took no part in
    # choosing the targets.
    spread = float(np.max(medians) - np.min(medians))
    print(f"    cross-date AOI-median spread = {spread:.2f} dB. NOT a gate: this is "
          f"vegetation and surface moisture,\n    and over a stack that now runs past "
          f"harvest it is supposed to move. The calibration gate is in "
          f"scene_diagnostics.")

    print("\nPhase 1 gates:", "ALL PASS" if ok else "FAILURE — do not proceed")
    return ok


if __name__ == "__main__":
    raise SystemExit(0 if run() else 1)
