"""Shipped tables for Round 3: the plot forecast, the village rollup, and the zone grid.

Round 3 is judged against a rubric rather than a leaderboard, so there is no prescribed
submission schema and no `sample_submission.csv` to match. That removes a constraint and
adds an obligation: the columns are ours to choose, so they have to be the ones that let a
judge check the work rather than the smallest set that satisfies a parser.

`farm_forecast.csv` therefore carries the forecast **and the chain that produced it** --
the crop label with its confidence, the canopy peak and its date, how much of the season
was cleared by the last pass, the season integral, the cohort-centred response that
integral maps to, the reference yield it multiplies, and the fraction of the answer that is
projected rather than observed. Every one of those is a term in the model and every one is
auditable per plot.

Three things are worth stating rather than burying.

`village_id`. The distributed shapefiles carry **22** in both `Sokhda_Farms.shp` (`ID_1`)
and `Sokhda_Village.shp` (`ID`). The value from the data wins.

The rollup is **verified against the village geometry, not just grouped by its name**.
`village_containment` intersects every plot polygon with every polygon in `Sokhda_Village.shp`
and assigns each plot to the village it shares the most area with, then requires that
geometric assignment to equal the `VILLAGE` attribute on all 966 rows. A groupby on a text
column is not an aggregation argument -- it is an aggregation assumption -- and the village
shapefile is shipped precisely so it can be checked. The same function reports what fraction
of the village polygon the digitised parcels actually cover, which is the number that says
whether a village total is a village total or a sample of one.

Weighting. Sokhda's farms run up to 3.49 ha with a median of 0.27 ha, and ten parcels have
degenerate geometry enclosing effectively no ground, so a plain per-farm mean would weight
a 0.02 ha plot the same as a 3.5 ha one. Every aggregate here is **area-weighted in
hectares**, and production is the true sum `sum(yield * area)` rather than a mean of
ratios.

The schema gate raises on every failure. Nothing in `validate` is a warning, and the column
check is full equality against `REQUIRED`, not a prefix match -- Round 2 used a prefix check
and it let a stray column through to a shipped file.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
from osgeo import ogr, osr

from farm_features import FARM_SHP, VILLAGE_SHP, _utm_srs

CROPS = ["Rice", "Cotton", "Maize", "Bajra", "Groundnut"]
N_FARMS = 966

REQUIRED = [
    "village_id", "village_name", "farm_id", "area_ha",
    "crop_type", "crop_confidence", "crop_margin", "long_duration_flag",
    "data_quality", "n_valid_dates",
    "has_canopy", "canopy_peak_db", "canopy_peak_doy", "canopy_end_db", "cleared_fraction",
    "season_integral_db", "extrapolated_fraction",
    "accumulation_response", "yield_ref_t_ha", "yield_forecast_t_ha", "production_t",
]

# Plausibility band, t/ha, duplicated from yield_forecast on purpose: this gate runs on the
# file that ships, not on the frame in memory that produced it, so it must not import its
# bound from the module it is checking.
PLAUSIBLE_T_HA = {"Rice": (0.5, 7.0), "Maize": (0.5, 9.0), "Bajra": (0.3, 4.0),
                  "Groundnut": (0.3, 5.0), "Cotton": (0.3, 4.0)}

# Sub-zone edge, metres. Sokhda's parcels span ~4.7 x 5.9 km, so 500 m gives enough cells
# to show a gradient while keeping most of them above MIN_ZONE_FARMS. See `zone_summary`.
ZONE_M = 500.0
MIN_ZONE_FARMS = 5

# A parcel may sit outside the village polygon only if it encloses no measurable ground.
# 1e-6 ha is the same degenerate-geometry threshold `yield_forecast` reports against, and
# ten of these parcels fall under it.
OUTSIDE_AREA_TOL_HA = 1e-6


ROUND = 4


def round_shipped(df: pd.DataFrame) -> pd.DataFrame:
    """Round once, before anything is aggregated.

    Rounding the plot table after computing the village totals from full precision makes
    the two disagree in the fourth decimal, and `cross_check` catches it -- correctly, since
    a judge summing the shipped CSV would get a different number from the shipped summary.
    Rounding first makes the village row literally the sum of the file that ships.
    """
    out = df.copy()
    for c in ("area_ha", "crop_margin", "canopy_peak_db", "canopy_end_db",
              "cleared_fraction", "season_integral_db", "extrapolated_fraction",
              "accumulation_response", "yield_ref_t_ha", "yield_forecast_t_ha"):
        out[c] = out[c].round(ROUND)
    out["production_t"] = (out.yield_forecast_t_ha * out.area_ha).round(ROUND)
    return out


def farm_forecast(df: pd.DataFrame) -> pd.DataFrame:
    """The 966-row plot table, in `REQUIRED` order."""
    return df[REQUIRED].sort_values("farm_id").reset_index(drop=True)


def village_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Per-crop village aggregate, area-weighted, plus an ALL row."""
    def row(sub, crop):
        area = sub.area_ha.sum()
        return {
            "village_id": int(sub.village_id.iloc[0]),
            "village_name": sub.village_name.iloc[0],
            "crop_type": crop,
            "n_farms": len(sub),
            "area_ha": area,
            "area_share": area / df.area_ha.sum(),
            "yield_ref_t_ha": float(sub.yield_ref_t_ha.iloc[0]) if crop != "ALL" else np.nan,
            "yield_t_ha_area_wt": float(np.average(sub.yield_forecast_t_ha,
                                                   weights=sub.area_ha)),
            "yield_t_ha_p10": float(sub.yield_forecast_t_ha.quantile(0.10)),
            "yield_t_ha_p90": float(sub.yield_forecast_t_ha.quantile(0.90)),
            "production_t": float(sub.production_t.sum()),
            "extrapolated_fraction_area_wt": float(np.average(sub.extrapolated_fraction,
                                                              weights=sub.area_ha)),
            "high_confidence_share": float(
                sub.area_ha[sub.crop_confidence == "high"].sum() / area),
        }

    rows = [row(sub, crop) for crop, sub in df.groupby("crop_type")]
    rows.append(row(df, "ALL"))
    return pd.DataFrame(rows)


def zone_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Within-village spatial breakdown on a fixed grid.

    The study area is a single village, so the required village table is ONE row: it
    reports a total and carries no spatial information at all, which is the one thing an
    aggregation is supposed to provide. Partitioning the village into fixed cells and
    aggregating each the same way -- area-weighted yield, production as a true sum -- puts
    the spatial variation back where a district officer can act on it, and it is the same
    arithmetic at a smaller scale rather than a second method that could disagree with the
    village row.

    Cells below `MIN_ZONE_FARMS` are dropped from the reported table rather than shown as
    noisy one-farm 'zones'; the count dropped is printed so the coverage is visible. Zone
    labels come from parcel centroids already carried in the farm table, so no new geometry
    is introduced.
    """
    d = df.copy()
    zx = np.floor((d.cx - d.cx.min()) / ZONE_M).astype(int)
    zy = np.floor((d.cy - d.cy.min()) / ZONE_M).astype(int)
    d["zone"] = [f"Z{a}{b}" for a, b in zip(zx, zy)]

    rows = []
    for zone, sub in d.groupby("zone"):
        rows.append({
            "zone": zone,
            "n_farms": len(sub),
            "area_ha": sub.area_ha.sum(),
            "yield_t_ha_area_wt": float(np.average(sub.yield_forecast_t_ha,
                                                   weights=sub.area_ha)),
            "production_t": float(sub.production_t.sum()),
            "dominant_crop": sub.groupby("crop_type").area_ha.sum().idxmax(),
            # NaN is the right answer for a cell where nothing grew a canopy, but taking
            # it through pandas' median raises a numpy empty-slice warning on the way, so
            # the empty case is handled here instead of being caught downstream.
            "cleared_fraction_median": (float(sub.cleared_fraction.median())
                                        if sub.cleared_fraction.notna().any() else np.nan),
            "measured_share": float((sub.data_quality != "imputed").mean()),
        })
    out = pd.DataFrame(rows).sort_values("yield_t_ha_area_wt").reset_index(drop=True)
    return out[out.n_farms >= MIN_ZONE_FARMS].reset_index(drop=True)


def validate(sub: pd.DataFrame) -> None:
    """Hard schema gate on the shipped plot table. Every failure raises."""
    if list(sub.columns) != REQUIRED:
        missing = set(REQUIRED) - set(sub.columns)
        extra = set(sub.columns) - set(REQUIRED)
        raise ValueError(f"columns must be exactly {REQUIRED}; missing={missing} extra={extra}")
    if len(sub) != N_FARMS:
        raise ValueError(f"{len(sub)} rows, expected {N_FARMS}")
    if sub.farm_id.duplicated().any():
        raise ValueError("duplicate farm_id")
    if sorted(sub.farm_id) != list(range(1, N_FARMS + 1)):
        raise ValueError("farm_id is not 1..966")
    # Two columns are nullable and their null pattern is not a gap in the data. A plot that
    # never rose MIN_CANOPY_DB above its own bare soil has no canopy episode, so there is
    # nothing for a clearing fraction to be a fraction OF and no date for a peak that does
    # not exist. Writing 0.0 into `cleared_fraction` would say "nothing was cleared", which
    # is a claim, and 1.0 would say "everything was". The gate asserts the pattern exactly
    # rather than tolerating NaN anywhere.
    nullable = ["cleared_fraction", "canopy_peak_doy"]
    expected_null = ~sub.has_canopy.astype(bool)
    for c in nullable:
        if not sub[c].isna().equals(expected_null):
            raise ValueError(f"{c} is null on a different set of plots than ~has_canopy")
    solid = [c for c in REQUIRED if c not in nullable]
    if sub[solid].isna().any().any():
        bad = sub[solid].columns[sub[solid].isna().any()].tolist()
        raise ValueError(f"NaN in {bad}")
    num = sub[solid].select_dtypes("number")
    if not np.isfinite(num.to_numpy()).all():
        raise ValueError("Inf in a numeric column")
    bad = set(sub.crop_type.unique()) - set(CROPS)
    if bad:
        raise ValueError(f"crop_type outside the permitted five: {bad}")
    if not sub.extrapolated_fraction.between(0, 1).all():
        raise ValueError("extrapolated_fraction outside 0-1")
    if not sub.cleared_fraction.dropna().between(0, 1).all():
        raise ValueError("cleared_fraction outside 0-1")
    lo = sub.crop_type.map(lambda c: PLAUSIBLE_T_HA[c][0])
    hi = sub.crop_type.map(lambda c: PLAUSIBLE_T_HA[c][1])
    if not ((sub.yield_forecast_t_ha >= lo) & (sub.yield_forecast_t_ha <= hi)).all():
        raise ValueError("a forecast is outside its crop's plausible band")


def cross_check(farms: pd.DataFrame, village: pd.DataFrame, tol: float = 1e-6) -> None:
    """The village table must be reconstructible from the plot table. Raises if it is not."""
    allrow = village[village.crop_type == "ALL"].iloc[0]
    if abs(farms.production_t.sum() - allrow.production_t) > tol:
        raise ValueError(f"village ALL production {allrow.production_t} != plot sum "
                         f"{farms.production_t.sum()}")
    if abs(farms.area_ha.sum() - allrow.area_ha) > tol:
        raise ValueError("village ALL area does not match the plot sum")
    per = farms.groupby("crop_type").production_t.sum()
    for crop, p in per.items():
        got = float(village.loc[village.crop_type == crop, "production_t"].iloc[0])
        if abs(got - p) > tol:
            raise ValueError(f"{crop}: village {got} != plot sum {p}")


# Point and line types have no area, and `OGR_G_Area()` warns when asked for one. The
# intersection of a degenerate parcel with a boundary is exactly that -- a point or an empty
# geometry -- so the guard is on the type, not on a caught exception. Kaggle printed three
# `OGR_G_Area() called against non-surface geometry type` lines before this existed, and a
# warning a judge has to interpret is a defect even when the value it returns is right.
_AREALESS = {ogr.wkbPoint, ogr.wkbMultiPoint, ogr.wkbLineString, ogr.wkbMultiLineString,
             ogr.wkbLinearRing, ogr.wkbNone}


def _area(geom) -> float:
    """Area in the geometry's own units, or 0.0 for a type that cannot have one."""
    if geom is None or geom.IsEmpty():
        return 0.0
    return 0.0 if ogr.GT_Flatten(geom.GetGeometryType()) in _AREALESS else geom.GetArea()


def village_containment() -> dict:
    """Assign every plot to a village by geometry and check it against the attribute.

    Every borrowed OGR geometry is `.Clone()`d before use. A borrowed reference that
    outlives its feature survives locally and segfaults on Kaggle with no traceback, and
    thirteen of these parcels are MULTIPOLYGON, which is where it bites first.

    Assignment is by largest shared area rather than centroid-in-polygon: a plot on the
    village edge can have its centroid outside the boundary while most of its ground is
    inside, and ten parcels enclose effectively no area at all, for which every intersection
    is zero and a centroid test is the only thing left. Both cases are counted and printed
    rather than smoothed over.
    """
    # Both shapefiles are geographic. Areas are computed in UTM 43N, the same projection
    # every other area in this pipeline uses, or `GetArea` returns square degrees and every
    # comparison below is meaningless while still printing a number.
    tsrs = _utm_srs()

    def _to_utm(layer):
        ssrs = layer.GetSpatialRef()
        ssrs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        return osr.CoordinateTransformation(ssrs, tsrs)

    vsrc = ogr.Open(VILLAGE_SHP)
    vlayer = vsrc.GetLayer()
    vtx = _to_utm(vlayer)
    villages = []
    for feat in vlayer:
        g = feat.GetGeometryRef().Clone()
        g.Transform(vtx)
        villages.append((feat.GetField("VILLAGE"), int(feat.GetField("ID")), g))

    fsrc = ogr.Open(FARM_SHP)
    flayer = fsrc.GetLayer()
    ftx = _to_utm(flayer)
    n_agree = n_disagree = n_by_centroid = n_outside = 0
    farm_area = inside_area = outside_area = 0.0
    for feat in flayer:
        geom = feat.GetGeometryRef().Clone()
        geom.Transform(ftx)
        attr = feat.GetField("VILLAGE")
        farm_area += _area(geom)

        shares = [(_area(g.Intersection(geom)), name) for name, _, g in villages]
        best_area, best = max(shares)
        if best_area <= 0.0:
            # Degenerate parcel: no measurable intersection with anything. Fall back to the
            # centroid, which is the only geometric statement such a polygon still supports.
            n_by_centroid += 1
            centroid = geom.Centroid()
            hits = [name for name, _, g in villages if g.Contains(centroid)]
            best = hits[0] if hits else None
        inside_area += best_area
        if best is None:
            n_outside += 1
            outside_area += _area(geom)
        elif best == attr:
            n_agree += 1
        else:
            n_disagree += 1

    village_area = sum(_area(g) for _, _, g in villages)
    return {"n_villages": len(villages),
            "village_names": [name for name, _, _ in villages],
            "n_farms": n_agree + n_disagree + n_outside,
            "n_agree": n_agree, "n_disagree": n_disagree,
            "n_by_centroid": n_by_centroid, "n_outside": n_outside,
            "farm_area_ha": farm_area / 1e4,
            "inside_area_ha": inside_area / 1e4,
            "outside_area_ha": outside_area / 1e4,
            "village_area_ha": village_area / 1e4}


def report_containment(c: dict) -> None:
    """Print the geometric rollup check. Raises if the geometry contradicts the attribute."""
    print("\nthe village rollup, checked against the village polygon rather than the "
          "village name")
    print(f"  Sokhda_Village.shp holds {c['n_villages']} polygon(s): "
          + ", ".join(c["village_names"]))
    print(f"  {c['n_agree']} of {c['n_farms']} plots assign to the same village by largest "
          f"shared area as by attribute")
    print(f"  {c['n_disagree']} disagree; {c['n_outside']} intersect no village polygon at "
          f"all ({c['outside_area_ha']:.4f} ha)")
    print(f"  {c['n_by_centroid']} degenerate parcels had zero intersection with every "
          f"polygon and were placed by centroid")
    print(f"  parcel area inside the boundary {c['inside_area_ha']:.1f} ha of "
          f"{c['farm_area_ha']:.1f} ha digitised "
          f"({100 * c['inside_area_ha'] / c['farm_area_ha']:.2f} %)")
    print(f"  the village polygon encloses {c['village_area_ha']:.1f} ha, so the digitised "
          f"parcels are {100 * c['farm_area_ha'] / c['village_area_ha']:.1f} % of Sokhda")
    print("  The village total is therefore a total over the mapped farmland of one village,\n"
          "  not over the village's whole area. Everything outside these parcels -- the "
          "built-up core,\n  roads, water, and any undigitised field -- is not forecast and "
          "is not claimed.")
    # The gate is on ground, not on row counts. A plot whose geometry says one village and
    # whose attribute says another would make the rollup wrong, and so would a parcel of real
    # size sitting outside the boundary. A parcel enclosing no measurable area cannot be
    # placed by any geometric test and is already declared in the degenerate-geometry count;
    # it carries a row, it carries no weight, and it is named here rather than hidden.
    if c["n_disagree"] or c["outside_area_ha"] > OUTSIDE_AREA_TOL_HA:
        raise ValueError(
            f"village rollup is not geometrically sound: {c['n_disagree']} plots disagree "
            f"with their VILLAGE attribute and {c['outside_area_ha']:.4f} ha lies outside "
            f"every village polygon. The village_summary groupby would include them anyway.")


def run(forecast_csv: str) -> tuple:
    # The geometric check runs FIRST, before anything is written. It is a gate, not a
    # report: if the plot geometry and the village attribute disagree, every table below is
    # aggregating over the wrong set and there is no point producing it.
    report_containment(village_containment())
    df = round_shipped(pd.read_csv(forecast_csv))
    farms = farm_forecast(df)
    validate(farms)
    village = village_summary(df)
    cross_check(farms, village)
    return farms, village, zone_summary(df)


def report(farms: pd.DataFrame, village: pd.DataFrame, zones: pd.DataFrame) -> None:
    print(f"\nfarm_forecast.csv  {len(farms)} rows x {len(farms.columns)} columns, "
          f"schema gate PASSED, village table reconstructs from it")
    print(farms.head(3).to_string(index=False))

    print("\nvillage aggregate by crop (area-weighted; production is the true sum):")
    print(village.to_string(index=False, float_format=lambda v: f"{v:.3f}"))

    print(f"\nwithin-village breakdown -- {len(zones)} sub-zones of {ZONE_M:.0f} m carrying "
          f"at least {MIN_ZONE_FARMS} farms")
    print("A single-village study area makes the required village table one row. This is "
          "where the\nspatial variation actually lives, and it is the same area-weighted "
          "arithmetic at a smaller scale.")
    print(zones.to_string(index=False, float_format=lambda v: f"{v:.2f}"))
    lo, hi = zones.yield_t_ha_area_wt.min(), zones.yield_t_ha_area_wt.max()
    vill = float(village.loc[village.crop_type == "ALL", "yield_t_ha_area_wt"].iloc[0])
    print(f"\nyield spread across sub-zones: {lo:.2f} to {hi:.2f} t/ha "
          f"({hi - lo:.2f} t/ha, against a village figure of {vill:.2f})")
    print(f"covered: {int(zones.n_farms.sum())}/{len(farms)} farms, "
          f"{zones.area_ha.sum():.1f}/{farms.area_ha.sum():.1f} ha; the rest sit in cells "
          f"below the {MIN_ZONE_FARMS}-farm floor")


if __name__ == "__main__":
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = os.path.join(root, "outputs")
    os.makedirs(out, exist_ok=True)
    farms, village, zones = run(os.path.join(root, "work", "farm_forecast_raw.csv"))
    farms.to_csv(os.path.join(out, "farm_forecast.csv"), index=False)
    village.to_csv(os.path.join(out, "village_summary.csv"), index=False)
    zones.to_csv(os.path.join(out, "zone_summary.csv"), index=False)
    report(farms, village, zones)
