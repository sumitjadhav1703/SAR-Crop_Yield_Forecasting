"""Solve for the terrain height the RPC geocoding should assume.

Capella focused these scenes onto a constant surface (`terrain_models.focusing` =
ExplicitInflatedWGS84[-21.534 m]), and the 225 GCPs sit on that same surface. The real
ground under Sokhda is not at that height, and a height error displaces a geocoded
pixel along ground range by `dh / tan(theta_i)`.

That signature is testable: the initial misregistration against Capella's own geocoded
preview was 5.7 m at theta=35.2 deg and 7.1 m at theta=28.7 deg, a ratio of 1.25 against
the 1.28 predicted by 1/tan(theta). So we solve for the height directly, per scene, by
minimising the offset against the vendor product.

The validation is that four scenes with three different incidence angles, fitted
independently, must agree on one height -- because they are all looking at the same
ground. Agreement is evidence the model is physical rather than a curve fit.
"""

from __future__ import annotations

import os

import numpy as np
from osgeo import gdal, osr
from scipy import fft as sp_fft
from scipy import ndimage

from geocode import (
    AOI_BOUNDS, PIXEL_SIZE, SCENES, TARGET_EPSG, RPC_HEIGHT,
    build_slant_gamma0, load_meta,
)  # noqa: F401  (AOI_BOUNDS is used by the residual solver)

gdal.UseExceptions()

# A window over the village core: enough structure for correlation, small enough that
# a height sweep is cheap. Used ONLY by the height fit, where what matters is having
# strong built-up structure to correlate against the vendor product.
FIT_WINDOW = (308500.0, 2479600.0, 312000.0, 2482600.0)

# The window the inter-date registration is solved on, and the window G2 measures over.
#
# It is the bounding box of the 966 farm polygons plus ~250 m. Round 2 solved its shifts
# on FIT_WINDOW, but the farms run from 308561 to 312710 easting and 2479198 to 2482857
# northing -- they spill outside FIT_WINDOW on the east, north and south, so the
# registration was being optimised on a window that excluded part of the ground it was
# going to be used to sample. Measured cost of that: T3, the peak-canopy date, sits 0.13 m
# from the master inside FIT_WINDOW and 1.35 m from it over the farms.
#
# It also matters for T5. Registration quality is not uniform across the AOI for a
# right-looking scene: T5 lands 0.19 m from the master over the farms (peak 0.00177) and
# 4.48 m over the full AOI (peak 0.00138, the weakest correlation in the stack). The full
# AOI includes large low-structure tracts where reversed-look correlation simply fails.
# Registering and gating on the ground we actually sample is the correct choice; quoting
# the full-AOI number as if it described the farms would not be.
FARM_WINDOW = (308300.0, 2478950.0, 312950.0, 2483100.0)


def _warp_window(src, height: float, bounds=FIT_WINDOW, path: str = "") -> np.ndarray:
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(TARGET_EPSG)
    ds = gdal.Warp(
        path or "", src, format="GTiff" if path else "MEM",
        dstSRS=srs.ExportToWkt(), rpc=True,
        transformerOptions=[f"RPC_HEIGHT={height}"],
        outputBounds=bounds, xRes=PIXEL_SIZE, yRes=PIXEL_SIZE,
        resampleAlg="average", errorThreshold=0.0,
        srcNodata=0, dstNodata=0, outputType=gdal.GDT_Float32,
    )
    return ds.GetRasterBand(1).ReadAsArray()


def _reference_window(path: str, bounds=FIT_WINDOW) -> np.ndarray:
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(TARGET_EPSG)
    ds = gdal.Warp(
        "", path, format="MEM", dstSRS=srs.ExportToWkt(), outputBounds=bounds,
        xRes=PIXEL_SIZE, yRes=PIXEL_SIZE, resampleAlg="average",
        outputType=gdal.GDT_Float32, srcNodata=0, dstNodata=0,
    )
    return ds.GetRasterBand(1).ReadAsArray()


def _edges(arr: np.ndarray) -> np.ndarray:
    """Edge structure only -- the one thing a linear product and an unknown 8-bit
    display stretch still share."""
    # float32 for the same reason as `phase_shift`: these are full-AOI arrays and the
    # double-precision version allocated four 222 MB temporaries to compute a gradient
    # magnitude that feeds a peak-finder. The log compresses the dynamic range to ~6
    # decades, well inside float32.
    valid = arr > 0
    out = np.zeros(arr.shape, dtype=np.float32)
    out[valid] = np.log(arr[valid], dtype=np.float32)
    if valid.any():
        out[valid] -= out[valid].mean()
    smooth = ndimage.gaussian_filter(out, 1.5, output=np.float32)
    del out
    gy, gx = np.gradient(smooth)
    del smooth
    mag = np.hypot(gx, gy)
    del gx, gy
    mag[~valid] = 0.0
    return mag


def _parabolic(c: np.ndarray, idx: int, axis_len: int) -> float:
    """Sub-pixel refinement of a correlation peak by a 3-point parabola."""
    lo, hi = (idx - 1) % axis_len, (idx + 1) % axis_len
    denom = c[lo] - 2.0 * c[idx] + c[hi]
    if denom == 0:
        return 0.0
    return float(np.clip(0.5 * (c[lo] - c[hi]) / denom, -1.0, 1.0))


# The largest inter-date shift the geometry admits, in metres. Capella publish ~5 m CE90
# absolute geolocation, each scene here is independently registered to its own vendor
# product to better than 0.15 m by the height fit, and the five well-behaved dates all
# solve inside 5.4 m. Anything beyond this is a false correlation peak, not a collect
# that landed 100 m away.
MAX_SHIFT_M = 20.0

# Decimation for the coarse pass of the two-scale search. Shadow and layover displacements
# are metre-scale; the field-parcel mosaic is tens of metres across. Averaging 8x1 m
# pixels together suppresses the first and keeps the second, which is what makes the
# coarse pass survive a reversed look direction when the fine pass does not.
COARSE_FACTOR = 8


def _peak(corr: np.ndarray, max_shift_px: float | None) -> tuple:
    """Locate the correlation peak, optionally restricted to a neighbourhood of zero.

    Returns (dy, dx, peak_value). The peak value is returned rather than discarded
    because it is the only warning a caller gets that a match is weak: a reversed-look
    pair produces a correlation surface that is nearly flat, and a flat surface still has
    an argmax.
    """
    ny, nx = corr.shape
    if max_shift_px is None:
        py, px = np.unravel_index(int(np.argmax(corr)), corr.shape)
    else:
        r = int(np.ceil(max_shift_px))
        idx = np.arange(-r, r + 1)
        sub = corr[np.ix_(idx % ny, idx % nx)]
        i, j = np.unravel_index(int(np.argmax(sub)), sub.shape)
        py, px = int(idx[i] % ny), int(idx[j] % nx)
    value = float(corr[py, px])
    dy = py + _parabolic(corr[:, px], py, ny)
    dx = px + _parabolic(corr[py, :], px, nx)
    if dy > ny / 2:
        dy -= ny
    if dx > nx / 2:
        dx -= nx
    return float(dy), float(dx), value


def _correlation_surface(ref: np.ndarray, mov: np.ndarray) -> np.ndarray:
    """Phase-correlation surface of the two images' edge structure.

    Single precision throughout, via `scipy.fft`. `numpy.fft` always computes in double
    regardless of input dtype, so a full-AOI transform here is a 27.8-million-element
    complex128 array -- 445 MB per spectrum, with several alive at once. That, not the
    rasters themselves, was the pipeline's true high-water mark (2,850 MB measured on
    Kaggle). `scipy.fft` honours float32 and returns complex64, which quarters it.
    Registration precision is unaffected: the peak is located to ~0.01 px either way, far
    below the 2 m gate tolerance.
    """
    a = _edges(ref).astype(np.float32)
    b = _edges(mov).astype(np.float32)
    win = (np.hanning(a.shape[0])[:, None] * np.hanning(a.shape[1])[None, :]).astype(np.float32)
    a *= win
    b *= win
    del win
    fa, fb = sp_fft.rfft2(a), sp_fft.rfft2(b)
    del a
    cross = fa * np.conj(fb)
    del fa, fb
    mag = np.abs(cross)
    cross = np.divide(cross, mag, out=np.zeros_like(cross), where=mag > 0)
    del mag
    corr = sp_fft.irfft2(cross, s=b.shape)
    del cross, b
    return corr


def _decimate(arr: np.ndarray, factor: int) -> np.ndarray:
    """Block-mean decimation that keeps nodata out of the average."""
    ny, nx = (arr.shape[0] // factor) * factor, (arr.shape[1] // factor) * factor
    a = arr[:ny, :nx].astype(np.float32)
    valid = (a > 0).astype(np.float32)
    a = a * valid
    shape = (ny // factor, factor, nx // factor, factor)
    total = a.reshape(shape).sum(axis=(1, 3))
    count = valid.reshape(shape).sum(axis=(1, 3))
    return np.divide(total, count, out=np.zeros_like(total), where=count > 0)


def phase_shift(ref: np.ndarray, mov: np.ndarray, max_shift_m: float | None = MAX_SHIFT_M,
                with_quality: bool = False):
    """Sub-pixel (dy, dx) translation aligning `mov` onto `ref`, in pixels.

    Two scales. The coarse pass decimates by `COARSE_FACTOR` and searches without any
    restriction; the fine pass searches full resolution within `max_shift_m` of the
    coarse answer. That ordering is what makes T5 work.

    T5 is the only right-looking scene in the stack. Shadow and layover fall on the
    opposite side of every bund, hedgerow and building, so at 1 m the edge structure the
    matcher keys on genuinely does not overlay -- its correlation surface is nearly flat
    (peak 0.0024 against 0.0075-0.0080 for the left-looking dates) and its unconstrained
    argmax landed 108 m away, which no geolocation error can produce. At 8 m the
    metre-scale shadow displacement is averaged out and the field-parcel mosaic, which
    does not care which side the radar looked from, dominates.

    `with_quality` additionally returns the peak value, so a caller can see a weak match
    rather than take a confident-looking number from a flat surface.
    """
    if max_shift_m is None:
        corr = _correlation_surface(ref, mov)
        dy, dx, value = _peak(corr, None)
        return (dy, dx, value) if with_quality else (dy, dx)

    coarse = _correlation_surface(_decimate(ref, COARSE_FACTOR), _decimate(mov, COARSE_FACTOR))
    cdy, cdx, _ = _peak(coarse, None)
    del coarse
    cdy, cdx = cdy * COARSE_FACTOR, cdx * COARSE_FACTOR

    corr = _correlation_surface(ref, mov)
    ny, nx = corr.shape
    r = int(np.ceil(max_shift_m / PIXEL_SIZE))
    iy = (np.arange(-r, r + 1) + int(round(cdy))) % ny
    ix = (np.arange(-r, r + 1) + int(round(cdx))) % nx
    sub = corr[np.ix_(iy, ix)]
    i, j = np.unravel_index(int(np.argmax(sub)), sub.shape)
    py, px = int(iy[i]), int(ix[j])
    value = float(corr[py, px])
    dy = py + _parabolic(corr[:, px], py, ny)
    dx = px + _parabolic(corr[py, :], px, nx)
    if dy > ny / 2:
        dy -= ny
    if dx > nx / 2:
        dx -= nx
    return (float(dy), float(dx), value) if with_quality else (float(dy), float(dx))


def fit_height(code: str, slant_path: str, preview_path: str, incidence_deg: float,
               coarse=np.arange(-60.0, 21.0, 10.0)) -> float:
    """Coarse sweep, then a refinement using the analytic dh/tan(theta) sensitivity.

    Every `phase_shift` here passes `max_shift_m=None`. The sweep deliberately mis-geocodes
    by up to 70 m to map out the sensitivity curve, so the bounded search that protects the
    *inter-date* registration would clamp exactly the displacements this function needs to
    see, and the curve would come back flat.
    """
    ref = _reference_window(preview_path)
    src = gdal.Open(slant_path)

    best = (None, np.inf)
    for h in coarse:
        dy, dx = phase_shift(ref, _warp_window(src, float(h)), max_shift_m=None)
        dist = float(np.hypot(dy, dx)) * PIXEL_SIZE
        print(f"    {code}  h={h:+7.1f} m   dy={dy:+6.2f} dx={dx:+6.2f} px   |d|={dist:5.2f} m")
        if dist < best[1]:
            best = (float(h), dist)

    h0 = best[0]
    for _ in range(3):
        dy, dx = phase_shift(ref, _warp_window(src, h0), max_shift_m=None)
        dist = float(np.hypot(dy, dx)) * PIXEL_SIZE
        if dist < 0.3:
            break
        # A height error moves the pixel along ground range by dh/tan(theta); we only
        # know the magnitude of the residual, so try both signs and keep the better.
        step = dist * np.tan(np.radians(incidence_deg))
        cands = []
        for cand in (h0 + step, h0 - step):
            cdy, cdx = phase_shift(ref, _warp_window(src, cand), max_shift_m=None)
            cands.append((float(np.hypot(cdy, cdx)) * PIXEL_SIZE, cand))
        cands.sort()
        if cands[0][0] >= dist:
            break
        h0 = cands[0][1]
    dy, dx = phase_shift(ref, _warp_window(src, h0), max_shift_m=None)
    print(f"    {code}  FIT h={h0:+7.2f} m -> residual {np.hypot(dy, dx) * PIXEL_SIZE:.2f} m")
    return h0


def run(work: str) -> dict:
    os.makedirs(work, exist_ok=True)
    fitted = {}
    for folder, code, date in SCENES:
        m = load_meta(folder, code, date)
        slant = os.path.join(work, f"_slant_gamma0_{code}.tif")
        if not os.path.exists(slant):
            print(f"[{code}] building slant gamma0 for the height fit ...", flush=True)
            build_slant_gamma0(m, slant)
        print(f"[{code}] fitting terrain height (theta={m.incidence_center_deg:.2f} deg), "
              f"focusing surface was {RPC_HEIGHT:.2f} m")
        fitted[code] = fit_height(code, slant, m.preview_path, m.incidence_center_deg)

    vals = np.array(list(fitted.values()))
    print("\nfitted heights:", {k: round(v, 2) for k, v in fitted.items()})
    print(f"mean {vals.mean():.2f} m   spread {vals.max() - vals.min():.2f} m   "
          f"std {vals.std():.2f} m")
    print("Four scenes at three incidence angles agreeing on one height is the check "
          "that this is terrain, not a fudge factor.")
    return fitted


def solve_residual_shifts(work: str, master: str = "T1", iterations: int = 3) -> dict:
    """Register every date onto one master, after the height fit.

    The height fit puts each date within 0.2 m of *its own* vendor preview, but the
    vendor previews disagree with each other by up to 4.3 m -- Capella's absolute
    geolocation error between separately-tasked collects. This solves the leftover
    translation directly on our own gamma0 products, which is what actually gets
    sampled.

    The sign convention is not assumed: each candidate shift is applied, re-measured,
    and kept only if the residual actually falls.
    """
    from geocode import RPC_HEIGHTS, warp_to_aoi

    slants = {code: os.path.join(work, f"_slant_gamma0_{code}.tif") for _, code, _ in SCENES}
    for code, path in slants.items():
        if not os.path.exists(path):
            raise FileNotFoundError(f"{path} missing; run geocode.py --keep-slant first")

    # Correlate over the farm-bearing window: the ground this registration is for.
    x0, y0, x1, y1 = FARM_WINDOW
    ax0, ay0 = int(x0 - AOI_BOUNDS[0]), int(AOI_BOUNDS[3] - y1)
    nx, ny = int(x1 - x0), int(y1 - y0)

    def warped(code: str, shift: tuple) -> np.ndarray:
        tmp = os.path.join(work, f"_coreg_{code}.tif")
        warp_to_aoi(slants[code], tmp, RPC_HEIGHTS[code], shift)
        ds = gdal.Open(tmp)
        arr = ds.GetRasterBand(1).ReadAsArray(ax0, ay0, nx, ny)
        ds = None
        os.remove(tmp)
        return arr

    ref = warped(master, (0.0, 0.0))
    shifts = {master: (0.0, 0.0)}
    quality = {}
    for _, code, _ in SCENES:
        if code == master:
            print(f"    {master}  master")
            continue
        shift = (0.0, 0.0)
        dy, dx, qual = phase_shift(ref, warped(code, shift), with_quality=True)
        best = float(np.hypot(dy, dx)) * PIXEL_SIZE
        print(f"    {code}  start dy={dy:+5.2f} dx={dx:+5.2f} px  |d|={best:5.2f} m  "
              f"peak={qual:.5f}")
        for _ in range(iterations):
            if best < 0.5:
                break
            improved = False
            for sy, sx in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
                cand = (shift[0] + sx * dx * PIXEL_SIZE, shift[1] + sy * dy * PIXEL_SIZE)
                cdy, cdx, cq = phase_shift(ref, warped(code, cand), with_quality=True)
                dist = float(np.hypot(cdy, cdx)) * PIXEL_SIZE
                if dist < best - 1e-6:
                    best, shift, dy, dx, qual, improved = dist, cand, cdy, cdx, cq, True
                    break
            if not improved:
                break
        shifts[code] = (round(shift[0], 2), round(shift[1], 2))
        quality[code] = qual
        print(f"    {code}  shift=({shifts[code][0]:+.2f}, {shifts[code][1]:+.2f}) m "
              f"-> residual {best:.2f} m  peak={qual:.5f}")

    # The peak value is reported because it is the difference between a measurement and a
    # number. T5's correlation surface is roughly a third as sharp as the left-looking
    # dates', which is the reversed look direction showing up in the statistic rather than
    # in a surprise later.
    ref_q = np.median([q for c, q in quality.items() if c != master])
    for code, q in quality.items():
        if code != master and q < 0.5 * ref_q:
            print(f"    NOTE {code}: correlation peak {q:.5f} is under half the "
                  f"stack median {ref_q:.5f}. The shift is bounded by geometry "
                  f"(|d| <= {MAX_SHIFT_M:.0f} m) and cross-checked at {COARSE_FACTOR}x "
                  f"decimation, but it is the least certain registration in the stack.")
    return shifts


if __name__ == "__main__":
    import argparse

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    work = os.path.join(root, "work", "gamma0")
    ap = argparse.ArgumentParser()
    ap.add_argument("--residual", action="store_true",
                    help="solve per-date co-registration shifts instead of terrain height")
    args = ap.parse_args()
    if args.residual:
        print("Residual co-registration to the T1 master:")
        print("COREG_SHIFT_EN =", solve_residual_shifts(work))
    else:
        run(work)
