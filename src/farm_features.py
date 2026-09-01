"""Per-farm statistics from the calibrated gamma0 stack.

The unit of analysis is the farm polygon, not the pixel. That single change is what
makes this tractable: Sokhda's farms have a median area of 0.27 ha, so a median farm
holds ~2,700 one-metre pixels, and single-look speckle averages down as 4.34/sqrt(N) dB
-- about 0.08 dB, against +-5.6 dB for an individual pixel. Round 1's documented
separability ceiling was a pixel-level ceiling and it does not bind here.

What replaces speckle as the dominant risk is geolocation. A 0.27 ha field is a 52 m
square, so a few metres of edge contamination matters. Phase 1 registered the stack to
0.3 m; this module handles the rest by eroding each polygon before sampling.

Two statistics deserve a note:

  CoV = std/mean of *linear* power. For fully-developed speckle at L looks the expected
  value is 1/sqrt(L), so CoV over a uniform field is a pure speckle prediction and any
  excess is real within-field heterogeneity.

  ENL = mean^2/var, the equivalent number of looks. Averaging N pixels of a uniform
  target gives ENL ~ N * L; a field that scores far below that is not uniform. Comparing
  observed ENL against what the pixel count alone predicts is what turns a speckle
  statistic into a crop-condition measurement.
"""

from __future__ import annotations

import glob
import os

import numpy as np
import pandas as pd
from osgeo import gdal, ogr, osr

import scene_diagnostics
from geocode import AOI_BOUNDS, DATA_DIR, DOY, PIXEL_SIZE, SCENES, TARGET_EPSG

gdal.UseExceptions()

def _find_shp(name: str) -> str:
    """Locate a shapefile by name under DATA_DIR, wherever the archive nested it.

    The distributed layout double-nests (`Farm_boundaries_shp/Farm_boundaries_shp/...`) and
    that nesting is an artefact of the packaging, not something to hard-code across
    environments. Exactly one match is required: zero raises, and so does more than one,
    because two candidates would mean silently picking the wrong boundaries.
    """
    hits = sorted(glob.glob(os.path.join(DATA_DIR, "**", name), recursive=True))
    if len(hits) != 1:
        raise FileNotFoundError(
            f"expected exactly one {name} under {DATA_DIR}, found {len(hits)}"
            + ("".join("\n  " + h for h in hits) if hits else ""))
    return hits[0]


FARM_SHP = _find_shp("Sokhda_Farms.shp")
VILLAGE_SHP = _find_shp("Sokhda_Village.shp")

# Erosion: enough to drop the mixed boundary pixels, capped so a small field keeps a
# usable core. The cap is a fraction of the polygon's inscribed radius, approximated as
# area/perimeter.
ERODE_MAX_M = 4.0
ERODE_FRACTION = 0.25
MIN_CORE_PX = 60          # below this the farm-mean is too noisy to trust on its own
MIN_DATE_COVERAGE = 0.50  # a date counts for a farm only above this valid-pixel fraction
# Round 2 ran >=3-of-4. With six dates the same *proportion* would be 4.5, and the same
# absolute tolerance (one date may be missing) would be 5. Four is chosen: it keeps the
# Round 2 rule's spirit -- a farm needs enough of its own trajectory that interpolating
# the rest is not invention -- while accepting that two of the six passes have the
# narrowest swaths in the stack (T2 3910 and T3 3897 columns against T1's 4682), so
# demanding five would discard farms for a packaging accident rather than a data problem.
# The coverage table printed by `build` is what this number has to be judged against.
MIN_VALID_DATES = 4       # >=4-of-6, Round 1's relaxed-validity rule carried forward
IMPUTE_NEIGHBOURS = 8     # spatial fill for farms the radar swath never covered

DATE_ORDER = [code for _, code, _ in SCENES]


def _ogr_mem_driver():
    """The OGR in-memory driver, whatever this GDAL build calls it.

    GDAL renamed it from "Memory" to "MEM" in 3.11 as part of unifying the raster and
    vector driver names. `GetDriverByName` returns None rather than raising for an unknown
    name, so the failure otherwise surfaces much later as
    `'NoneType' object has no attribute 'CreateDataSource'`. Note this is the *vector*
    driver -- `gdal.GetDriverByName("MEM")` for rasters is unaffected and unchanged.

    "MEM" is tried FIRST: on 3.11+ the old name still resolves but emits a deprecation
    warning on every call, and on older builds "MEM" simply returns None and the loop falls
    through to the name that build knows.
    """
    for name in ("MEM", "Memory"):
        drv = ogr.GetDriverByName(name)
        if drv is not None:
            return drv
    raise RuntimeError("no OGR in-memory driver in this GDAL build "
                       f"({gdal.__version__}); tried 'Memory' and 'MEM'")


def _utm_srs() -> osr.SpatialReference:
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(TARGET_EPSG)
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return srs


def load_farms() -> tuple:
    """Farms reprojected to UTM 43N, with their eroded core geometry.

    Returns (records, memory_datasource). The datasource must stay referenced for the
    layer to remain valid.
    """
    src = ogr.Open(FARM_SHP)
    layer = src.GetLayer()
    ssrs = layer.GetSpatialRef()
    ssrs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    tsrs = _utm_srs()
    transform = osr.CoordinateTransformation(ssrs, tsrs)

    mem = _ogr_mem_driver().CreateDataSource("farms")
    out = mem.CreateLayer("core", tsrs, ogr.wkbPolygon)
    out.CreateField(ogr.FieldDefn("IDX", ogr.OFTInteger))

    records = []
    for i, feat in enumerate(layer):
        geom = feat.GetGeometryRef().Clone()
        geom.Transform(transform)
        area = geom.GetArea()
        perim = geom.Boundary().Length()
        # area/perimeter is the inscribed radius for a circle and a good enough proxy
        # for these compact parcels.
        erode = min(ERODE_MAX_M, ERODE_FRACTION * (area / perim) if perim else 0.0)
        core = geom.Buffer(-erode) if erode > 0 else geom.Clone()
        if core.IsEmpty() or core.GetArea() <= 0:
            core = geom.Clone()
            erode = 0.0

        idx = i + 1
        nf = ogr.Feature(out.GetLayerDefn())
        nf.SetGeometry(core)
        nf.SetField("IDX", idx)
        out.CreateFeature(nf)

        centroid = geom.Centroid()
        records.append({
            "idx": idx,
            "farm_id": int(feat.GetField("FID")),
            "village_id": int(feat.GetField("ID_1")),
            "village_name": feat.GetField("VILLAGE"),
            "area_ha": area / 10000.0,
            "erode_m": erode,
            "cx": centroid.GetX(),
            "cy": centroid.GetY(),
        })
    return records, mem


def rasterise_cores(mem_ds, shape: tuple, geotransform: tuple) -> np.ndarray:
    """Label raster of eroded farm cores on the gamma0 grid."""
    ny, nx = shape
    lab_ds = gdal.GetDriverByName("MEM").Create("", nx, ny, 1, gdal.GDT_Int32)
    lab_ds.SetGeoTransform(geotransform)
    lab_ds.SetProjection(_utm_srs().ExportToWkt())
    gdal.RasterizeLayer(lab_ds, [1], mem_ds.GetLayer(), options=["ATTRIBUTE=IDX"])
    return lab_ds.GetRasterBand(1).ReadAsArray()


BLOCK_ROWS = 512


def _grouped(labels: np.ndarray, values: np.ndarray, n: int) -> tuple:
    """Per-label count, sum and sum-of-squares over valid pixels.

    Accumulated in row blocks. Done whole-array, the boolean-indexed `int64` labels, the
    `float64` values and their squares are three temporaries the size of the raster at
    once -- ~670 MB for this 5906x4714 grid, on top of the raster and the label mask.
    Blocking caps that at a few MB and changes no result: count, sum and sum-of-squares
    are exactly additive across blocks.
    """
    count = np.zeros(n + 1, dtype=np.int64)
    total = np.zeros(n + 1, dtype=np.float64)
    sq = np.zeros(n + 1, dtype=np.float64)
    for r0 in range(0, values.shape[0], BLOCK_ROWS):
        v = values[r0:r0 + BLOCK_ROWS]
        valid = v > 0
        if not valid.any():
            continue
        lab = labels[r0:r0 + BLOCK_ROWS][valid].astype(np.int64)
        val = v[valid].astype(np.float64)
        count += np.bincount(lab, minlength=n + 1)
        total += np.bincount(lab, weights=val, minlength=n + 1)
        sq += np.bincount(lab, weights=val * val, minlength=n + 1)
    return count[1:], total[1:], sq[1:]


def _nanmedian_where_measured(block: np.ndarray) -> np.ndarray:
    """Column medians ignoring NaN, and NaN for a column with nothing measured in it."""
    out = np.full(block.shape[1], np.nan)
    ok = np.isfinite(block).any(axis=0)
    if ok.any():
        out[ok] = np.nanmedian(block[:, ok], axis=0)
    return out


def build(work: str) -> pd.DataFrame:
    records, mem = load_farms()
    n = len(records)
    df = pd.DataFrame(records)

    rasters = {}
    for _, code, _ in SCENES:
        hits = glob.glob(os.path.join(work, f"gamma0_lin_{code}_*.tif"))
        if not hits:
            raise FileNotFoundError(f"missing geocoded gamma0 for {code}")
        rasters[code] = hits[0]

    ref = gdal.Open(rasters[DATE_ORDER[0]])
    shape = (ref.RasterYSize, ref.RasterXSize)
    gt = ref.GetGeoTransform()
    labels = rasterise_cores(mem, shape, gt)

    core_px = np.bincount(labels.ravel(), minlength=n + 1)[1:]
    df["core_px"] = core_px

    for code in DATE_ORDER:
        ds = gdal.Open(rasters[code])
        if (ds.RasterYSize, ds.RasterXSize) != shape or ds.GetGeoTransform() != gt:
            raise ValueError(f"{code} is not on the common grid; re-run geocode.py")
        arr = ds.GetRasterBand(1).ReadAsArray()

        count, total, sq = _grouped(labels, arr, n)
        with np.errstate(invalid="ignore", divide="ignore"):
            mean = np.where(count > 0, total / np.maximum(count, 1), np.nan)
            var = np.where(count > 1, sq / np.maximum(count, 1) - mean**2, np.nan)
            var = np.maximum(var, 0.0)
            cov = np.where(mean > 0, np.sqrt(var) / mean, np.nan)
            enl = np.where(var > 0, mean**2 / var, np.nan)

        df[f"cov_frac_{code}"] = np.where(core_px > 0, count / np.maximum(core_px, 1), 0.0)
        df[f"g0_lin_{code}"] = mean
        df[f"g0_db_raw_{code}"] = 10.0 * np.log10(np.where(mean > 0, mean, np.nan))
        df[f"cov_{code}"] = cov
        df[f"enl_{code}"] = enl
        df[f"npx_{code}"] = count

    # --- per-date radiometric offsets, measured not assumed -------------------------
    #
    # `scene_diagnostics` estimates one constant per date on 8 m blocks in the built-up
    # tail -- targets with no crop calendar -- and the estimate is validated on two dates
    # held out of the selection: T4 and T6 sit 4.01 dB apart before the offsets and
    # 0.02 dB apart after. T6 alone carries +4.28 dB of it. Without this correction every
    # feature that differences the late season against the early season is wrong by about
    # 4 dB and the whole stack reads as if the village had been harvested twice over.
    #
    # T5 gets no offset. Its residual against the master is not a constant: it runs
    # -3.5 dB on the darkest blocks and +2.3 dB on the brightest, and at stricter
    # selections it reaches +18 dB, because two mechanisms with opposite signs are at work
    # (rain brightening rough surfaces, reversed look direction extinguishing dihedrals).
    offsets = scene_diagnostics.read_offsets(os.path.dirname(os.path.abspath(work)))["offsets_db"]
    for code in DATE_ORDER:
        df[f"g0_db_{code}"] = df[f"g0_db_raw_{code}"] + offsets.get(code, 0.0)
        df[f"offset_db_{code}"] = offsets.get(code, 0.0)

    # --- validity: Round 1's confirmed relaxed >=3-of-4 rule -----------------------
    cover = df[[f"cov_frac_{c}" for c in DATE_ORDER]].to_numpy()
    good = (cover >= MIN_DATE_COVERAGE) & np.isfinite(
        df[[f"g0_db_{c}" for c in DATE_ORDER]].to_numpy()
    )
    df["n_valid_dates"] = good.sum(axis=1)

    db = df[[f"g0_db_{c}" for c in DATE_ORDER]].to_numpy(dtype=float).copy()
    db[~good] = np.nan

    # Fill a single missing date by interpolating the farm's own trajectory in time --
    # its neighbouring dates are far more informative than any cohort average.
    doys = np.array([DOY[c] for c in DATE_ORDER], dtype=float)
    filled = db.copy()
    interpolated = np.zeros(len(df), dtype=bool)
    for i in range(len(df)):
        row = db[i]
        miss = ~np.isfinite(row)
        if miss.any() and (~miss).sum() >= MIN_VALID_DATES:
            filled[i, miss] = np.interp(doys[miss], doys[~miss], row[~miss])
            interpolated[i] = True

    df["data_quality"] = np.where(
        df["n_valid_dates"] == len(DATE_ORDER), "measured",
        np.where(df["n_valid_dates"] >= MIN_VALID_DATES, "interpolated", "imputed"),
    )
    df["core_px_low"] = df["core_px"] < MIN_CORE_PX

    # --- spatial fill for farms the swath never covered ----------------------------
    # 71 farms sit off the edge of one or more collects and cannot reach 3 valid dates.
    # The rubric requires every farm to be processed, so they are filled from their
    # nearest well-measured neighbours: cropping in a village is strongly spatially
    # autocorrelated, adjacent parcels usually carry the same crop and management, and
    # this breaks the circularity of needing a crop label to impute the features that
    # produce the crop label. They stay flagged as `imputed` everywhere downstream.
    donor = (df["data_quality"] != "imputed").to_numpy()
    need = ~donor
    if need.any():
        if donor.sum() < IMPUTE_NEIGHBOURS:
            raise ValueError("too few measured farms to impute from")
        xy = df[["cx", "cy"]].to_numpy()
        donor_xy = xy[donor]
        donor_db = filled[donor]
        donor_cov = df.loc[donor, [f"cov_{c}" for c in DATE_ORDER]].to_numpy(dtype=float)
        donor_enl = df.loc[donor, [f"enl_{c}" for c in DATE_ORDER]].to_numpy(dtype=float)
        cov_all = df[[f"cov_{c}" for c in DATE_ORDER]].to_numpy(dtype=float)
        enl_all = df[[f"enl_{c}" for c in DATE_ORDER]].to_numpy(dtype=float)
        for i in np.flatnonzero(need):
            dist = np.hypot(donor_xy[:, 0] - xy[i, 0], donor_xy[:, 1] - xy[i, 1])
            near = np.argsort(dist)[:IMPUTE_NEIGHBOURS]
            filled[i] = np.nanmedian(donor_db[near], axis=0)
            # A donor set can be all-NaN for one date -- T5's CoV is undefined because T5's
            # level is the T4-T6 interpolation, not a measurement. The median of nothing is
            # NaN and that is the right answer, but `np.nanmedian` warns on the way there
            # and the warning lands in the shipped log looking like a defect. Take the
            # median only where there is something to take it over.
            cov_all[i] = _nanmedian_where_measured(donor_cov[near])
            enl_all[i] = _nanmedian_where_measured(donor_enl[near])
        for j, code in enumerate(DATE_ORDER):
            df[f"cov_{code}"] = cov_all[:, j]
            df[f"enl_{code}"] = enl_all[:, j]
        df["impute_donor_dist_m"] = np.nan
        df.loc[need, "impute_donor_dist_m"] = [
            float(np.sort(np.hypot(donor_xy[:, 0] - xy[i, 0],
                                   donor_xy[:, 1] - xy[i, 1]))[:IMPUTE_NEIGHBOURS].mean())
            for i in np.flatnonzero(need)
        ]

    if not np.isfinite(filled).all():
        raise ValueError("gamma0 trajectory still incomplete after interpolation and fill")

    for j, code in enumerate(DATE_ORDER):
        df[f"g0_db_measured_{code}"] = filled[:, j]

    # --- T5's level is not usable, so it is not used --------------------------------
    #
    # Everything downstream that integrates or differences LEVELS reads
    # `g0_db_filled_*`, and in that trajectory T5 is replaced by the straight line
    # joining T4 and T6 in time. This is not imputation of missing data -- T5 is measured,
    # and well measured -- it is the refusal to compare a number with the five numbers it
    # is not commensurate with.
    #
    # What T5 does contribute is `t5_anomaly`, its departure from that line, and that is a
    # measurement no other date can make. The 63 mm of rain in the three days before the
    # pass is a natural soil-moisture experiment applied to all 966 plots at once: a plot
    # whose soil is exposed responds to it, and a plot still under closed canopy is
    # decoupled from it. So the confound that makes T5's level unusable is also what makes
    # its residual a soil-exposure -- that is, a harvest -- indicator. Whether it actually
    # works is tested in `feature_audit`, not assumed here.
    i5, i4, i6 = DATE_ORDER.index("T5"), DATE_ORDER.index("T4"), DATE_ORDER.index("T6")
    w = (DOY["T5"] - DOY["T4"]) / (DOY["T6"] - DOY["T4"])
    t5_line = filled[:, i4] + w * (filled[:, i6] - filled[:, i4])
    df["t5_measured_db"] = filled[:, i5]
    df["t5_interp_db"] = t5_line
    df["t5_anomaly"] = filled[:, i5] - t5_line
    filled[:, i5] = t5_line

    for j, code in enumerate(DATE_ORDER):
        df[f"g0_db_filled_{code}"] = filled[:, j]

    # --- temporal descriptors ------------------------------------------------------
    # X-band saturates at canopy closure, so peak magnitude around T3 is exactly where
    # crops are least separable. The discriminating information is in the shoulder
    # seasons -- hence slopes, curvature and peak timing rather than levels alone.
    #
    # The first block is Round 2's, unchanged and computed from the same four dates, so
    # every Round 2 result stays reproducible from this frame and the six-date versions
    # can be compared against it rather than replacing it silently.
    t1, t2, t3, t4, _t5_line, t6 = (filled[:, j] for j in range(6))
    df["slope_early"] = (t3 - t1) / (DOY["T3"] - DOY["T1"])
    df["slope_late"] = (t4 - t3) / (DOY["T4"] - DOY["T3"])
    df["slope_emerge"] = (t2 - t1) / (DOY["T2"] - DOY["T1"])
    df["curvature"] = t1 - 2.0 * t3 + t4
    df["flood_depth"] = np.minimum(t1, t2) - t3

    # Whole-stack descriptors. These change meaning against Round 2 because they now span
    # June to November rather than June to October: `peak_idx` runs 0..5, and `auc`
    # integrates the entire season instead of stopping two months before harvest.
    df["dynamic_range"] = filled.max(axis=1) - filled.min(axis=1)
    df["peak_idx"] = filled.argmax(axis=1)
    df["mean_db"] = filled.mean(axis=1)
    # np.trapz was renamed np.trapezoid in NumPy 2.0; Kaggle's image may predate that.
    trapz = getattr(np, "trapezoid", None) or np.trapz
    df["auc"] = trapz(filled, doys, axis=1) / (doys[-1] - doys[0])

    # --- what the two new acquisitions add -----------------------------------------
    # The late-season limb is the whole reason Round 3 can forecast where Round 2 could
    # only report. T4 (13 Oct) was Round 2's last look and caught most crops still
    # standing; T6 (12 Nov) is after most kharif harvest in central Gujarat.
    df["slope_harvest"] = (t6 - t4) / (DOY["T6"] - DOY["T4"])
    df["late_drop"] = t4 - t6
    df["end_level"] = t6
    df["end_departure"] = t6 - np.maximum(t1, t2)   # is the field back to its own bare soil?


    mem = None
    return df


if __name__ == "__main__":
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    work = os.path.join(root, "work")
    frame = build(os.path.join(work, "gamma0"))
    # CSV rather than parquet: GDAL and pyarrow both register a "file" filesystem
    # factory in the same process and collide. The table is 966 rows -- CSV costs
    # nothing and keeps the deliverable notebook dependency-light.
    out = os.path.join(work, "farm_features.csv")
    frame.to_csv(out, index=False)

    print(f"{len(frame)} farms -> {out}")
    print("\ndata quality:")
    print(frame["data_quality"].value_counts().to_string())
    print(f"\ncore pixels: median {int(frame.core_px.median())}, "
          f"p10 {int(frame.core_px.quantile(0.1))}, "
          f"below {MIN_CORE_PX}px: {int(frame.core_px_low.sum())} farms")
    print(f"erosion applied: median {frame.erode_m.median():.2f} m, "
          f"max {frame.erode_m.max():.2f} m")
    print("\nfarm-mean gamma0 (dB) by date:")
    for code in DATE_ORDER:
        col = frame[f"g0_db_{code}"].dropna()
        print(f"  {code}  n={len(col):3d}  p10={col.quantile(.1):6.2f}  "
              f"median={col.median():6.2f}  p90={col.quantile(.9):6.2f}")
    print("\nspeckle check — CoV should sit near 1.0 for single-look uniform fields:")
    for code in DATE_ORDER:
        col = frame[f"cov_{code}"].dropna()
        print(f"  {code}  CoV median={col.median():.3f}   "
              f"ENL median={frame[f'enl_{code}'].median():.2f}")
