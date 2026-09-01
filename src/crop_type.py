"""Farm-level crop type from the calibrated gamma0 trajectories.

Context, stated plainly because it shapes every choice below. The competition's Data
page promises a `round1_crop_classification.csv`; it is not in the distributed data (the
Kaggle file listing returns 31 files, none of them a CSV), and Round 1 only ever produced
village-level hectares per crop, never per-farm labels. So there is nothing to join on
and the labels have to be derived here. The organizers call this "a means to an end for
this round, not the primary deliverable" -- so the goal is a transparent, physically
argued classification with an honest confidence statement, not a black box.

Round 1 established over ~30 experiments that single-polarisation HH carries weak
crop-*type* information for structurally similar dryland crops. Two things changed:

  - the unit is a farm polygon, not a pixel, so speckle drops from +-5.6 dB to ~0.09 dB;
  - boundaries are given, so there is no segmentation step to get wrong -- which is what
    sank Round 1's OBIA lineage five times.

What has not changed is physics: at 3.1 cm the radar sees the top of the canopy and
saturates once it closes. No processing recovers information the wavelength never
captured, so this module reports per-farm confidence and the write-up states the limit.

=== Feature choice: incidence geometry decides it ===

The four collects were tasked independently and have different incidence angles:
T1 35.24, T2 28.77, T3 28.69, T4 31.53 deg. gamma0 removes the geometry dependence for
distributed volume scatterers but not for surface scattering, so a cross-date difference
is only clean when the angles match. That makes T2-T3 (0.08 deg apart) the one
geometrically matched pair in the stack, T3-T4 (2.8 deg) nearly clean, and anything
involving T1 (3.7-6.5 deg away) the most contaminated.

Features are therefore built on T2/T3/T4. Two earlier versions of this module got this
wrong and it mattered:

  - Using T1->T2 as an "emergence" slope produced a cluster covering 31% of the village
    that was defined almost entirely by that descriptor. Nothing has a canopy on 19 June;
    that rise is monsoon-onset soil moisture confounded with the stack's largest
    incidence change. Removed.
  - Forcing a one-to-one cluster->crop match made Bajra a residual slot -- the cluster it
    received fit Cotton better and its backscatter *rose* into October, when bajra must
    fall because it has been harvested. That is exactly the failure Round 1 documented
    twice ("Bajra vs Groundnut is a tiebreak between the two least-dynamic leftovers").
    Now every cluster is assigned to its own best-fitting crop independently.

=== Why no "other" sink ===

Round 1's k=9 sink absorbed 31% of cropland indiscriminately and regressed on the real
leaderboard. Non-crop parcels are handled instead by an explicit physical screen, which
is auditable in a way a sink is not.

=== What the data actually supports: a two-tier answer ===

Three successive assignment schemes were tried here -- prior-constrained many-to-one,
Hungarian one-to-one, and unconstrained argmax. They disagreed about Maize, Bajra and
Groundnut every time, and in each one whichever crop the rule pointed at last absorbed
the residual (41% Groundnut in one, 31% Bajra in another, 1.4% Maize in a third). They
agreed, every time, about two things:

  Rice    one cluster sits ~5 dB above every other at peak canopy and falls into
          October. Physically explicable: paddy occupies low-lying water-retaining
          soils, and once tillering starts over standing water the stem-surface double
          bounce is strong at HH; the level drops as fields are drained and harvested.
  Cotton  one cluster is the only one whose backscatter *rises* from 14 Aug to 13 Oct.
          Cotton is the only one of the five still green and structurally bulky in
          mid-October; everything else has been harvested.

That is the honest result, and it is what Round 1 predicted: single-pol HH has a
documented separability floor for structurally similar dryland crops, and at 3.1 cm the
canopy saturates once closed. Farm-level averaging removed the *noise* barrier (+-5.6 dB
to 0.09 dB); it cannot create *information* the wavelength never captured.

So the module returns a two-tier classification rather than pretending to five-way
confidence:

  tier 1 (high confidence)  Rice and Cotton, from the two signatures above.
  tier 2 (low confidence)   the remainder is allocated across Maize / Bajra / Groundnut
                            by ranking on gamma0 at T4, ascending. Cut points come from
                            district-proportional area.

The tier-2 axis was chosen after the scattering regime was measured, and the first choice
was wrong. It originally ranked on `range234`, the seasonal swing across T2/T3/T4. That
put farms with a 19-June mean of -13.99 dB -- against -18 .. -19.6 dB for everything else
-- at the top of the ranking and hence into Bajra. That brightness is wet, freshly tilled
bare soil at monsoon onset, i.e. *late sowing*, not harvest swing. The axis was measuring
sowing date and calling it crop type.

gamma0 at T4 replaces it because the same-day Sentinel-2 comparison established that
gamma0 on 13 October tracks standing vegetation directly (+0.550, monotonic; see
`s2_ndvi.py`). The three crops differ mainly in when they leave the field: bajra is a
75-85 day crop harvested by late September, maize is harvested Sep-Oct, and groundnut is
lifted Oct-November and is still in the ground on the 13 October collect. So ascending
gamma0_T4 is ascending "still there on 13 October", which is the one axis among these
three with a clear agronomic ordering and a measured physical meaning.

The district mix is used openly, and only here, as the allocation rule for a subset the
radar is stated as unable to separate -- not as a hidden constraint on the whole answer.
Every row carries `crop_confidence`, so a judge can see exactly which labels are load-
bearing and which are not.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from phenology import CANOPY_DATES

CROPS = ["Rice", "Cotton", "Maize", "Bajra", "Groundnut"]
# T5's level is the T4-T6 interpolation, not a measurement (see `farm_features`), so it is
# excluded from every level-based screen and descriptor here.
DATES = ["T1", "T2", "T3", "T4", "T6"]

# More clusters than crops: many-to-one assignment lets a crop with two management
# regimes take two clusters instead of forcing an artificial split, and it gives each
# crop's signature a real chance of being captured by some cluster.
N_CLUSTERS = 9
N_SEEDS = 20
RANDOM_STATE = 20260730
IMPUTE_NEIGHBOURS = 8

# Descriptors, all on the incidence-matched or near-matched dates. `level_T3` is the
# absolute gamma0 at peak vegetative; `d23` the canopy build over the clean pair; `d34`
# senescence/harvest; `curv234` whether the trajectory peaks mid-season or keeps rising;
# `range234` the seasonal swing; `cov_T3` within-field structure at peak canopy.
# The first six are Round 2's, on the four dates it had. The last three are what the two
# November-side acquisitions add, and they are the reason this round re-derives the labels
# rather than carrying Round 2's forward:
#
#   d46              drift-corrected change from 13 October to 12 November. Cotton is the
#                    only one of the five still standing through November; everything else
#                    is off the field or lifting. Round 2 had to infer this from 13 October
#                    alone, thirty days before the discriminating event.
#   canopy_end_db    canopy signal remaining on 12 November, on the sign measured in
#                    `canopy_sign`. Near zero for a cleared field whatever its soil is like.
#   observed_integral season-total canopy departure, DOY 226-316.
#
# All three are departures from each plot's own June bare soil with the district-wide
# bare-soil drift removed, so none of them carries the scene-level radiometric difference
# between dates -- which matters here, because T6 sits +1.65 dB above T1 district-wide.
FEATURES = ["level_T3", "d23", "d34", "curv234", "range234", "cov_T3",
            "d46", "canopy_end_db", "observed_integral"]

# Non-crop screen, applied BEFORE clustering.
#
# Round 1's largest confirmed win came from gating which pixels reached the clustering
# step. Here the farm polygons are the spatial gate, but some digitised parcels contain
# buildings, trees or radar artefacts, and a first pass reproduced Round 1's leak exactly:
# a 10-farm cluster whose T2 mean was +2.5 dB -- while T1/T3/T4 sat at a normal -20 dB --
# got labelled Bajra. A whole field jumping 30 dB on one date and back is an artefact,
# not a crop.
#
#   BRIGHT  farm mean above -10 dB on any date. X-band HH over any crop sits well below
#           this; the crop population here spans -22 to -14 dB.
#   SPIKY   max CoV above 2.0, i.e. std twice the mean. Fully developed single-look
#           speckle gives CoV = 1.0 (measured: 0.98-1.05) and real crop patchiness
#           reaches ~1.2-1.4. Above 2.0 a few pixels carry most of the energy.
#
# Screened farms are labelled from their neighbours and flagged, never dropped -- the
# rubric requires all 966 -- and the flag travels into the output.
#   LONG-DURATION  canopy departure at or above 1.5 dB on ALL THREE canopy dates. An annual
#              kharif crop is at or near its own bare-soil level at one end of the season
#              or the other -- sown into bare ground in June, off the field by November.
#              A parcel that sits well above its own bare soil from 14 August through 12
#              November held canopy across the whole window and is not one of the five.
#
#              The threshold is set by cotton, the longest-standing of the five: cotton's
#              90th percentile for this statistic is +0.26 dB, so 1.5 dB is far outside
#              anything an annual reaches here. It catches 12 parcels, 12.2 ha (2.7 % of
#              farm area), whose median size is 0.95 ha against the AOI median of 0.27 ha.
#              Sentinel-2 confirms them independently and was not used to choose the
#              threshold: median NDVI 0.705 on 13 October RISING to 0.794 on 12 November,
#              against 0.479 and 0.516 for the population. Nothing annual is greener in
#              mid-November than in mid-October at that level.
#
#              This screen was first written as a PERENNIAL screen, reading the parcels as
#              orchard or plantation. The reserved-scene test in validate.py falsified that:
#              they are decisively greener than the population on 12 December and 16 January
#              but decisively LESS green on 10 June (0.247 vs 0.397, p = 1.1e-04), and their
#              June radar level is indistinguishable from everyone else's (p = 0.71). In
#              June they are bare fields. The trajectory is a crop sown with the monsoon
#              that brightens across all six passes and is still green in mid-January --
#              sugarcane and banana both fit and both are grown in Vadodara. The constant
#              and the flag were renamed to say only what the data supports: long duration,
#              not one of the five kharif annuals.
OUTLIER_MAX_DB = -10.0
OUTLIER_MAX_COV = 2.0
LONG_DURATION_MIN_DB = 1.5

# District crop mix, used ONLY to report against the result -- never as an input. An
# earlier version used it as an assignment constraint and it drove the answer: two
# clusters landed on Groundnut and the labels flipped when its weight changed. Sources:
#   - Gujarat kharif 2025 sowing (the season these scenes image): groundnut 20.41 and
#     cotton 20.35 lakh ha, paddy 7.17, maize 2.64, bajra 1.53.
#   - Vadodara's field-crop profile is paddy/cotton/maize; Gujarat's groundnut area is
#     concentrated in Saurashtra, not the central zone.
#   - Vadodara ranks 1st in Gujarat for maize yield, 2nd for cotton yield.
#   - Round 1 found real bajra area in Vadodara district to be close to zero.
CROP_MIX_REFERENCE = {"Rice": 0.26, "Cotton": 0.32, "Maize": 0.18, "Bajra": 0.08,
                      "Groundnut": 0.16}

# Tier-1 thresholds, on cluster-level z-scored descriptors. Deliberately strict: a
# cluster must show the signature clearly to earn a high-confidence label.
RICE_LEVEL_Z = 1.0     # peak-canopy level well above every other cluster
RICE_D34_Z = 0.0       # and falling into October (drained, harvested)
COTTON_D34_Z = 1.0     # the only crop still standing on 13 October
# Round 3's cotton rule, and a better one: cotton is the only crop of the five still
# carrying canopy on 12 NOVEMBER. Round 2 had to read that off 13 October, before bajra,
# maize and much of the rice had finished, so the separation it needed had barely opened.
#
# It is applied PER PLOT and in absolute dB, not per cluster in z-scores, and both changes
# are deliberate:
#
#   Per plot, because cotton does not form its own cluster cleanly. Sorting plots by
#   November canopy and reading the independent optical record gives a smooth monotone
#   gradient, not a separate mode -- the fraction of plots greening by more than 0.10 NDVI
#   between 13 October and 12 November runs 0.22, 0.25, 0.31, 0.46, 0.53, 0.79 across
#   ascending bands of `canopy_end_db`. Cluster-level assignment therefore splits cotton
#   across mixed clusters: it labelled 89 % of the top band cotton but only 50 % of the
#   band below it, which have the same optical signature.
#
#   In absolute dB, because a z-score threshold moves when the clustering moves. The
#   stability table shows exactly that: tier-1 area ranged over 96.9-130.6 ha across
#   n_clusters and n_seeds settings while nothing about the fields changed.
#
# The value is anchored on this stack's own noise floor rather than fitted. MIN_CANOPY_DB
# is 0.5 dB, set by the plot-to-plot soil spread on the two June dates that cannot contain
# a canopy; 1.5 dB is three times that, and it is the same figure the long-duration screen
# uses for "unambiguous canopy" on a single date.
#
# Disclosure, because it affects how much the corroboration is worth: the optical banding
# above was inspected before this constant was fixed. The optical agreement at 1.5 dB
# specifically is therefore corroboration, not an independent test of that value.
# `cotton_sensitivity` reports 1.0 / 1.5 / 2.0 dB so the reader can see the whole range.
COTTON_NOV_DB = 1.5

# The unseparable remainder, ordered by ascending departure at T6 = ascending "still standing
# on 12 November": bajra off the field by late Sep, maize harvested Sep-Oct, groundnut
# lifted Oct-Nov and still in the ground on the collect date.
# Ranked on 12 November rather than on Round 2's raw gamma0 at 13 October. Two reasons, both
# improvements rather than preferences: the discriminating event is thirty days later than
# Round 2 could see it, and a departure from the plot's own bare soil is not contaminated by
# that plot's soil brightness the way an absolute level is.
#
# The axis is the SIGNED departure, and it was `canopy_end_db` -- the same departure clipped
# at zero -- until the second Kaggle run disagreed with the local run about 39 plots and
# 1.7 t of village production (S14). The clip is what did it:
#
#   793 tier-2 plots, 403 with canopy_end_db == 0.0 exactly (all 136 bajra, 267 of 316 maize)
#   inside that block departure_T6 runs -14.316 .. -0.001 dB across 392 distinct values
#
# The cumulative-area cut between Bajra and Maize fell entirely inside that tie block, so the
# whole Bajra-vs-Maize distinction was settled by the order pandas happened to leave equal
# keys in -- not a property of the fields, and free to differ between machines. Clipping is
# right for `cleared_fraction` and for the cotton rule, which both live above zero and both
# ask "how much canopy is left"; it is wrong as a ranking key, where "how far below its own
# soil this plot has fallen" is exactly the ordering being asked for. It is the same
# degeneracy S4 removed from the season integral (signed rho +0.564 against the optical
# reference, clipped +0.472, absolute -0.085), left standing here because S4 looked at the
# integral and not at the classifier that consumes the same column.
TIER2_AXIS = "departure_T6"
TIER2_ORDER = ["Bajra", "Maize", "Groundnut"]

# Pre-registered before the axis was changed, so the run scores a prediction rather than
# describing an outcome. Both are recorded whichever way they fall (S4, S9).
#
#   1. The tier-2 cohorts should separate BETTER on NDVI residualised against the ranking
#      axis, in `s2_ndvi.report_validation`, than the eta2_resid = 0.0274 / F = 10.30 the
#      clipped axis produced: the ordering now carries information where it carried none.
#   2. `t5_anomaly` -- soil exposure measured after 63 mm of rain, and never used to build
#      any label -- should order Bajra > Maize > Groundnut, most-exposed to least.
TIER2_PREREGISTERED = ("s2_ndvi eta2_resid > 0.0274 for tier 2; "
                       "t5_anomaly ordered Bajra > Maize > Groundnut")

# Phenological expectations for central-Gujarat kharif, as the sign and strength each
# crop should show on each z-scored descriptor.
# T2 = 19 Jun (monsoon onset, sowing) | T3 = 14 Aug (peak vegetative) | T4 = 13 Oct.
#
# The classic dark-flood rice rule is NOT usable here. Round 1 tested it at pixel level
# and at object level and closed it: median T2->T3 rise was negative in every village
# against a required +6 dB. Our farm-level min(T1,T2)-T3 agrees -- median +0.4 dB, only
# -1.4 dB at the 10th percentile. Rice is identified instead by a persistently elevated
# HH level: paddy sits on low-lying water-retaining soils, and once tillering starts over
# standing water the stem-surface double bounce is strong at HH. It falls as fields are
# drained and harvested.
#
#   Rice       highest level at peak canopy, strong build over T2->T3, falling into Oct.
#   Cotton     the only crop still green and structurally bulky on 13 Oct -> the only
#              positive d34.
#   Maize      strong canopy build to mid-Aug, harvested Sep-Oct -> +d23, -d34, moderate
#              level. Separated from Rice by a much lower absolute level.
#   Bajra      short duration, off the field by late Sep -> the most negative d34, large
#              seasonal swing, below-average level.
#   Groundnut  low dense canopy, little structural change -> smallest swing, low level.
PHENOLOGY_RULES = {
    "Rice":      {"level_T3": +1.0, "d23": +0.6, "d34": -0.3},
    "Cotton":    {"d34": +1.0, "curv234": -0.4},
    "Maize":     {"d23": +0.8, "d34": -0.4, "level_T3": +0.2, "range234": +0.2},
    "Bajra":     {"d34": -1.0, "range234": +0.5, "level_T3": -0.3},
    "Groundnut": {"range234": -1.0, "level_T3": -0.4, "d23": -0.2},
}


def derive_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add the incidence-aware descriptors the rules are written against."""
    t2, t3, t4 = (df[f"g0_db_filled_{t}"] for t in ["T2", "T3", "T4"])
    # Six-date descriptor, drift-corrected. `departure_*` and `canopy_end_db` arrive from
    # `phenology`, which is why this module now reads `farm_phenology.csv`.
    df["d46"] = df["departure_T6"] - df["departure_T4"]
    df["level_T3"] = t3
    df["d23"] = t3 - t2       # incidence-matched pair: 28.77 vs 28.69 deg
    df["d34"] = t4 - t3       # 28.69 vs 31.53 deg, near-matched
    df["curv234"] = t2 - 2.0 * t3 + t4
    df["range234"] = df[[f"g0_db_filled_{t}" for t in ["T2", "T3", "T4"]]].max(axis=1) - \
        df[[f"g0_db_filled_{t}" for t in ["T2", "T3", "T4"]]].min(axis=1)
    return df


def screen_non_crop(df: pd.DataFrame) -> np.ndarray:
    """Flag parcels whose radar signature cannot be vegetation. See the constants."""
    too_bright = df[[f"g0_db_filled_{t}" for t in DATES]].max(axis=1) > OUTLIER_MAX_DB
    too_spiky = df[[f"cov_{t}" for t in DATES]].max(axis=1) > OUTLIER_MAX_COV
    long_duration = df[[f"departure_{t}" for t in CANOPY_DATES]].min(axis=1) >= LONG_DURATION_MIN_DB
    df["long_duration_flag"] = long_duration.to_numpy()
    return (too_bright | too_spiky | long_duration).to_numpy()


def consensus_labels(x: np.ndarray, n_clusters: int = N_CLUSTERS,
                     n_seeds: int = N_SEEDS) -> tuple:
    """Cluster over many seeds and keep the partition closest to the consensus.

    K-means on ~930 points is cheap, so rather than trusting one seed we build the
    co-association matrix over `n_seeds` runs and keep the run that best agrees with it.
    That yields a stable partition and, as a by-product, a per-farm measure of how often
    a farm's neighbours travel with it.
    """
    n = x.shape[0]
    runs = [KMeans(n_clusters=n_clusters, n_init=10, random_state=RANDOM_STATE + s)
            .fit_predict(x) for s in range(n_seeds)]

    co = np.zeros((n, n), dtype=np.float32)
    for lab in runs:
        co += (lab[:, None] == lab[None, :]).astype(np.float32)
    co /= len(runs)

    scores = [float(((lab[:, None] == lab[None, :]).astype(np.float32) * co).sum())
              for lab in runs]
    best = runs[int(np.argmax(scores))]
    stability = np.array([co[i, best == best[i]].mean() for i in range(n)])
    return best, stability


def cluster_profile(df: pd.DataFrame, labels: np.ndarray) -> pd.DataFrame:
    """Mean descriptor per cluster, z-scored across clusters."""
    prof = df.groupby(labels)[FEATURES].mean()
    return (prof - prof.mean()) / prof.std(ddof=0).replace(0.0, 1.0)


def phenology_fit(zprof: pd.DataFrame) -> pd.DataFrame:
    """Score every cluster against every crop's rule. Higher is a better match."""
    return pd.DataFrame(
        {crop: sum(coef * zprof[feat] for feat, coef in rules.items())
         for crop, rules in PHENOLOGY_RULES.items()},
        index=zprof.index,
    )[CROPS]


def assign_tier1(zprof: pd.DataFrame) -> dict:
    """Clusters that clearly show the Rice or Cotton signature. Threshold rules only.

    The organizers stated for Round 1 that they "primarily expect a rule-based or
    threshold-based approach"; this is that. Clustering only proposes candidate
    signatures, and explicit physical thresholds adjudicate which ones earn a label.
    """
    tier1 = {}
    for c in zprof.index:
        if zprof.loc[c, "level_T3"] >= RICE_LEVEL_Z and zprof.loc[c, "d34"] <= RICE_D34_Z:
            tier1[int(c)] = "Rice"
        elif zprof.loc[c, "d34"] >= COTTON_D34_Z:
            tier1[int(c)] = "Cotton"
    return tier1


def allocate_tier2(df: pd.DataFrame, unresolved: np.ndarray,
                   tiebreak=None, weights=None) -> pd.Series:
    """Split the unseparable remainder across Bajra / Maize / Groundnut.

    Ranked on canopy remaining at 12 November ascending -- ascending "still standing at the
    end of the stack". The same-day Sentinel-2 comparison established that this is a direct
    measure of standing vegetation: the departure at T6 correlates with same-day NDVI at
    rho=+0.454, and the clearing measure built from it tracks the optical change at -0.529. Bajra is a 75-85 day crop off the field by late September, maize is
    harvested Sep-Oct, groundnut is lifted Oct-Nov and still in the ground on the collect
    date. Cut points are set so the *area* split matches the district mix renormalised
    over these three.

    This is the only place the district mix enters the classification, and it enters as
    a stated allocation rule for a subset the radar cannot separate.

    `weights` overrides that mix, in `TIER2_ORDER`, and exists so
    `yield_forecast.district_mix_sensitivity` can price what the prior is worth. It is never
    passed on the shipped path. Until an audit asked for it, the mix was the one input to the
    answer with no error bar at all -- it sets the areas of three of the five cohorts, 793 of
    966 plots, and the uncertainty budget did not have a row for it.
    """
    sub = df.loc[unresolved]
    # Stable sort with an explicit final key. Ten plots remain exactly equal on the axis and
    # something has to order them; by default that is `farm_id`, the only stable plot key in
    # the dataset, so the allocation is a function of the fields and of nothing else. The old
    # default quicksort left the order of equal keys to the input row order, and S14 is what
    # that cost. `tiebreak` exists so `tier2_arbitrariness` can price what the tie order is
    # still worth, and is never passed on the shipped path.
    second = pd.Series(tiebreak, index=sub.index) if tiebreak is not None else sub["farm_id"]
    order = sub.assign(_second=second).sort_values([TIER2_AXIS, "_second"],
                                                   ascending=True, kind="mergesort").index
    w = np.array([CROP_MIX_REFERENCE[c] for c in TIER2_ORDER]) if weights is None \
        else np.asarray(weights, dtype=float)
    weights = w / w.sum()

    area = df.loc[order, "area_ha"].to_numpy()
    cum = np.cumsum(area) / area.sum()
    edges = np.cumsum(weights)[:-1]
    bucket = np.searchsorted(edges, cum, side="left")
    return pd.Series([TIER2_ORDER[min(b, len(TIER2_ORDER) - 1)] for b in bucket], index=order)


def tier2_arbitrariness(df: pd.DataFrame, unresolved: np.ndarray,
                        n_perm: int = 200) -> dict:
    """How much of the tier-2 answer is still decided by the order of equal keys?

    S14's defect was invisible because a tie block is silent: the run prints a number, the
    number is stable on one machine, and nothing in the output says that the same values in
    a different order would have printed a different one. This measures it rather than
    trusting the axis. Plots are permuted before the stable sort `n_perm` times, which
    reorders exact ties and nothing else, and the spread in cohort area is what the tie
    order is worth.

    It measures the allocation rule, not the fields. `yield_forecast.uncertainty_budget`
    prices the same permutations in tonnes.
    """
    sub = df.loc[unresolved]
    axis = sub[TIER2_AXIS].to_numpy(dtype=float)
    _, counts = np.unique(axis, return_counts=True)
    tied = sub.index[pd.Series(axis, index=sub.index).duplicated(keep=False)]
    rng = np.random.default_rng(RANDOM_STATE)

    areas = {c: [] for c in TIER2_ORDER}
    for _ in range(n_perm):
        lab = allocate_tier2(df, unresolved, tiebreak=rng.permutation(len(sub)))
        for c in TIER2_ORDER:
            areas[c].append(float(df.loc[lab[lab == c].index, "area_ha"].sum()))
    # The before/after of S15, printed rather than remembered: the clipped axis this one
    # replaced tied every plot that ended the season at or below its own June soil.
    clipped = np.clip(sub[TIER2_AXIS].to_numpy(dtype=float), 0.0, None)
    was_tied = clipped == 0.0
    return {"n_tier2": int(len(sub)),
            "n_tied_clipped": int(was_tied.sum()),
            "area_tied_clipped": float(sub.loc[was_tied, "area_ha"].sum()),
            "n_distinct_in_that_block": int(pd.unique(axis[was_tied]).size),
            "n_tied": int(len(tied)),
            "area_tied": float(df.loc[tied, "area_ha"].sum()),
            "tier2_area": float(sub["area_ha"].sum()),
            "largest_tie_run": int(counts.max()),
            "area_spread": {c: (float(np.min(v)), float(np.max(v)))
                            for c, v in areas.items()},
            "n_perm": int(n_perm)}


def cotton_sensitivity(df: pd.DataFrame, keep: np.ndarray,
                       levels=(1.0, 1.5, 2.0)) -> pd.DataFrame:
    """How much of the cotton area is the 1.5 dB in `COTTON_NOV_DB`?

    Reported rather than argued, for the same reason `phenology.clearing_sensitivity` is.
    The November canopy is a continuous gradient with no natural gap, so any single cut is
    a judgement and the reader is entitled to see the whole range.
    """
    rows = []
    for lv in levels:
        m = (df["canopy_end_db"] >= lv) & keep
        rows.append({"cotton_nov_db": lv, "plots": int(m.sum()),
                     "area_ha": float(df.loc[m, "area_ha"].sum()),
                     "area_share": float(df.loc[m, "area_ha"].sum() / df["area_ha"].sum())})
    return pd.DataFrame(rows)


def run(features_csv: str, n_clusters: int = N_CLUSTERS, n_seeds: int = N_SEEDS) -> tuple:
    df = derive_features(pd.read_csv(features_csv))
    df["non_crop_flag"] = screen_non_crop(df)
    keep = ~df["non_crop_flag"].to_numpy()

    scaler = StandardScaler().fit(df.loc[keep, FEATURES].to_numpy(dtype=float))
    x = scaler.transform(df[FEATURES].to_numpy(dtype=float))

    labels = np.full(len(df), -1, dtype=int)
    stability = np.zeros(len(df))
    lab_keep, stab_keep = consensus_labels(x[keep], n_clusters, n_seeds)
    labels[keep] = lab_keep
    stability[keep] = stab_keep

    # Screened parcels still need a label -- the schema requires all 966 rows. They take
    # the majority cluster of their nearest clustered neighbours: the same spatial
    # autocorrelation argument used for the out-of-swath farms in Phase 2.
    if (~keep).any():
        xy = df[["cx", "cy"]].to_numpy()
        donor_xy = xy[keep]
        for i in np.flatnonzero(~keep):
            d = np.hypot(donor_xy[:, 0] - xy[i, 0], donor_xy[:, 1] - xy[i, 1])
            labels[i] = np.bincount(lab_keep[np.argsort(d)[:IMPUTE_NEIGHBOURS]]).argmax()

    df["cluster"] = labels
    df["cluster_stability"] = stability

    zprof = cluster_profile(df[keep], lab_keep)
    fit = phenology_fit(zprof)

    tier1 = assign_tier1(zprof)
    df["crop_type"] = df["cluster"].map(tier1)
    # Plot-level cotton, applied after the cluster rules and before the tier-2 allocation.
    # See COTTON_NOV_DB. A plot already called Rice by its cluster is left alone: paddy is
    # drained and cut by mid-November and neither rice cluster carries any November canopy
    # (median canopy_end_db 0.00 for both), so the two rules do not in fact compete here.
    standing_nov = (df["canopy_end_db"] >= COTTON_NOV_DB) & keep & df["crop_type"].isna()
    df.loc[standing_nov, "crop_type"] = "Cotton"
    df["crop_confidence"] = np.where(df["crop_type"].notna(), "high", "low")
    unresolved = df.index[df["crop_type"].isna()].to_numpy()
    # Carried into `work/farm_crops.csv` so the uncertainty budget can find the allocated
    # subset without re-deriving which plots the threshold rules did not claim.
    df["tier2_flag"] = False
    df.loc[unresolved, "tier2_flag"] = True
    if len(unresolved):
        df.loc[unresolved, "crop_type"] = allocate_tier2(df, unresolved)
    # A screened parcel's label came from its neighbours, so it is never high-confidence.
    df.loc[~keep, "crop_confidence"] = "low"

    # Per-farm confidence: how much closer a farm sits to its own cluster centre than to
    # the nearest centre carrying a *different* crop. Small margins can flip.
    centres = np.vstack([x[keep][lab_keep == c].mean(axis=0) for c in sorted(set(lab_keep))])
    order = {c: i for i, c in enumerate(sorted(set(lab_keep)))}
    dist = np.linalg.norm(x[:, None, :] - centres[None, :, :], axis=2)
    own = dist[np.arange(len(df)), [order[c] for c in labels]]
    cluster_crop = df.groupby("cluster")["crop_type"].agg(lambda s: s.mode().iat[0])
    other = dist.copy()
    for c in sorted(set(lab_keep)):
        same = [order[k] for k in sorted(set(lab_keep))
                if cluster_crop.get(k) == cluster_crop.get(c)]
        other[np.ix_(labels == c, same)] = np.inf
    nearest = other.min(axis=1)
    df["crop_margin"] = (nearest - own) / (nearest + own)
    return df, zprof, tier1, fit, x, labels, keep


def report(features_csv: str, df, zprof, tier1, fit, x, labels, keep,
           with_stability: bool = True) -> None:
    """Print every crop-step figure the write-up quotes.

    This used to live in `__main__`, which the notebook never executes, so the shipped
    artefact printed nothing at all for Phase 3 while the write-up quoted a dozen numbers
    from it -- the same defect the Round 1 audit logged as F9 and that `s2_ndvi` was fixed
    for. A number that is not in the run log is a number nobody can check.

    `with_stability` re-runs the clustering at four other settings, which is the evidence
    for the tier-1 stability claim. It costs four extra fits.
    """
    print(f"{len(df)} farms; non-crop screen removed {int((~keep).sum())} "
          f"({df.area_ha[~keep].sum():.1f} ha, "
          f"{df.area_ha[~keep].sum() / df.area_ha.sum():.1%}) before clustering")
    print(f"{N_CLUSTERS} clusters over {N_SEEDS} seeds on the remaining {int(keep.sum())}")
    print(f"silhouette = {silhouette_score(x[keep], labels[keep]):.3f}   "
          f"consensus stability: median {np.median(df.cluster_stability[keep]):.2f}")

    print("\ncluster -> label, with the z-scored descriptors that decided it")
    print("  tier 1 = the threshold rules fired; tier 2 = allocated, radar cannot separate")
    print("  cl tier  label        n     ha  " + "".join(f"{s:>10}" for s in FEATURES))
    for c in zprof.index:
        sub = df[df.cluster == c]
        tier = "1" if int(c) in tier1 else "2"
        label = tier1.get(int(c), "/".join(sorted(set(sub.crop_type))))
        print(f"  {int(c)}   {tier}    {label:<12} {len(sub):3d} {sub.area_ha.sum():6.1f}  "
              + "".join(f"{zprof.loc[c, s]:10.2f}" for s in FEATURES))
    print("  best phenology fit per cluster, for the record (not used to assign):")
    print("       " + "".join(f"{c:>11}" for c in CROPS))
    for c in zprof.index:
        print(f"    {int(c)}  " + "".join(f"{fit.loc[c, crop]:11.2f}" for crop in CROPS))

    print("\nconfidence tiers:")
    for conf in ("high", "low"):
        sub = df[df.crop_confidence == conf]
        print(f"  {conf:<4} {len(sub):3d} farms  {sub.area_ha.sum():6.1f} ha  "
              f"{sub.area_ha.sum() / df.area_ha.sum():5.1%}  "
              f"({', '.join(sorted(set(sub.crop_type)))})")

    print("\nabsolute gamma0 (dB) by crop and date — the physical trajectory:")
    print("  crop        " + "".join(f"{c:>9}" for c in DATES) + "      d23      d34")
    for crop in CROPS:
        sub = df[df.crop_type == crop]
        if not len(sub):
            continue
        print(f"  {crop:<10}  " + "".join(f"{sub[f'g0_db_filled_{t}'].mean():9.2f}" for t in DATES)
              + f"{sub.d23.mean():9.2f}{sub.d34.mean():9.2f}")

    print("\ncrop mix (area share). Rice/Cotton are measured; the other three are the")
    print("district mix applied to the residual, so their agreement is by construction:")
    area = df.groupby("crop_type").area_ha.sum()
    for crop in CROPS:
        measured = crop in set(tier1.values())
        print(f"  {crop:<10} {int((df.crop_type == crop).sum()):3d} farms  "
              f"{area.get(crop, 0.0):6.1f} ha  {area.get(crop, 0.0) / df.area_ha.sum():5.1%}"
              f"  (district {CROP_MIX_REFERENCE[crop]:.0%})"
              f"  {'measured' if measured else 'allocated'}")

    print("\nseparability — is the clustering resolving real structure?")
    spread = df.groupby("crop_type")["level_T3"].mean()
    print(f"  between-crop spread in peak-canopy gamma0 : {spread.max() - spread.min():.2f} dB")
    print(f"  farm-level speckle noise, median N={int(df.core_px.median())} px : "
          f"{4.34 / np.sqrt(df.core_px.median()):.3f} dB")
    print(f"  low-confidence farms (margin < 0.05) : {int((df.crop_margin < 0.05).sum())}")
    # The dark-flood rice rule, closed twice in Round 1 and re-tested here at farm level
    # so the write-up's "not usable and not used" is a measurement rather than a memory.
    print(f"  dark-flood rice rule, min(T1,T2)->T3 rise : "
          f"{-df.flood_depth.median():+.2f} dB median (needs +6 dB) — not usable")

    # S14. The tier-2 cut used to fall inside a block of 403 plots that all carried the
    # same clipped value, so the Bajra/Maize split was settled by sort order. On the signed
    # axis this is what is left of that, measured rather than asserted.
    arb = tier2_arbitrariness(df, df.index[df["tier2_flag"]].to_numpy())
    print(f"\ntier-2 ordering — how much of the allocation is decided by tied keys? (S14)")
    print(f"  the clipped axis this one replaced tied {arb['n_tied_clipped']} of "
          f"{arb['n_tier2']} allocated plots on one value\n"
          f"  ({arb['area_tied_clipped']:.1f} ha), and the cut fell inside that block. "
          f"{TIER2_AXIS} separates the same\n  plots across "
          f"{arb['n_distinct_in_that_block']} distinct values.")
    print(f"  axis {TIER2_AXIS}: {arb['n_tied']} of {arb['n_tier2']} allocated plots still "
          f"share an exact value\n"
          f"  with another ({arb['area_tied']:.1f} of {arb['tier2_area']:.1f} ha; largest "
          f"tied run {arb['largest_tie_run']} plots)")
    print(f"  cohort area over {arb['n_perm']} permutations of the tie order, ha:")
    for crop, (lo, hi_) in arb["area_spread"].items():
        print(f"    {crop:<10} {lo:6.2f} – {hi_:6.2f}   (shipped "
              f"{df.loc[df.crop_type == crop, 'area_ha'].sum():6.2f})")
    # Pre-registered prediction 2, scored here. `t5_anomaly` is the residual of the 29 Oct
    # pass from the T4-T6 interpolation -- soil exposure measured through 63 mm of rain --
    # and no label was built from it, so it is entitled to disagree.
    t5 = df.groupby("crop_type")["t5_anomaly"].median()
    got = [c for c in t5.loc[TIER2_ORDER].sort_values(ascending=False).index]
    print("  pre-registered prediction 1: the tier-2 cohorts separate better on optical "
          "NDVI residualised\n    against the ranking axis than the clipped axis managed "
          "(eta2_resid 0.0274, F 10.30) — scored in\n    the SENTINEL-2 VALIDATION block "
          "below, not here.")
    print(f"  pre-registered prediction 2: t5_anomaly (soil exposure on 29 Oct, in no "
          f"label) orders\n    {' > '.join(TIER2_ORDER[::-1][::-1])} most-exposed first. "
          f"Measured medians, dB: "
          + ", ".join(f"{c} {t5[c]:+.2f}" for c in CROPS if c in t5.index)
          + f"\n    observed order {' > '.join(got)} — "
          + ("AGREES" if got == TIER2_ORDER else "CONTRADICTS"))

    if not with_stability:
        return
    print("\nstability — does the labelling survive changes to the clustering setup?")
    print("  'tier1' column is the one that matters: it is the part being claimed.")
    hi = df.crop_confidence == "high"
    for nc, ns in ((N_CLUSTERS, 5), (N_CLUSTERS, 40), (7, N_SEEDS), (11, N_SEEDS)):
        alt = run(features_csv, nc, ns)[0]
        both_hi = hi & (alt.crop_confidence == "high")
        t1 = (alt.crop_type[both_hi] == df.crop_type[both_hi]).mean() if both_hi.any() else np.nan
        print(f"  n_clusters={nc:<3} n_seeds={ns:<3} all {(alt.crop_type == df.crop_type).mean():5.1%}"
              f"   tier1 {t1:5.1%} over {int(both_hi.sum())} farms"
              f"   (high-conf area {alt.area_ha[alt.crop_confidence == 'high'].sum():5.1f} ha"
              f" vs {df.area_ha[hi].sum():5.1f})")


if __name__ == "__main__":
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    work = os.path.join(root, "work")
    # Not farm_features.csv. The six-date descriptors this module now clusters on are
    # produced by `phenology`, whose output is that frame plus the phenology columns.
    features = os.path.join(work, "farm_phenology.csv")
    out = run(features)
    out[0].to_csv(os.path.join(work, "farm_crops.csv"), index=False)
    report(features, *out)
    print("\nsensitivity of the cotton area to COTTON_NOV_DB:")
    print(cotton_sensitivity(out[0], out[6]).to_string(index=False))
