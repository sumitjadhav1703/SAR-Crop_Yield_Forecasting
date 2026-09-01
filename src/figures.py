"""Figures for the media gallery and the write-up.

Every figure is drawn from a delivered artefact -- `outputs/farm_forecast.csv`,
`outputs/village_summary.csv`, `outputs/zone_summary.csv`, the farm shapefile -- so a
figure cannot disagree with the numbers that ship. Where a panel needs a quantity that is
upstream of the shipped table (the raw gamma0 stack, the NDVI joins), it merges the work
table onto the shipped one by `farm_id` and the shipped column always wins.

Nothing here recomputes a forecast, a total, or a correlation that a module already
computed and printed. Round 2 was caught three times printing a number in the write-up that
no cell produced; the fix is that figures read files rather than re-derive.
"""

from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.collections import PatchCollection
from matplotlib.patches import Polygon as MplPolygon
from packaging.version import Version
from osgeo import gdal, ogr, osr

from farm_features import FARM_SHP, VILLAGE_SHP
import geocode
import scene_diagnostics
from geocode import TARGET_EPSG

CROPS = ["Rice", "Cotton", "Maize", "Bajra", "Groundnut"]
CROP_COLOURS = {"Rice": "#2c7fb8", "Cotton": "#b8860b", "Maize": "#d95f02",
                "Bajra": "#7570b3", "Groundnut": "#1b9e77"}
DATES = ["T1", "T2", "T3", "T4", "T5", "T6"]
DATE_LABELS = {"T1": "6 Jun", "T2": "19 Jun", "T3": "14 Aug", "T4": "13 Oct",
               "T5": "29 Oct", "T6": "12 Nov"}
# Incidence angle per collect. Worth carrying onto the trajectory figure: T1 is 6.5 deg
# steeper than T2/T3, which is the largest geometry change in the stack and the reason the
# T1->T2 "emergence" slope was dropped from the crop descriptors.
DATE_INCIDENCE = {"T1": 35.24, "T2": 28.77, "T3": 28.69, "T4": 31.53,
                  "T5": 29.84, "T6": 29.75}
DOY = [157, 170, 226, 286, 302, 316]
DOY_OF = dict(zip(DATES, DOY))

# The two dates that define each plot's own bare-soil reference, and the three that can
# carry a canopy. T5's level is not measured -- `farm_features` replaces it with the T4-T6
# interpolation -- so it is drawn as an open marker wherever a level appears.
ANCHOR_DATES = ["T1", "T2"]
CANOPY_DATES = ["T3", "T4", "T6"]
INTERPOLATED = ["T5"]

FOOTER = ("EPSG:32643 (UTM 43N) · Capella C14 stripmap HH SLC → $\\gamma^0$, "
          "RPC-geocoded to 1 m · farm boundaries as supplied")


def _transform_to_utm(layer):
    ssrs = layer.GetSpatialRef()
    ssrs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    tsrs = osr.SpatialReference()
    tsrs.ImportFromEPSG(TARGET_EPSG)
    tsrs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return osr.CoordinateTransformation(ssrs, tsrs)


def _rings(geom) -> list:
    """Exterior rings of a polygon or multipolygon, as vertex arrays in map units.

    Same borrowed-reference hazard as `farm_patches`: `GetGeometryRef(i)` hands back a
    pointer owned by the parent, so every child is cloned before the parent can fall out of
    scope.
    """
    if geom.GetGeometryName() == "MULTIPOLYGON":
        parts = [geom.GetGeometryRef(i).Clone() for i in range(geom.GetGeometryCount())]
    else:
        parts = [geom.Clone()]
    out = []
    for part in parts:
        ring = part.GetGeometryRef(0)
        out.append(np.array([[ring.GetX(i), ring.GetY(i)]
                             for i in range(ring.GetPointCount())]))
    return out


def village_outline() -> list:
    """Sokhda's administrative boundary in UTM 43N.

    The farm polygons alone float in white space, which reads as a point cloud rather than a
    village. The boundary is what makes the maps legible as a place, and it also shows how
    much of the village is unparcelled -- 447.5 ha of farms inside a ~1,080 ha polygon.
    """
    src = ogr.Open(VILLAGE_SHP)
    layer = src.GetLayer()
    tr = _transform_to_utm(layer)
    out = []
    for feat in layer:
        geom = feat.GetGeometryRef().Clone()
        geom.Transform(tr)
        out.extend(_rings(geom))
    return out


def farm_patches() -> tuple:
    """Farm polygons as matplotlib patches, in UTM 43N, keyed by FID."""
    src = ogr.Open(FARM_SHP)
    layer = src.GetLayer()
    ssrs = layer.GetSpatialRef()
    ssrs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    tsrs = osr.SpatialReference()
    tsrs.ImportFromEPSG(TARGET_EPSG)
    tsrs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    tr = osr.CoordinateTransformation(ssrs, tsrs)

    patches, ids = [], []
    for feat in layer:
        geom = feat.GetGeometryRef().Clone()
        geom.Transform(tr)
        # Some parcels are digitised as MultiPolygon. Drawing needs one outline per farm,
        # so take the largest part; the statistics upstream used the full geometry, and
        # this only affects the picture.
        #
        # The Clone() is load-bearing, not defensive. `GetGeometryRef(i)` returns a
        # *borrowed* reference owned by the parent geometry. Rebinding `geom` to the child
        # drops the last Python reference to the parent, GDAL frees it, and the child
        # pointer is left dangling -- the next `GetGeometryRef(0)` then reads freed memory.
        # That is undefined behaviour: it happened to survive locally and killed the Kaggle
        # kernel outright, with no traceback, which is exactly how a segfault presents.
        if geom.GetGeometryName() == "MULTIPOLYGON":
            parts = [geom.GetGeometryRef(i) for i in range(geom.GetGeometryCount())]
            geom = max(parts, key=lambda g: g.GetArea()).Clone()
        ring = geom.GetGeometryRef(0)
        pts = np.array([[ring.GetX(i), ring.GetY(i)] for i in range(ring.GetPointCount())])
        patches.append(MplPolygon(pts, closed=True))
        ids.append(int(feat.GetField("FID")))
    return patches, np.array(ids)


def _map_axes(ax, frame: bool = True) -> None:
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for side in ax.spines.values():
        side.set_visible(frame)
        if frame:
            side.set_linewidth(0.8)
            side.set_color("#444444")


def _draw_village(ax, outline, label: bool = True) -> None:
    for ring in outline:
        ax.plot(ring[:, 0], ring[:, 1], color="#333333", linewidth=1.1,
                linestyle=(0, (6, 3)), zorder=5)
    if label and outline:
        # A proxy handle rather than an in-map annotation: the boundary's top edge is where
        # the statistics box wants to sit, and the two collided.
        proxy = plt.Line2D([], [], color="#333333", linewidth=1.1, linestyle=(0, (6, 3)))
        leg = ax.legend([proxy], ["Sokhda village boundary"], loc="lower right",
                        frameon=True, fontsize=7.5, handlelength=2.4, borderpad=0.5)
        leg.get_frame().set_edgecolor("#cccccc")
        leg.get_frame().set_linewidth(0.6)
        leg.set_zorder(8)


def _scale_bar(ax, frac: float = 0.24) -> None:
    """Metric scale bar. Exact, because the map is in UTM metres, not degrees."""
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    target = (x1 - x0) * frac
    mag = 10.0 ** np.floor(np.log10(target))
    length = min([m * mag for m in (1, 2, 5, 10)],
                 key=lambda v: abs(v - target) if v <= target * 1.5 else 1e18)
    bx = x0 + (x1 - x0) * 0.04
    by = y0 + (y1 - y0) * 0.045
    h = (y1 - y0) * 0.008
    # Two alternating blocks, the usual convention -- reads as a scale bar at thumbnail size
    # where a plain line reads as a stray annotation.
    for i, colour in enumerate(("#222222", "#ffffff")):
        ax.add_patch(plt.Rectangle((bx + i * length / 2, by), length / 2, h,
                                   facecolor=colour, edgecolor="#222222",
                                   linewidth=0.6, zorder=7))
    text = f"{length / 1000:g} km" if length >= 1000 else f"{length:g} m"
    ax.text(bx + length / 2, by + h * 1.9, text, ha="center", va="bottom",
            fontsize=7.5, color="#222222", zorder=7)


def _north_arrow(ax) -> None:
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    x = x0 + (x1 - x0) * 0.955
    y = y0 + (y1 - y0) * 0.90
    d = (y1 - y0) * 0.055
    ax.annotate("", xy=(x, y + d), xytext=(x, y),
                arrowprops=dict(arrowstyle="-|>", color="#222222", linewidth=1.1), zorder=7)
    ax.text(x, y - d * 0.35, "N", ha="center", va="top", fontsize=8.5,
            color="#222222", zorder=7)


def _stats_box(ax, lines: list, loc: str = "upper left") -> None:
    x, ha = (0.015, "left") if "left" in loc else (0.985, "right")
    y, va = (0.985, "top") if "upper" in loc else (0.015, "bottom")
    ax.text(x, y, "\n".join(lines), transform=ax.transAxes, ha=ha, va=va,
            fontsize=7.5, linespacing=1.5, zorder=8,
            bbox=dict(boxstyle="round,pad=0.45", facecolor="white", alpha=0.88,
                      edgecolor="#bbbbbb", linewidth=0.6))


def _pad_to_16x9(fig) -> None:
    """Grow the canvas to 16:9 without moving anything on it.

    Kaggle's Writeup gallery crops every image to ~16:9 for the thumbnail and the page
    viewer, and it crops the SIDES to get there. Four figures here are 2.18-2.40:1 -- wide
    two- and three-panel layouts -- so the crop cut the right-hand edge off, which on
    `backtest` removed the annotation box stating that the shipped rule does not beat
    persistence. Losing the negative result to a thumbnail crop is the worst possible thing
    to lose.

    The fix is padding, not re-layout. These four have hand-tuned `subplots_adjust` margins
    and header text sized against a specific canvas, and re-tuning all of them two days from
    a deadline is how a working figure gets broken. So the canvas grows to 16:9 and every
    margin and every text is rescaled to hold its position in ABSOLUTE inches: the drawing is
    pixel-for-pixel what it was, with white space added above and below.

    Figure-fraction text is anchored to whichever edge it sits nearer. That is a heuristic,
    and it is the right one here because every `fig.text` in these figures is either the
    header block just under the title or the `_footer` credit line -- nothing floats in the
    middle. Check the render if that ever stops being true.
    """
    w, h = fig.get_size_inches()
    target = w * 9.0 / 16.0
    if h >= target - 1e-6:
        return
    scale = h / target
    sp = fig.subplotpars
    for t in fig.texts:
        x, y = t.get_position()
        t.set_position((x, 1.0 - (1.0 - y) * scale if y > 0.5 else y * scale))
    fig.set_size_inches(w, target)
    fig.subplots_adjust(left=sp.left, right=sp.right,
                        top=1.0 - (1.0 - sp.top) * scale, bottom=sp.bottom * scale,
                        wspace=sp.wspace, hspace=sp.hspace)


def _footer(fig, extra: str = "") -> None:
    fig.text(0.5, 0.012, FOOTER + (f" · {extra}" if extra else ""),
             ha="center", fontsize=6.5, color="#777777")


def _flag_imputed(ax, df: pd.DataFrame, patches, ids) -> int:
    """Outline the farms whose values were filled rather than measured.

    71 farms were never covered by the swath and are filled from their nearest valid
    neighbours. They carry `data_quality` in the CSV, but a reader of the map cannot see
    which colours are measurements -- so they are hatched here rather than left to blend in.
    """
    if "data_quality" not in df:
        return 0
    q = df.set_index("farm_id").loc[ids, "data_quality"].to_numpy()
    sel = np.flatnonzero(q != "measured")
    if len(sel):
        ax.add_collection(PatchCollection([patches[i] for i in sel], facecolor="none",
                                          edgecolor="#333333", linewidth=0.45,
                                          hatch="////", zorder=4))
    return int(len(sel))


def _draw_choropleth(ax, df: pd.DataFrame, patches, ids, column: str,
                     cmap: str = "RdYlGn", vmin=None, vmax=None, outline=None,
                     furniture: bool = True):
    """Shade the farm polygons by one column. Returns the collection, for the colorbar.

    Axes-level so the standalone figure and the cover panel draw from one implementation
    and cannot drift apart.
    """
    order = df.set_index("farm_id").loc[ids, column].to_numpy(dtype=float)
    pc = PatchCollection(patches, cmap=cmap, edgecolor="white", linewidth=0.15)
    pc.set_array(order)
    pc.set_clim(vmin if vmin is not None else np.nanmin(order),
                vmax if vmax is not None else np.nanmax(order))
    ax.add_collection(pc)
    if outline:
        _draw_village(ax, outline, label=furniture)
    ax.autoscale_view()
    _map_axes(ax)
    if furniture:
        _scale_bar(ax)
        _north_arrow(ax)
    return pc


def _colorbar_with_histogram(fig, ax, pc, values, label: str) -> None:
    """Colorbar carrying the distribution of the values it encodes.

    A bare ramp says what the colours mean; it does not say how many farms sit at each end.
    Overlaying the histogram makes the map and its distribution one object, so a reader
    cannot misjudge a long tail as a typical value.
    """
    cax = ax.inset_axes([1.03, 0.06, 0.032, 0.84])
    cb = fig.colorbar(pc, cax=cax)
    # Label above the ramp, not rotated beside it: the histogram sits immediately to the
    # right and a rotated label lands underneath it.
    cax.set_title(label, fontsize=8.5, pad=7, loc="left")
    cb.ax.tick_params(labelsize=8)

    lo, hi = pc.get_clim()
    v = values[np.isfinite(values)]
    counts, edges = np.histogram(v, bins=28, range=(lo, hi))
    hax = ax.inset_axes([1.105, 0.06, 0.075, 0.84])
    hax.barh((edges[:-1] + edges[1:]) / 2, counts, height=(edges[1] - edges[0]) * 0.92,
             color="#555555", linewidth=0)
    hax.set_ylim(lo, hi)
    hax.set_xlim(0, counts.max() * 1.08 if counts.max() else 1)
    hax.set_yticks([])
    hax.set_xticks([])
    hax.patch.set_alpha(0.0)
    for side in ("top", "right", "bottom"):
        hax.spines[side].set_visible(False)
    hax.spines["left"].set_color("#bbbbbb")
    hax.text(0.5, -0.018, f"n = {len(v)}", transform=hax.transAxes, ha="center",
             va="top", fontsize=6.8, color="#777777")


def choropleth(df: pd.DataFrame, patches, ids, column: str, title: str, path: str,
               cmap: str = "RdYlGn", vmin=None, vmax=None, label: str = "",
               outline=None, subtitle: str = "", stats: list = None,
               fmt: str = "{:.1f}") -> None:
    fig, ax = plt.subplots(figsize=(13.2, 7.425))
    pc = _draw_choropleth(ax, df, patches, ids, column, cmap, vmin, vmax, outline)
    _flag_imputed(ax, df, patches, ids)

    v = df[column].to_numpy(dtype=float)
    ax.set_title(title, fontsize=13, pad=24 if subtitle else 8)
    if subtitle:
        ax.text(0.5, 1.018, subtitle, transform=ax.transAxes, ha="center", va="bottom",
                fontsize=8.5, color="#555555", wrap=True)
    _colorbar_with_histogram(fig, ax, pc, v, label or column)

    n_imp = int((df.data_quality != "measured").sum()) if "data_quality" in df else 0
    _stats_box(ax, (stats if stats is not None else []) + [
        f"min {fmt.format(np.nanmin(v))}   median {fmt.format(np.nanmedian(v))}   "
        f"max {fmt.format(np.nanmax(v))}",
        f"{len(df)} farms · {df.area_ha.sum():.1f} ha · hatched = {n_imp} filled, not measured",
    ])
    fig.tight_layout(rect=(0, 0.022, 0.9, 1))
    _footer(fig)
    fig.savefig(path, dpi=160)
    plt.close(fig)


def crop_map(df: pd.DataFrame, patches, ids, path: str, outline=None) -> None:
    crop = df.set_index("farm_id").loc[ids, "crop_type"]
    conf = df.set_index("farm_id").loc[ids, "crop_confidence"]
    fig, ax = plt.subplots(figsize=(13.2, 7.425))
    for name in CROPS:
        for confidence, alpha in (("high", 1.0), ("low", 0.42)):
            sel = np.flatnonzero((crop == name).to_numpy() & (conf == confidence).to_numpy())
            if not len(sel):
                continue
            ax.add_collection(PatchCollection(
                [patches[i] for i in sel], facecolor=CROP_COLOURS[name],
                edgecolor="white", linewidth=0.15, alpha=alpha))
    # label=False: this figure builds its own legend below, and `ax.legend` replaces rather
    # than appends, so the boundary is carried as an extra handle there instead.
    if outline:
        _draw_village(ax, outline, label=False)
    ax.autoscale_view()
    _map_axes(ax)
    _scale_bar(ax)
    _north_arrow(ax)

    ax.set_title("Crop type, Sokhda", fontsize=13, pad=26)
    ax.text(0.5, 1.018,
            "solid = tier 1, labelled by a physical threshold rule   ·   "
            "faded = tier 2, allocated on a ranking axis and flagged low-confidence",
            transform=ax.transAxes, ha="center", va="bottom", fontsize=8.5, color="#555555")

    # Legend carries the area and confidence split, so the map answers "how much of this is
    # actually known?" without a trip to the write-up.
    total = df.area_ha.sum()
    handles, labels = [], []
    for c in CROPS:
        sub = df[df.crop_type == c]
        if not len(sub):
            continue
        hi = (sub.crop_confidence == "high").sum()
        # Swatch alpha matches how that crop is actually drawn, so the legend cannot show a
        # solid key for a cohort the map renders faded.
        handles.append(plt.Line2D([], [], marker="s", linestyle="", markersize=10,
                                  color=CROP_COLOURS[c], alpha=1.0 if hi else 0.42))
        labels.append(f"{c}  —  {len(sub)} farms, {sub.area_ha.sum():5.1f} ha "
                      f"({100 * sub.area_ha.sum() / total:4.1f}%), "
                      + (f"{hi} high-conf" if hi else "tier 2, all low-conf"))
    if outline:
        handles.append(plt.Line2D([], [], color="#333333", linewidth=1.1,
                                  linestyle=(0, (6, 3))))
        labels.append("Sokhda village boundary")
    leg = ax.legend(handles, labels, loc="upper left", frameon=True, fontsize=8,
                    handletextpad=0.7, borderpad=0.6, labelspacing=0.55)
    leg.get_frame().set_edgecolor("#bbbbbb")
    leg.get_frame().set_linewidth(0.6)
    leg.get_frame().set_alpha(0.9)

    hi_area = df.loc[df.crop_confidence == "high", "area_ha"].sum()
    _stats_box(ax, [
        f"{100 * hi_area / total:.1f}% of area carries a high-confidence label",
        "tier 2 explains 0.17% of NDVI variance once the ranking axis is removed",
    ], loc="lower right")
    fig.tight_layout(rect=(0, 0.022, 1, 1))
    _footer(fig)
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _draw_trajectories(ax, df: pd.DataFrame, legend: bool = True,
                       annotate: bool = False) -> None:
    for crop in CROPS:
        sub = df[df.crop_type == crop]
        if not len(sub):
            continue
        vals = np.column_stack([sub[f"g0_db_filled_{t}"] for t in DATES])
        med = np.median(vals, axis=0)
        lo, hi = np.percentile(vals, [25, 75], axis=0)
        ax.plot(DOY, med, "-", color=CROP_COLOURS[crop], label=f"{crop} (n={len(sub)})",
                linewidth=1.8)
        # T5's level is interpolated, not measured. Drawing it as a filled marker like the
        # rest would put a measurement on the figure that the pipeline does not have.
        meas = [i for i, t in enumerate(DATES) if t not in INTERPOLATED]
        interp = [i for i, t in enumerate(DATES) if t in INTERPOLATED]
        ax.plot(np.array(DOY)[meas], med[meas], "o", color=CROP_COLOURS[crop], markersize=4.5)
        ax.plot(np.array(DOY)[interp], med[interp], "o", markersize=4.5,
                markerfacecolor="white", markeredgecolor=CROP_COLOURS[crop])
        ax.fill_between(DOY, lo, hi, color=CROP_COLOURS[crop], alpha=0.12)
    ax.set_xticks(DOY)
    ax.set_xticklabels([DATE_LABELS[t] for t in DATES])
    ax.set_ylabel(r"$\gamma^0$ HH (dB)")
    if annotate:
        # The incidence angle belongs on this axis: T1 is 6.5 deg steeper than T2/T3, the
        # largest geometry change in the stack, and a reader comparing T1 to T2 by eye is
        # otherwise comparing two viewing geometries without being told.
        for d, t in zip(DOY, DATES):
            ax.annotate(f"{DATE_INCIDENCE[t]:.1f}°", xy=(d, 0), xycoords=("data", "axes fraction"),
                        xytext=(0, -26), textcoords="offset points", ha="center",
                        fontsize=7.5, color="#777777")
        ax.annotate(r"$\theta_i$", xy=(0, 0), xycoords="axes fraction",
                    xytext=(-30, -26), textcoords="offset points", ha="center",
                    fontsize=7.5, color="#777777")
        ax.axvspan(DOY[1], DOY[2], color="#4a90d9", alpha=0.05, zorder=0)
        ax.annotate("monsoon · canopy closure", xy=((DOY[1] + DOY[2]) / 2, 1.0),
                    xycoords=("data", "axes fraction"), xytext=(0, -12),
                    textcoords="offset points", ha="center", fontsize=7.5, color="#4a7fb0")
    if legend:
        ax.legend(frameon=False, fontsize=9)
    ax.grid(alpha=0.25)


def trajectories(df: pd.DataFrame, path: str) -> None:
    """Farm-mean gamma0 per crop across all six dates."""
    fig, ax = plt.subplots(figsize=(12, 6.75))
    _draw_trajectories(ax, df, annotate=True)
    ax.set_title("Farm-mean backscatter trajectory by crop, all six passes",
                 fontsize=13, pad=26)
    ax.text(0.5, 1.022, "median with IQR shaded · each point is a per-farm mean over "
            "~2,100 pixels, so speckle is 0.094 dB · open marker at 29 Oct = interpolated, "
            "not measured",
            transform=ax.transAxes, ha="center", va="bottom", fontsize=8.5, color="#555555")
    _stats_box(ax, [
        "Levels are NOT comparable across dates on their own: the scene-level bare-soil",
        "reference drifts +1.65 dB between June and 12 November, measured on 16.5 M",
        "non-farm pixels. Every model input is a departure from each plot's OWN June",
        "soil, with that drift removed first. See the next figure.",
    ], loc="lower left")
    fig.tight_layout(rect=(0, 0.045, 1, 1))
    _footer(fig)
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _draw_departures(ax, df: pd.DataFrame, legend: bool = True) -> None:
    x = [DOY_OF[t] for t in CANOPY_DATES]
    for crop in CROPS:
        sub = df[df.crop_type == crop]
        if not len(sub):
            continue
        vals = np.column_stack([sub[f"departure_{t}"] for t in CANOPY_DATES])
        med = np.median(vals, axis=0)
        lo, hi = np.percentile(vals, [25, 75], axis=0)
        ax.plot(x, med, "-o", color=CROP_COLOURS[crop], markersize=5, linewidth=1.9,
                label=f"{crop} (n={len(sub)})")
        ax.fill_between(x, lo, hi, color=CROP_COLOURS[crop], alpha=0.11)
    ax.axhline(0.0, color="#333333", linewidth=1.0)
    ax.set_xticks(x)
    ax.set_xticklabels([DATE_LABELS[t] for t in CANOPY_DATES])
    ax.set_ylabel("departure from the plot's own June bare soil (dB)")
    ax.grid(alpha=0.25)
    if legend:
        ax.legend(frameon=False, fontsize=9)


def canopy_departure(df: pd.DataFrame, path: str) -> None:
    """The actual model input: each plot measured against itself, drift removed."""
    fig, ax = plt.subplots(figsize=(12, 6.75))
    _draw_departures(ax, df)
    ax.set_title("Canopy departure — every plot measured against its own June bare soil",
                 fontsize=13, pad=26)
    ax.text(0.5, 1.022,
            "anchor = mean of 6 and 19 June, both pre-sowing · scene-level bare-soil drift "
            "removed before differencing · zero = the plot's own soil",
            transform=ax.transAxes, ha="center", va="bottom", fontsize=8.5, color="#555555")
    _stats_box(ax, [
        "The sign is measured, not assumed: at X-band HH over this AOI a greener plot is a",
        "BRIGHTER plot (rho = +0.569 against same-day differenced Sentinel-2, n = 813).",
        "The pre-registration predicted attenuation for four of the five crops and was",
        "wrong for four of the five. Cotton is the only label still above soil on 12 Nov.",
    ], loc="upper left")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    _footer(fig)
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _draw_sign(ax, df: pd.DataFrame, legend: bool = True) -> tuple:
    """The differenced sign test, drawn from `canopy_sign` itself rather than re-derived.

    An earlier version of this panel differenced the raw levels and used the Round 3 labels,
    and printed spearman +0.541 on n=905 while the module's own log printed +0.569 on n=813.
    Two numbers for one measurement is the exact defect the figures are supposed to make
    impossible, so the panel now uses the module's frame, its coverage gate, and its Round 2
    labels -- Round 2's, because the sign was measured before the Round 3 labels existed.
    """
    import canopy_sign as cs

    d = cs.load()
    d = d[d.ok].copy()
    d["d_dep"] = d.departure_T6 - d.departure_T4
    d["d_ndvi"] = d.ndvi_T6 - d.ndvi_T4
    for crop in CROPS:
        m = (d.crop_r2 == crop).to_numpy()
        if m.sum():
            ax.scatter(d.d_ndvi[m], d.d_dep[m], s=11, alpha=0.55,
                       color=CROP_COLOURS[crop], label=crop)
    stats_row = cs.differenced(cs.load())
    row = stats_row[stats_row.crop == "ALL"].iloc[0]
    xs = np.linspace(d.d_ndvi.min(), d.d_ndvi.max(), 50)
    intercept = float(np.polyfit(d.d_ndvi, d.d_dep, 1)[1])
    ax.plot(xs, row.dB_per_NDVI * xs + intercept, color="#222222", linewidth=1.4,
            linestyle="--", zorder=5, label=f"fit: {row.dB_per_NDVI:+.2f} dB per NDVI unit")
    ax.axhline(0, color="#999999", linewidth=0.8)
    ax.axvline(0, color="#999999", linewidth=0.8)
    ax.grid(alpha=0.25)
    if legend:
        ax.legend(frameon=False, fontsize=8.5, loc="upper left")
    return int(row.n), float(row.rho), float(row.dB_per_NDVI)


def canopy_sign(df: pd.DataFrame, path: str) -> None:
    fig, ax = plt.subplots(figsize=(12, 6.75))
    n, rho, slope = _draw_sign(ax, df)
    ax.set_xlabel("$\\Delta$NDVI, 13 Oct $\\rightarrow$ 12 Nov (Sentinel-2, same days as the "
                  "SAR collects)")
    ax.set_ylabel("$\\Delta$(canopy departure), 13 Oct $\\rightarrow$ 12 Nov (dB)")
    ax.set_title("The canopy sign was measured before the model was written",
                 fontsize=13, pad=26)
    ax.text(0.5, 1.022,
            f"n = {n} plots with $\\geq$90% clean optical core on BOTH dates   ·   "
            f"spearman {rho:+.3f}   ·   slope {slope:+.2f} dB per NDVI unit",
            transform=ax.transAxes, ha="center", va="bottom", fontsize=8.5, color="#555555")
    _stats_box(ax, [
        "Pre-registered in canopy_sign.EXPECTED_SIGN, which was never edited afterwards:",
        "attenuation (greener = darker) for Cotton, Maize, Bajra, Groundnut; the opposite",
        "for Rice. FOUR OF FIVE WERE CONTRADICTED. Both sides are differenced, so each",
        "plot's own soil and its own baseline greenness cancel, and the two dates carry",
        "near-identical 14-day antecedent rainfall (11.9 vs 12.2 mm), which rules out a",
        "scene moisture effect. Plot-level irrigation remains an unresolved caveat.",
    ], loc="lower right")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    _footer(fig, "Sentinel-2 L2A B04/B08, 10 m, SCL 4/5/6/7 only")
    fig.savefig(path, dpi=160)
    plt.close(fig)


def model_chain(df: pd.DataFrame, path: str) -> None:
    """Y_ref -> season integral -> cohort-centred response -> forecast, drawn as one chain."""
    fig, axes = plt.subplots(1, 3, figsize=(14.4, 6.0))
    fig.subplots_adjust(left=0.06, right=0.985, top=0.70, bottom=0.17, wspace=0.26)

    ax = axes[0]
    for crop in CROPS:
        sub = df[df.crop_type == crop]
        ax.scatter(sub.season_integral_db, sub.accumulation_response, s=9, alpha=0.5,
                   color=CROP_COLOURS[crop], label=crop)
    ax.axhline(1.0, color="#333333", linewidth=1.0, linestyle=":")
    # 1st-99th percentile, not the full range: a handful of plots sit past -10 dB and
    # squash the S-curve everything else lives on into a vertical line.
    lo, hi = np.percentile(df.season_integral_db.dropna(), [1, 99])
    pad = 0.12 * (hi - lo)
    ax.set_xlim(lo - pad, hi + pad)
    ax.set_xlabel("season canopy integral (dB, mean departure over the season)\n"
                  "1st–99th percentile shown; the response saturates at $\\pm$30 %",
                  fontsize=9)
    ax.set_ylabel("accumulation response $a$", fontsize=9)
    ax.set_title("1. integral $\\rightarrow$ response, centred within each crop",
                 fontsize=10)
    ax.legend(frameon=False, fontsize=7.5, ncol=2)
    ax.grid(alpha=0.25)
    ax.tick_params(labelsize=8)

    ax = axes[1]
    per = df.groupby("crop_type").agg(ref=("yield_ref_t_ha", "first"),
                                      med=("yield_forecast_t_ha", "median")).reindex(CROPS)
    y = np.arange(len(per))[::-1]
    ax.barh(y, per.ref, color=[CROP_COLOURS[c] for c in per.index], alpha=0.35,
            edgecolor="#333333", linewidth=0.6, label="$Y_{ref}$, Gujarat kharif 2025-26")
    ax.plot(per.med, y, "D", color="#222222", markersize=6, linestyle="none",
            label="cohort median forecast")
    ax.set_yticks(y, per.index)
    ax.set_xlabel("t/ha", fontsize=9)
    ax.set_title("2. each cohort's median forecast lands on its $Y_{ref}$", fontsize=10)
    ax.legend(frameon=False, fontsize=7.5, loc="lower right")
    ax.grid(alpha=0.25, axis="x")
    ax.tick_params(labelsize=8)

    ax = axes[2]
    for crop in CROPS:
        sub = df[df.crop_type == crop]
        ax.scatter(sub.accumulation_response, sub.yield_forecast_t_ha, s=9, alpha=0.5,
                   color=CROP_COLOURS[crop])
    ax.set_xlabel("accumulation response $a$", fontsize=9)
    ax.set_ylabel("forecast (t/ha)", fontsize=9)
    ax.set_title("3. $Y_{final} = Y_{ref}(crop, 2025\\!-\\!26)\\times a$", fontsize=10)
    ax.grid(alpha=0.25)
    ax.tick_params(labelsize=8)

    fig.suptitle("The forecast is one reference yield and one measured modulation",
                 fontsize=15, y=0.965)
    fig.text(0.5, 0.80,
             "One modulation term, not three. A vigour index built from the same six "
             "departures the integral already integrates would\ncount the same measurement "
             "twice and look like two independent lines of evidence. $a$ is centred so each "
             "crop's median plot\nreceives its published state yield — the model "
             "redistributes within a cohort, it does not move the cohort. (An even-sized "
             "cohort\nmisses by ~0.2 %: numpy's median averages the two middle plots, which "
             "straddle 1.0 rather than sitting on it.)",
             ha="center", fontsize=9, color="#444444")
    _footer(fig, "$Y_{ref}$: DA&FW 3rd advance estimates, Gujarat kharif 2025-26")
    _pad_to_16x9(fig)          # Kaggle crops the gallery to 16:9; see the helper
    fig.savefig(path, dpi=160)
    plt.close(fig)


def extrapolation(df: pd.DataFrame, path: str) -> None:
    """How much of each crop's answer is projected past the last pass rather than observed."""
    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(14.4, 6.4),
                                     gridspec_kw={"width_ratios": [1.15, 1]})
    fig.subplots_adjust(left=0.065, right=0.98, top=0.76, bottom=0.10, wspace=0.24)

    per = df.groupby("crop_type").agg(
        area=("area_ha", "sum"),
        extrap=("extrapolated_fraction", "mean")).reindex(CROPS)
    y = np.arange(len(per))[::-1]
    ax_a.barh(y, 1.0 - per.extrap, color=[CROP_COLOURS[c] for c in per.index], alpha=0.95,
              edgecolor="#333333", linewidth=0.6, label="observed within the stack")
    ax_a.barh(y, per.extrap, left=1.0 - per.extrap,
              color=[CROP_COLOURS[c] for c in per.index], alpha=0.25,
              edgecolor="#333333", linewidth=0.6, hatch="//",
              label="projected past 12 Nov")
    for yi, (crop, r) in zip(y, per.iterrows()):
        if r.extrap > 0.01:
            ax_a.annotate(f"{100 * r.extrap:.0f}% projected (hatched)", xy=(1.0, yi),
                          xytext=(5, 0), textcoords="offset points", va="center",
                          fontsize=8.5, color="#333333")
        else:
            ax_a.annotate("closed by observation", xy=(1.0, yi), xytext=(5, 0),
                          textcoords="offset points", va="center", fontsize=8.5,
                          color="#666666")
    ax_a.set_yticks(y, per.index)
    ax_a.set_xlim(0, 1.42)
    ax_a.set_xlabel("share of the season canopy integral", fontsize=9)
    ax_a.set_title("Observed versus projected", fontsize=11, pad=8)
    # No legend on this panel. It carried two entries -- "observed within the stack" and
    # "projected past 12 Nov" -- that the per-row annotations already state, and every place
    # it could sit collides with something: "center right" ran through the Maize annotation,
    # and below the axes it fell off the canvas. The hatch is named in the Cotton row
    # instead, which is the only row that has one.
    ax_a.grid(alpha=0.22, axis="x")

    cl = df.cleared_fraction.dropna()
    ax_b.hist(cl, bins=25, color="#4a7fb0", alpha=0.75, edgecolor="white")
    ax_b.axvline(cl.median(), color="#b03030", linewidth=1.4,
                 label=f"median {cl.median():.2f}")
    ax_b.set_xlabel("cleared fraction at 12 Nov  =  $1 - canopy(T6)/canopy_{peak}$",
                    fontsize=9)
    ax_b.set_ylabel("plots", fontsize=9)
    ax_b.set_title(f"Canopy gone by the last pass  (n = {len(cl)} with an episode)",
                   fontsize=11, pad=8)
    ax_b.legend(frameon=False, fontsize=8.5)
    ax_b.grid(alpha=0.22, axis="y")

    fig.suptitle("The forecast states how much of itself it did not observe", fontsize=15,
                 y=0.95)
    fig.text(0.5, 0.845,
             "A per-plot harvest DATE was attempted and deleted: with three canopy samples "
             "and a 60-day September gap, the categorical\n'harvested / standing' label had "
             "no optical support at all (p = 1.00). The continuous cleared fraction that "
             "replaced it does validate\nagainst Sentinel-2 at rho = -0.529 — the 13 Oct and "
             "12 Nov scenes, which are diagnostic here, not held out. Cotton is "
             "the only crop whose season materially outruns the stack.",
             ha="center", fontsize=9, color="#444444")
    _footer(fig, "drawn from outputs/farm_forecast.csv")
    _pad_to_16x9(fig)          # Kaggle crops the gallery to 16:9; see the helper
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _backtest_frame() -> pd.DataFrame:
    """The exact frame `backtest.__main__` scores, rebuilt here so the figure cannot drift
    from the log. Round 2's labels are used on purpose: they were derived from T1-T4 only,
    so no information about the withheld date reaches any predictor through the label."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    phen = pd.read_csv(os.path.join(root, "work", "farm_phenology.csv"))
    r2 = pd.read_csv(geocode.round2_crops_path(),
                     usecols=["farm_id", "crop_type"]).rename(columns={"crop_type": "crop_r2"})
    frame = phen.merge(r2, on="farm_id", how="inner")
    return frame[frame.data_quality == "measured"]


def backtest_figure(path: str) -> None:
    """The headline validation: fit on T1-T4, predict the withheld 12 November pass."""
    import backtest

    frame = _backtest_frame()
    naive = backtest.run(frame, "level")
    ctrl = backtest.run(frame, "level_driftaware")

    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(14.4, 6.6), sharey=True)
    fig.subplots_adjust(left=0.235, right=0.975, top=0.74, bottom=0.11, wspace=0.08)

    order = list(naive.predictor)
    y = np.arange(len(order))[::-1]
    for ax, tab, title in ((ax_a, naive, "scored on the raw level"),
                           (ax_b, ctrl, "scored with the +1.65 dB bare-soil drift\n"
                                        "handed to EVERY predictor")):
        vals = tab.set_index("predictor").loc[order]
        colours = ["#b03030" if v < 0 else "#3a7d44" for v in vals.skill_vs_persistence]
        ax.barh(y, vals.skill_vs_persistence, color=colours, alpha=0.85,
                edgecolor="#333333", linewidth=0.6)
        ax.hlines(y, vals.ci_lo, vals.ci_hi, color="#222222", linewidth=1.2)
        ax.axvline(0.0, color="#222222", linewidth=1.1)
        for yi, (_, r) in zip(y, vals.iterrows()):
            off = 6 if r.skill_vs_persistence >= 0 else -6
            ax.annotate(f"{r.skill_vs_persistence:+.3f}",
                        xy=(r.ci_hi if r.skill_vs_persistence >= 0 else r.ci_lo, yi),
                        xytext=(off, 0), textcoords="offset points", va="center",
                        ha="left" if off > 0 else "right", fontsize=8.5, color="#333333")
        ax.set_yticks(y, order)
        ax.set_xlabel("skill against persistence  (1 = perfect, 0 = no better, < 0 = worse)",
                      fontsize=9)
        ax.set_title(title, fontsize=10, pad=8)
        ax.grid(alpha=0.22, axis="x")
        ax.tick_params(labelsize=9)
    # Both panels on ONE x scale. sharey only shares the categories; leaving the x axes
    # independent lets a -0.41 bar on the right look longer than a -0.59 bar on the left,
    # which is the whole comparison the figure exists to make.
    lo = min(naive.ci_lo.min(), ctrl.ci_lo.min())
    hi = max(naive.ci_hi.max(), ctrl.ci_hi.max())
    pad = 0.30 * (hi - lo)
    for ax in (ax_a, ax_b):
        ax.set_xlim(lo - pad, hi + pad)

    decay_n = float(naive.loc[naive.predictor.str.startswith("B5"),
                              "skill_vs_persistence"].iloc[0])
    decay_c = float(ctrl.loc[ctrl.predictor.str.startswith("B5"),
                             "skill_vs_persistence"].iloc[0])
    b4 = ctrl[ctrl.predictor.str.startswith("B4")].iloc[0]
    # The headline is negative and it is stated as the headline. A validation figure that
    # buries its own result under a bar chart is a marketing figure.
    _stats_box(ax_b, [
        "THE SHIPPED RULE DOES NOT BEAT PERSISTENCE.",
        f"Under the control it scores {b4.skill_vs_persistence:+.3f} with a 95 % interval of",
        f"[{b4.ci_lo:+.3f}, {b4.ci_hi:+.3f}], which contains zero. What the back-test",
        "establishes is narrower than skill and still worth having: the",
        "projection is not WORSE than carrying the last observation",
        "forward, and every alternative that looked better was an artefact.",
    ], loc="lower right")
    fig.suptitle("Leave-future-out back-test — fit on 6 Jun to 13 Oct, predict 12 November",
                 fontsize=15, y=0.955)
    fig.text(0.5, 0.845,
             f"n = {int(naive.n.iloc[0])} measured plots · 2,000-bootstrap CIs · crop labels "
             f"are Round 2's, derived from T1–T4 only, so no information about the\nwithheld "
             f"date reaches any predictor. The control is why the shipped rule is a flat "
             f"hold: a decaying senescence limb scored {decay_n:+.3f} "
             f"on the left\nand {decay_c:+.3f} on the right. It was winning by being biased "
             f"in the direction of a district drift it did not model, and it was deleted.",
             ha="center", fontsize=9, color="#444444")
    _footer(fig, "backtest.run(frame, 'level') and backtest.run(frame, 'level_driftaware')")
    _pad_to_16x9(fig)          # Kaggle crops the gallery to 16:9; see the helper
    fig.savefig(path, dpi=160)
    plt.close(fig)


def reserved_optical(df: pd.DataFrame, path: str) -> None:
    """The held-out December and January scenes, and the one claim they can settle."""
    from scipy import stats

    # validate.MIN_COV on BOTH reserved dates plus measured-only, matching validate.report
    # exactly. An earlier version used a looser gate and printed p = 1.14e-11 on n = 61
    # cotton while the validation log printed 1.26e-11 on n = 58.
    import validate as V
    sub = df[(df[f"ndvi_cov_{V.RESERVED[0]}"] >= V.MIN_COV)
             & (df[f"ndvi_cov_{V.RESERVED[1]}"] >= V.MIN_COV)
             & (df.data_quality == "measured")]
    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(14.4, 6.6),
                                     gridspec_kw={"width_ratios": [1.25, 1]})
    fig.subplots_adjust(left=0.065, right=0.985, top=0.685, bottom=0.11, wspace=0.22)

    x = [DOY_OF["T1"], DOY_OF["T4"], DOY_OF["T6"], 346, 381]
    labels = ["10 Jun", "13 Oct", "12 Nov", "12 Dec", "16 Jan"]
    cols = ["ndvi_T1", "ndvi_T4", "ndvi_T6", "ndvi_R1", "ndvi_R2"]
    for crop in CROPS:
        s = sub[sub.crop_type == crop]
        if not len(s):
            continue
        ax_a.plot(x, [s[c].median() for c in cols], "-o", color=CROP_COLOURS[crop],
                  markersize=5, linewidth=1.9, label=f"{crop} (n={len(s)})")
    ax_a.axvspan(330, 395, color="#b03030", alpha=0.07, zorder=0)
    ax_a.annotate("RESERVED — read by nothing upstream", xy=(362, 1.0),
                  xycoords=("data", "axes fraction"), xytext=(0, -13),
                  textcoords="offset points", ha="center", fontsize=8, color="#b03030")
    ax_a.set_xticks(x)
    ax_a.set_xticklabels(labels)
    ax_a.set_ylabel("median Sentinel-2 NDVI")
    ax_a.set_title("Crop-label NDVI trajectory into the reserved window", fontsize=11, pad=8)
    ax_a.legend(frameon=False, fontsize=8.5, ncol=2)
    ax_a.grid(alpha=0.25)

    cot = sub[sub.crop_type == "Cotton"]
    rest = sub[sub.crop_type != "Cotton"]
    p = stats.mannwhitneyu(cot.ndvi_R1, rest.ndvi_R1, alternative="greater").pvalue
    parts = [cot.ndvi_R1.dropna(), rest.ndvi_R1.dropna()]
    key = "tick_labels" if Version(matplotlib.__version__) >= Version("3.9") else "labels"
    bp = ax_b.boxplot(parts, patch_artist=True, showfliers=False,
                      **{key: [f"Cotton\nn={len(parts[0])}", f"other four\nn={len(parts[1])}"]})
    bp["boxes"][0].set_facecolor(CROP_COLOURS["Cotton"])
    bp["boxes"][0].set_alpha(0.7)
    bp["boxes"][1].set_facecolor("#999999")
    bp["boxes"][1].set_alpha(0.45)
    ax_b.set_ylabel("NDVI, 12 December 2025")
    ax_b.set_title(f"Cotton on the reserved December scene\none-sided Mann-Whitney "
                   f"p = {p:.2e}", fontsize=11, pad=8)
    ax_b.grid(alpha=0.22, axis="y")

    fig.suptitle("Held-out optical — a SAR-only label tested on a scene it never saw",
                 fontsize=15, y=0.975)
    fig.text(0.5, 0.815,
             "December and January are post-kharif and inside the rabi window, so they "
             "CANNOT score the yield forecast — December NDVI over a\nharvested paddy plot "
             "is a rabi crop. What they can test is which plots still carry a kharif crop, "
             "and of the five only cotton is picked\ninto January. The cotton label is a "
             "SAR threshold on 12 November, and that threshold was informed by Oct–Nov "
             "optical banding —\nso this is a SAR-only rule tested on a December scene it "
             "never saw, not proof that 1.5 dB is the right cut. Negative control:\nplots "
             "cleared by 12 Nov are NOT bare in December (0.488 against a population 0.520) "
             "— they are under rabi, as the reading requires.",
             ha="center", fontsize=9, color="#444444")
    _footer(fig, "Sentinel-2 L2A, 2025-12-12 and 2026-01-16; assert_reserved_unread() gates "
                 "the pipeline against reading them")
    _pad_to_16x9(fig)          # Kaggle crops the gallery to 16:9; see the helper
    fig.savefig(path, dpi=160)
    plt.close(fig)


def zone_map(df: pd.DataFrame, patches, ids, path: str, outline=None) -> None:
    """The 500 m grid, which is where the spatial part of the aggregation actually lives."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    zones = pd.read_csv(os.path.join(root, "outputs", "zone_summary.csv"))

    import submit
    d = df.copy()
    zx = np.floor((d.cx - d.cx.min()) / submit.ZONE_M).astype(int)
    zy = np.floor((d.cy - d.cy.min()) / submit.ZONE_M).astype(int)
    d["zone"] = [f"Z{a}{b}" for a, b in zip(zx, zy)]
    d = d.merge(zones[["zone", "yield_t_ha_area_wt", "n_farms"]], on="zone", how="left")

    fig, (ax, ax_b) = plt.subplots(1, 2, figsize=(14.4, 8.1),
                                   gridspec_kw={"width_ratios": [1.35, 1]})
    fig.subplots_adjust(left=0.005, right=0.965, top=0.80, bottom=0.075, wspace=0.10)

    pc = _draw_choropleth(ax, d, patches, ids, "yield_t_ha_area_wt", outline=outline,
                          cmap="viridis")
    _scale_bar(ax, frac=0.22)
    _north_arrow(ax)
    ax.set_title(f"Sub-zone forecast, {submit.ZONE_M:.0f} m cells "
                 f"({len(zones)} cells with $\\geq$ {submit.MIN_ZONE_FARMS} farms)",
                 fontsize=11, pad=6)
    cax = ax.inset_axes([0.28, 0.02, 0.44, 0.026])
    cb = fig.colorbar(pc, cax=cax, orientation="horizontal")
    cb.set_label("area-weighted forecast (t/ha)", fontsize=8)
    cb.ax.tick_params(labelsize=7)

    z = zones.sort_values("yield_t_ha_area_wt")
    yy = np.arange(len(z))
    ax_b.barh(yy, z.yield_t_ha_area_wt, color="#3f7f93", alpha=0.85, height=0.78)
    ax_b.set_yticks(yy, z.zone, fontsize=5.6)
    ax_b.set_xlabel("area-weighted forecast (t/ha)", fontsize=9)
    vill = float((df.yield_forecast_t_ha * df.area_ha).sum() / df.area_ha.sum())
    ax_b.axvline(vill, color="#b03030", linewidth=1.4,
                 label=f"village figure {vill:.2f} t/ha")
    ax_b.legend(frameon=False, fontsize=8.5, loc="lower right")
    ax_b.set_title("Every cell, ranked", fontsize=11, pad=8)
    ax_b.grid(alpha=0.22, axis="x")
    ax_b.tick_params(axis="x", labelsize=8)

    fig.suptitle("The village table is one row. This is the aggregation that carries "
                 "information.", fontsize=15, y=0.955)
    fig.text(0.5, 0.865,
             f"The study area is a single village, so the required village-level table is a "
             f"single total with no spatial content at all. The same\narea-weighted "
             f"arithmetic applied on a fixed {submit.ZONE_M:.0f} m grid spreads "
             f"{z.yield_t_ha_area_wt.min():.2f} to {z.yield_t_ha_area_wt.max():.2f} t/ha "
             f"around a village figure of {vill:.2f} — a "
             f"{z.yield_t_ha_area_wt.max() - z.yield_t_ha_area_wt.min():.2f} t/ha range a "
             f"district officer can act on.\nCells below {submit.MIN_ZONE_FARMS} farms are "
             f"dropped rather than shown as noisy one-farm zones: "
             f"{int(z.n_farms.sum())} of {len(df)} farms are covered.",
             ha="center", fontsize=9, color="#444444")
    _footer(fig, "drawn from outputs/zone_summary.csv")
    fig.savefig(path, dpi=160)
    plt.close(fig)


def village_summary(path: str, out_dir: str) -> None:
    """The village-level aggregation, as a chart and as the table that ships.

    Reads `outputs/village_summary.csv` -- the artefact `submit.py` actually wrote -- rather
    than re-aggregating from the farm table. A figure that re-derives its own totals can
    disagree with the submission; this one cannot. A missing file raises, because a gallery
    image showing a silently re-computed aggregation is exactly the failure mode the phase
    gates exist to prevent.
    """
    s = pd.read_csv(os.path.join(out_dir, "village_summary.csv"))
    total = s[s.crop_type == "ALL"].iloc[0]
    per = s[s.crop_type != "ALL"].sort_values("area_ha", ascending=False)
    y = np.arange(len(per))[::-1]

    fig = plt.figure(figsize=(14.4, 8.1))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.0, 0.82], hspace=0.30, wspace=0.20,
                          left=0.085, right=0.975, top=0.80, bottom=0.055)

    # Left: area, with the high-confidence fraction drawn inside each bar. The two tiers are
    # the central caveat of the crop step, so the aggregation figure shows which hectares
    # carry a label that survived a physical threshold and which were allocated.
    ax_a = fig.add_subplot(gs[0, 0])
    colours = [CROP_COLOURS[c] for c in per.crop_type]
    ax_a.barh(y, per.area_ha, color=colours, alpha=0.55, edgecolor="#333333", linewidth=0.6)
    ax_a.barh(y, per.area_ha * per.high_confidence_share, color=colours, alpha=1.0,
              edgecolor="#333333", linewidth=0.6)
    for yi, (_, r) in zip(y, per.iterrows()):
        ax_a.annotate(f"{r.area_ha:.1f} ha · {100 * r.area_share:.1f}%",
                      xy=(r.area_ha, yi), xytext=(4, 0), textcoords="offset points",
                      va="center", fontsize=8, color="#333333")
    ax_a.set_yticks(y, per.crop_type)
    ax_a.set_xlim(0, per.area_ha.max() * 1.30)
    ax_a.set_xlabel("area (ha)", fontsize=9)
    ax_a.set_title("Cropped area, and how much of it is high-confidence", fontsize=10, pad=8)
    ax_a.text(0.985, 0.06, "solid = measured label (tier 1)\nfaded = allocated (tier 2)",
              transform=ax_a.transAxes, ha="right", fontsize=7.5, color="#555555")
    ax_a.grid(alpha=0.22, axis="x")
    ax_a.tick_params(labelsize=9)

    # Right: production, which is the quantity the aggregation exists to produce. Annotated
    # with the per-hectare rate so a long bar driven by area rather than by rate is legible
    # as such -- groundnut and maize dominate on hectares, not on yield.
    ax_b = fig.add_subplot(gs[0, 1])
    ax_b.barh(y, per.production_t, color=colours, alpha=0.85, edgecolor="#333333",
              linewidth=0.6)
    for yi, (_, r) in zip(y, per.iterrows()):
        ax_b.annotate(f"{r.production_t:.1f} t  ({r.yield_t_ha_area_wt:.2f} t/ha)",
                      xy=(r.production_t, yi), xytext=(4, 0), textcoords="offset points",
                      va="center", fontsize=8, color="#333333")
    ax_b.set_yticks(y, per.crop_type)
    ax_b.set_xlim(0, per.production_t.max() * 1.42)
    ax_b.set_xlabel("forecast production at harvest (t)", fontsize=9)
    ax_b.set_title("Production  =  $\\Sigma$ (forecast yield $\\times$ area)", fontsize=10,
                   pad=8)
    ax_b.grid(alpha=0.22, axis="x")
    ax_b.tick_params(labelsize=9)

    ax_t = fig.add_subplot(gs[1, :])
    ax_t.axis("off")
    cols = ["crop", "farms", "area (ha)", "share", "$Y_{ref}$ 2025-26\n(t/ha)",
            "forecast\n(t/ha, area-wt)", "p10 – p90\n(t/ha)", "production\n(t)",
            "projected\nshare", "measured\nlabels"]
    rows, order = [], list(per.crop_type) + ["ALL"]
    for _, r in pd.concat([per, total.to_frame().T]).iterrows():
        ref = "—" if pd.isna(r.yield_ref_t_ha) else f"{float(r.yield_ref_t_ha):.2f}"
        rows.append([r.crop_type, f"{int(r.n_farms)}", f"{float(r.area_ha):.1f}",
                     f"{100 * float(r.area_share):.1f}%", ref,
                     f"{float(r.yield_t_ha_area_wt):.2f}",
                     f"{float(r.yield_t_ha_p10):.2f} – {float(r.yield_t_ha_p90):.2f}",
                     f"{float(r.production_t):.1f}",
                     f"{100 * float(r.extrapolated_fraction_area_wt):.0f}%",
                     f"{100 * float(r.high_confidence_share):.1f}%"])
    tab = ax_t.table(cellText=rows, colLabels=cols, cellLoc="center", loc="center")
    tab.auto_set_font_size(False)
    tab.set_fontsize(8.2)
    tab.scale(1, 1.78)
    for (row, col), cell in tab.get_celld().items():
        cell.set_edgecolor("#cccccc")
        if row == 0:
            cell.set_text_props(weight="bold", fontsize=7.6)
            cell.set_facecolor("#f0f0f0")
        elif order[row - 1] == "ALL":
            cell.set_text_props(weight="bold")
            cell.set_facecolor("#f7f7f7")
        elif col == 0:
            cell.set_facecolor(CROP_COLOURS[order[row - 1]])
            cell.set_alpha(0.30)

    fig.suptitle(f"Village forecast — {total.village_name}, "
                 f"village_id {int(total.village_id)}", fontsize=15, y=0.965)
    fig.text(0.5, 0.895,
             f"all {int(total.n_farms)} farms carry a row · aggregation is area-weighted in "
             f"hectares, not per farm — plots span 0.004 to 3.49 ha, and ten enclose "
             f"effectively no ground",
             ha="center", fontsize=9.5, color="#444444")
    fig.text(0.5, 0.868,
             f"{total.production_t:.1f} t forecast at harvest over {total.area_ha:.1f} ha  ·  "
             f"{total.yield_t_ha_area_wt:.2f} t/ha area-weighted  ·  "
             f"{100 * total.extrapolated_fraction_area_wt:.1f}% of the season integral "
             f"projected rather than observed",
             ha="center", fontsize=10, color="#222222")
    _footer(fig, "drawn from outputs/village_summary.csv, the aggregation that ships")
    fig.savefig(path, dpi=160)
    plt.close(fig)


def uncertainty_budget(path: str) -> None:
    """What the village total is worth, and which term owns the width.

    Reads `work/uncertainty_budget.csv`, which `yield_forecast.report_uncertainty` wrote
    while the run was still going. Every row is the whole chain re-run under one change, so
    the widths are comparable to each other and to the number they surround.

    The panel exists because the honest answer to "how sure are you" is not a single symbol
    after the total. It is a ranking, and in this pipeline the ranking has the external
    reference on top and everything the radar contributes an order of magnitude below it.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tab = pd.read_csv(os.path.join(root, "work", "uncertainty_budget.csv"))
    total = float(tab.shipped_t.iloc[0])
    tab = tab.sort_values("half_width_t")
    y = np.arange(len(tab))

    fig = plt.figure(figsize=(12, 6.75))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.72, 1], wspace=0.22,
                          left=0.075, right=0.975, top=0.78, bottom=0.20)

    ax = fig.add_subplot(gs[0, 0])
    for yi, r in zip(y, tab.itertuples()):
        colour = "#b2182b" if r.half_width_t > 20 else "#2c7fb8"
        ax.plot([r.low_t, r.high_t], [yi, yi], color=colour, linewidth=7, alpha=0.75,
                solid_capstyle="butt")
        ax.annotate(f"±{r.half_width_t:.1f} t  ({r.half_width_pct:.1f} %)",
                    xy=(r.high_t, yi), xytext=(7, 0), textcoords="offset points",
                    va="center", fontsize=8.5, color="#333333")
    ax.axvline(total, color="#222222", linestyle="--", linewidth=1.2)
    ax.annotate(f"shipped {total:.1f} t", xy=(total, len(tab) - 0.35), xytext=(5, 0),
                textcoords="offset points", fontsize=9, color="#222222")
    ax.set_yticks(y, [s.split(" (")[0] for s in tab.source])
    ax.set_xlim(tab.low_t.min() - 40, tab.high_t.max() + 75)
    ax.set_ylim(-0.7, len(tab) - 0.2)
    ax.set_xlabel("village production forecast (t)", fontsize=9)
    ax.set_title("Each bar is the whole chain re-run under one change", fontsize=10, pad=8)
    ax.grid(alpha=0.22, axis="x")
    ax.tick_params(labelsize=9)

    axb = fig.add_subplot(gs[0, 1])
    yref = float(tab.loc[tab.source.str.startswith("reference"), "half_width_t"].iloc[0])
    radar = float(tab.loc[~tab.source.str.startswith("reference"), "half_width_t"].sum())
    axb.bar([0, 1], [radar, yref], color=["#2c7fb8", "#b2182b"], alpha=0.85, width=0.58)
    for xi, v in zip([0, 1], [radar, yref]):
        axb.annotate(f"±{v:.1f} t", xy=(xi, v), xytext=(0, 4), textcoords="offset points",
                     ha="center", fontsize=9.5, color="#222222")
    axb.set_xticks([0, 1], ["every radar term\nadded together",
                            "the state reference\nalone"])
    axb.set_ylabel("half-width on the village total (t)", fontsize=9)
    axb.set_ylim(0, max(radar, yref) * 1.22)
    axb.set_title("Where the width actually is", fontsize=10, pad=8)
    axb.grid(alpha=0.22, axis="y")
    axb.tick_params(labelsize=8.5)

    fig.suptitle("What the village total is worth", fontsize=14.5, y=0.945)
    fig.text(0.5, 0.875,
             "four sources, each priced by re-running the forecast rather than by "
             "propagating a formula through it",
             ha="center", fontsize=9.5, color="#444444")
    fig.text(0.5, 0.075,
             "The per-plot SAR term ranks plots inside a cohort; the level it ranks around "
             "is a state advance estimate.\nSo the radar decides who is above and below "
             "the line, and somebody else's measurement decides where the line is.",
             ha="center", fontsize=9, color="#222222")
    _footer(fig, "drawn from work/uncertainty_budget.csv, written by yield_forecast.report_uncertainty")
    fig.savefig(path, dpi=160)
    plt.close(fig)


def cover(df: pd.DataFrame, patches, ids, path: str, outline=None) -> None:
    """Media-gallery cover: the deliverable, the physics behind it, and the check on it.

    Deliberately not a montage of all twelve figures. A cover has to survive being scaled to
    a thumbnail, so it carries three panels only -- what was produced (the forecast map), the
    measurement that drives it (the canopy departure curves), and the one piece of evidence
    that comes from outside the SAR entirely (the measured canopy sign). Every panel is drawn
    by the same helper as its full-size counterpart, so the cover cannot show a number the
    figures contradict.
    """
    fig = plt.figure(figsize=(12, 6.75))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.06, 1], hspace=0.44, wspace=0.10,
                          left=0.01, right=0.965, top=0.795, bottom=0.09)

    ax_map = fig.add_subplot(gs[:, 0])
    pc = _draw_choropleth(ax_map, df, patches, ids, "yield_forecast_t_ha",
                          outline=outline, cmap="viridis", furniture=False)
    _scale_bar(ax_map, frac=0.20)
    prod = (df.yield_forecast_t_ha * df.area_ha).sum()
    ax_map.set_title(f"Final yield forecast — {len(df)} plots, {df.area_ha.sum():.0f} ha, "
                     f"{prod:.0f} t", fontsize=11, pad=6)
    # Inset rather than `fig.colorbar(ax=...)`: the equal-aspect map leaves dead space at the
    # bottom of its box, and a space-stealing colorbar puts its label hard against the
    # neighbouring panel's y-axis.
    cax = ax_map.inset_axes([0.30, 0.015, 0.42, 0.028])
    cb = fig.colorbar(pc, cax=cax, orientation="horizontal")
    cb.set_label("forecast yield at harvest (t/ha)", fontsize=8)
    cb.ax.tick_params(labelsize=7)

    ax_dep = fig.add_subplot(gs[0, 1])
    _draw_departures(ax_dep, df, legend=False)
    ax_dep.set_title("Canopy departure from each plot's own June soil", fontsize=9)
    ax_dep.set_ylabel("dB above own soil", fontsize=8)
    ax_dep.tick_params(labelsize=8)
    lo, hi = ax_dep.get_ylim()
    ax_dep.set_ylim(lo, hi + 0.40 * (hi - lo))
    ax_dep.legend(frameon=False, fontsize=7, loc="upper center", ncol=3,
                  columnspacing=1.0, handlelength=1.4, borderpad=0.1)

    ax_sign = fig.add_subplot(gs[1, 1])
    n, rho, slope = _draw_sign(ax_sign, df, legend=False)
    ax_sign.set_title(f"The canopy sign, measured not assumed: spearman {rho:+.3f} (n={n})",
                      fontsize=9)
    ax_sign.set_xlabel("$\\Delta$NDVI, 13 Oct $\\rightarrow$ 12 Nov", fontsize=8)
    ax_sign.set_ylabel("$\\Delta$departure (dB)", fontsize=8)
    ax_sign.tick_params(labelsize=8)

    fig.suptitle("Sokhda, Vadodara — final kharif yield forecast from six Capella X-band "
                 "SLC passes", fontsize=14.5, y=0.955)
    fig.text(0.5, 0.885,
             "6 acquisitions, 6 Jun – 12 Nov 2025 · raw complex SLC $\\rightarrow$ "
             "$\\gamma^0$, RPC-geocoded to 1 m, co-registered to 0.21 m · no ground truth, "
             "no label to fit",
             ha="center", fontsize=9.5, color="#444444")
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _read_block(path: str, width: int, bounds=None) -> tuple:
    """A geocoded product, average-resampled to `width` px, with its map extent.

    Two reasons the resampling is `GRIORA_Average` rather than the default nearest: the AOI
    is 5,906 x 4,714 at 1 m and three channels read whole are 330 MB of float32 for a
    picture 2,400 px wide, and averaging on the way down is multilooking -- it is the same
    operation that takes farm-level speckle from +-5.6 dB to 0.09 dB, and it is what makes
    the field pattern visible rather than the speckle.
    """
    ds = gdal.Open(path)
    gt = ds.GetGeoTransform()
    x0, y0, nx, ny = 0, 0, ds.RasterXSize, ds.RasterYSize
    if bounds is not None:
        xmin, ymin, xmax, ymax = bounds
        x0 = max(0, int((xmin - gt[0]) / gt[1]))
        y0 = max(0, int((ymax - gt[3]) / gt[5]))
        nx = min(ds.RasterXSize - x0, int((xmax - xmin) / gt[1]))
        ny = min(ds.RasterYSize - y0, int((ymax - ymin) / abs(gt[5])))
    width = min(width, nx)
    h = max(1, int(round(ny * width / nx)))
    arr = ds.GetRasterBand(1).ReadAsArray(x0, y0, nx, ny, buf_xsize=width, buf_ysize=h,
                                          resample_alg=gdal.GRIORA_Average)
    extent = (gt[0] + x0 * gt[1], gt[0] + (x0 + nx) * gt[1],
              gt[3] + (y0 + ny) * gt[5], gt[3] + y0 * gt[5])
    ds = None
    return arr.astype(np.float32), extent


# Each channel is stretched over a fixed dB window around its own median rather than over
# its own 2-98 percentiles. The three dates share almost all of their dynamic range -- a
# bund is bright in June and in November -- so a percentile stretch maps all three onto the
# same numbers and returns a grey image. The colour in a multitemporal composite is the
# BETWEEN-DATE difference, and a narrow symmetric window is what shows it.
COMPOSITE_SPAN_DB = 5.0
COMPOSITE_SATURATION = 1.25


def _channel(arr: np.ndarray, offset_db: float) -> np.ndarray:
    """One channel: linear gamma0 -> dB, measured offset applied, windowed to 0-1."""
    db = 10.0 * np.log10(np.where(arr > 0, arr, np.nan)) + offset_db
    mid = np.nanmedian(db)
    return np.clip((db - (mid - COMPOSITE_SPAN_DB)) / (2 * COMPOSITE_SPAN_DB), 0.0, 1.0)


def _composite(paths: dict, offsets: dict, width: int, bounds=None) -> tuple:
    """The three-date RGB cube, co-valid-masked, with saturation lifted."""
    chans, extent, valid = [], None, None
    for code in COMPOSITE_CHANNELS:
        arr, extent = _read_block(paths[code], width, bounds)
        ok = np.isfinite(arr) & (arr > 0)
        valid = ok if valid is None else (valid & ok)
        chans.append(_channel(arr, offsets.get(code, 0.0)))
    rgb = np.dstack(chans)
    rgb[~np.isfinite(rgb)] = 0.0
    hsv = matplotlib.colors.rgb_to_hsv(rgb)
    hsv[..., 1] = np.clip(hsv[..., 1] * COMPOSITE_SATURATION, 0.0, 1.0)
    rgb = matplotlib.colors.hsv_to_rgb(hsv)
    # A pixel measured on some dates and not others is not a colour, it is an edge of the
    # swath. Painted black rather than left to read as a crop signature.
    rgb[~valid] = 0.0
    return rgb, extent


# The three dates that carry the season, and why each is in a channel:
#   R  T2 19 Jun  monsoon onset -- wet soil, crop barely emerged, the brightest AOI median
#   G  T3 14 Aug  peak vegetative, and the driest antecedent pass in the stack
#   B  T6 12 Nov  after most of the harvest
# T6 carries the measured +4.28 dB scene offset. Applied here, because an uncorrected
# composite reads blue everywhere and would disagree with the model shipping beside it.
COMPOSITE_CHANNELS = ["T2", "T3", "T6"]
COMPOSITE_KEY = [
    ("green", "brightest in August — a canopy at peak that was gone by November"),
    ("blue / magenta", "still bright on 12 November — cotton and the long-duration parcels"),
    ("red", "bright only at monsoon onset — wet soil that never closed a canopy"),
    ("grey", "the same on all three dates — built-up, roads, bunds, bare ground"),
]
ZOOM_HALF_M = 600.0


def sar_composite(df: pd.DataFrame, patches, ids, path: str, outline=None,
                  width: int = 2200) -> None:
    """Multi-temporal RGB composite of the calibrated stack.

    One picture that is the evidence for the whole method and contains no model: three dates
    of the same calibrated gamma0 in three colour channels. If the season did not modulate
    X-band backscatter plot by plot, this image would be grey -- and the parts of it that
    are grey are exactly the parts that are not fields.

    The zoom is read at native resolution over its own window and carries the delivered crop
    labels, so a reader can check the labels against the colour instead of taking them.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    work = os.path.join(root, "work")
    offsets = scene_diagnostics.read_offsets(work)["offsets_db"]
    scene_paths = scene_diagnostics.paths(os.path.join(work, "gamma0"))

    rgb, extent = _composite(scene_paths, offsets, width)
    cx, cy = float(df.cx.median()), float(df.cy.median())
    zbounds = (cx - ZOOM_HALF_M, cy - ZOOM_HALF_M, cx + ZOOM_HALF_M, cy + ZOOM_HALF_M)
    # 0.35 px per metre in the zoom: ~9 looks, which is what turns speckle into fields.
    zrgb, zextent = _composite(scene_paths, offsets, int(0.35 * 2 * ZOOM_HALF_M),
                               zbounds)

    fig = plt.figure(figsize=(12, 6.75))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.5, 1], wspace=0.05,
                          left=0.012, right=0.988, top=0.795, bottom=0.115)

    ax = fig.add_subplot(gs[0, 0])
    ax.imshow(rgb, extent=extent, origin="upper", interpolation="bilinear")
    if outline is not None:
        _draw_village(ax, outline, label=False)
    ax.add_patch(plt.Rectangle((zbounds[0], zbounds[1]), 2 * ZOOM_HALF_M, 2 * ZOOM_HALF_M,
                               fill=False, edgecolor="white", linewidth=1.0))
    _map_axes(ax, frame=False)
    ax.set_title("19 Jun · 14 Aug · 12 Nov 2025 as red · green · blue, whole AOI",
                 fontsize=10, pad=6)
    _scale_bar(ax, frac=0.22)
    _north_arrow(ax)

    axz = fig.add_subplot(gs[0, 1])
    axz.imshow(zrgb, extent=zextent, origin="upper", interpolation="bilinear")
    labelled = {crop: [] for crop in CROPS}
    crop_of = dict(zip(df.farm_id, df.crop_type))
    for poly, fid in zip(patches, ids):
        v = poly.get_xy()
        if (abs(v[:, 0].mean() - cx) < ZOOM_HALF_M
                and abs(v[:, 1].mean() - cy) < ZOOM_HALF_M and fid in crop_of):
            labelled[crop_of[fid]].append(MplPolygon(v, closed=True))
    for crop, polys in labelled.items():
        if polys:
            axz.add_collection(PatchCollection(polys, facecolor="none", linewidth=1.0,
                                               edgecolor=CROP_COLOURS[crop]))
    axz.set_xlim(zbounds[0], zbounds[2])
    axz.set_ylim(zbounds[1], zbounds[3])
    _map_axes(axz, frame=True)
    n_zoom = sum(len(v) for v in labelled.values())
    axz.set_title(f"the white box, {2 * ZOOM_HALF_M:.0f} m across — {n_zoom} plots by "
                  "delivered label", fontsize=10, pad=6)
    leg = axz.legend(handles=[plt.Line2D([], [], color=CROP_COLOURS[c], lw=2.4, label=c)
                              for c in CROPS if labelled[c]],
                     frameon=True, fontsize=7.5, loc="upper left", ncol=1,
                     handlelength=1.3, borderpad=0.4, labelspacing=0.3)
    leg.get_frame().set_facecolor("black")
    leg.get_frame().set_alpha(0.55)
    leg.get_frame().set_edgecolor("none")
    for text in leg.get_texts():
        text.set_color("white")

    fig.suptitle("One picture, no model: three dates of calibrated $\\gamma^0$ in three "
                 "colour channels", fontsize=14.5, y=0.955)
    fig.text(0.5, 0.885,
             "Capella X-band HH, RPC-geocoded to 1 m and co-registered · the measured "
             "+4.28 dB T6 offset applied · each channel windowed "
             f"±{COMPOSITE_SPAN_DB:.1f} dB about its own median",
             ha="center", fontsize=9.5, color="#444444")
    for i, (name, meaning) in enumerate(COMPOSITE_KEY):
        fig.text(0.06 + 0.47 * (i % 2), 0.075 - 0.030 * (i // 2),
                 f"{name}: {meaning}", fontsize=8.5, color="#222222")
    _footer(fig)
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _load() -> pd.DataFrame:
    """The shipped plot table, with the upstream columns the panels need merged onto it.

    The shipped column always wins on a name collision: `outputs/farm_forecast.csv` is the
    artefact a judge reads, so a figure must not quietly draw a different value for the same
    quantity because the work table holds it at a different precision.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ship = pd.read_csv(os.path.join(root, "outputs", "farm_forecast.csv"))
    raw = pd.read_csv(os.path.join(root, "work", "farm_forecast_raw.csv"))
    ndvi = pd.read_csv(os.path.join(root, "work", "farm_ndvi.csv"))
    extra = [c for c in raw.columns if c not in ship.columns or c == "farm_id"]
    df = ship.merge(raw[extra], on="farm_id", how="left")
    return df.merge(ndvi, on="farm_id", how="left")


def run() -> list:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = os.path.join(root, "outputs")
    out = os.path.join(root, "figures")
    os.makedirs(out, exist_ok=True)
    df = _load()
    patches, ids = farm_patches()
    outline = village_outline()

    prod = (df.yield_forecast_t_ha * df.area_ha).sum()
    jobs = [
        ("cover.png", lambda p: cover(df, patches, ids, p, outline)),
        ("sar_composite.png",
         lambda p: sar_composite(df, patches, ids, p, outline)),
        ("yield_forecast_map.png",
         lambda p: choropleth(df, patches, ids, "yield_forecast_t_ha",
                              "Final yield forecast at harvest, Sokhda kharif 2025", p,
                              cmap="viridis", label="forecast yield (t/ha)",
                              outline=outline, fmt="{:.2f}",
                              subtitle="a forecast of the harvest outcome, not a "
                                       "yield-to-date — cotton's answer is 56 % projected "
                                       "past the last pass, everything else is closed by "
                                       "observation",
                              stats=[f"village production forecast: {prod:.1f} t over "
                                     f"{df.area_ha.sum():.1f} ha  "
                                     f"({prod / df.area_ha.sum():.2f} t/ha area-weighted)"])),
        ("crop_type_map.png", lambda p: crop_map(df, patches, ids, p, outline)),
        ("trajectories.png", lambda p: trajectories(df, p)),
        ("canopy_departure.png", lambda p: canopy_departure(df, p)),
        ("canopy_sign.png", lambda p: canopy_sign(df, p)),
        ("model_chain.png", lambda p: model_chain(df, p)),
        ("extrapolation.png", lambda p: extrapolation(df, p)),
        ("backtest.png", lambda p: backtest_figure(p)),
        ("reserved_optical.png", lambda p: reserved_optical(df, p)),
        ("zone_map.png", lambda p: zone_map(df, patches, ids, p, outline)),
        ("village_summary.png", lambda p: village_summary(p, out_dir)),
        ("uncertainty_budget.png", lambda p: uncertainty_budget(p)),
    ]

    made = []
    for name, fn in jobs:
        path = os.path.join(out, name)
        fn(path)
        made.append(path)
        print(f"wrote {path}")
    return made


if __name__ == "__main__":
    run()
