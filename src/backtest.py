"""Leave-future-out back-test: fit on T1-T4, predict T6, score against what happened.

This is the headline validation of the round, and it exists because of a hard constraint:
there is no ground-truth yield, so no claim about forecast accuracy can be made by
comparison with labels. What CAN be done is to withhold the future the stack already
contains. Round 2 had exactly four acquisitions, T1 to T4, ending 13 October. Round 3 has
two more. So the chain can be re-run as if it were still 13 October, asked to project
forward, and scored against 12 November -- on this exact AOI, these exact plots, this exact
instrument.

That is real, quantified forecast skill. It is the direct answer to "how do you know your
forecast is any good with no labels", and nothing else available in this competition comes
close to it.

=== WHAT IS BEING TESTED ===

Not the yield number -- there is nothing to score that against. What is tested is the one
piece of machinery that turns an observed season into a forecast: the projection rule in
`yield_forecast.season_integral`, which carries a plot's last observed canopy forward along
its own last limb, never upward, until its crop's calendar harvest. Applied from T4 that
rule makes a falsifiable statement about 12 November, and here it is falsified or not.

=== THE LEAKAGE RULES, STATED BEFORE THE NUMBERS ===

  * Crop labels come from ROUND 2, which derived them from T1-T4 alone. The Round 3 labels
    use `canopy_end_db` at T6 and would leak the answer straight into the predictor.
  * The June anchor uses T1 and T2 only, which are inside the training window.
  * The T3->T4 limb is the only slope any predictor may use.
  * T5 is excluded entirely. Its level in `farm_features` is the T4-T6 interpolation, not a
    measurement, so scoring against it would be scoring against T6 with extra steps.

=== TWO TARGETS, BECAUSE ONE OF THEM QUIETLY ASSUMES SOMETHING ===

  departure_T6   the plot's canopy relative to its own June soil, with the district-wide
                 bare-soil drift at T6 removed. Removing that drift means knowing the
                 scene level on 12 November, which a forecaster standing on 13 October
                 does not. It is measured off non-farm ground rather than off the farms,
                 so it is not the answer being leaked -- but it is not free either.
  g0_db_T6       the raw level. Nothing about 12 November is assumed. Harder, and the
                 honest upper bound on what a real forecast could have done.

Both are reported. Quoting only the first would overstate the result.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

import geocode
from geocode import DOY
from yield_forecast import HARVEST_DOY

TRAIN_DATES = ["T1", "T2", "T3", "T4"]
# District-wide bare-soil drift at T6 relative to T1, dB, as measured by
# `phenology.bare_soil_drift` off 16.5 M AOI pixels belonging to no farm polygon. Used only
# by the `level_driftaware` control below.
DRIFT_T6_DB = 1.65
TARGET_DATE = "T6"
N_BOOTSTRAP = 2000
RANDOM_STATE = 20260826


def _predictors(df: pd.DataFrame) -> dict:
    d3, d4 = df["departure_T3"].to_numpy(float), df["departure_T4"].to_numpy(float)
    span = float(DOY["T4"] - DOY["T3"])
    horizon = float(DOY[TARGET_DATE] - DOY["T4"])
    slope = (d4 - d3) / span
    crop = df["crop_r2"].to_numpy()
    harvest = pd.Series(crop).map(HARVEST_DOY).to_numpy(float)

    # B4, the shipped rule: zero once the crop's calendar harvest has passed, otherwise the
    # last observation carried FLAT. The decaying variant is kept as B5 so the comparison
    # that produced this design stays runnable rather than becoming a claim in a comment.
    model = np.where(harvest <= DOY[TARGET_DATE], 0.0, np.clip(d4, 0.0, None))

    decay = np.minimum(slope, 0.0)
    days = np.clip(np.minimum(harvest, DOY[TARGET_DATE]) - DOY["T4"], 0.0, None)
    decayed = np.clip(d4 + decay * days, 0.0, None)
    decayed = np.where(harvest <= DOY["T4"], 0.0, decayed)

    return {
        "B1 persistence": d4,
        "B2 cohort mean at T4": pd.Series(d4).groupby(pd.Series(crop)).transform("mean")
                                  .to_numpy(),
        "B3 linear extrapolation": d4 + slope * horizon,
        "B4 shipped rule (flat hold)": model,
        "B5 decaying limb (rejected)": decayed,
    }


def _scores(truth: np.ndarray, pred: np.ndarray) -> dict:
    e = pred - truth
    return {"MAE": float(np.mean(np.abs(e))), "RMSE": float(np.sqrt(np.mean(e ** 2))),
            "bias": float(np.mean(e))}


def _skill_ci(truth, pred, base, rng, n=N_BOOTSTRAP) -> tuple:
    """Bootstrap CI on the skill score 1 - MSE_model / MSE_baseline, resampling plots."""
    idx = np.arange(len(truth))
    out = np.empty(n)
    for i in range(n):
        s = rng.choice(idx, size=len(idx), replace=True)
        mm = np.mean((pred[s] - truth[s]) ** 2)
        bb = np.mean((base[s] - truth[s]) ** 2)
        out[i] = 1.0 - mm / bb if bb > 0 else np.nan
    return float(np.nanpercentile(out, 2.5)), float(np.nanpercentile(out, 97.5))


def run(df: pd.DataFrame, target: str = "departure") -> pd.DataFrame:
    """Score every predictor against the withheld date. `target` is 'departure' or 'level'."""
    preds = _predictors(df)
    if target == "departure":
        truth = df[f"departure_{TARGET_DATE}"].to_numpy(float)
    elif target == "level_driftaware":
        # Same as "level", but every predictor is told the district-wide bare-soil drift at
        # T6. This is the control for a suspicion the plain "level" result invites: B4
        # predicts a higher canopy than persistence does, and the raw level at T6 is +1.65 dB
        # above T1 district-wide, so B4 could be winning by being biased in the direction
        # that happens to offset a drift NEITHER predictor models. Handing every predictor
        # the drift removes that route to a win.
        import phenology, json
        anchor = df[[f"g0_db_filled_{c}" for c in ("T1", "T2")]].to_numpy(float).mean(axis=1)
        truth = df[f"g0_db_filled_{TARGET_DATE}"].to_numpy(float)
        preds = {k: v + anchor + DRIFT_T6_DB for k, v in preds.items()}
    elif target == "level":
        # Same predictors, re-expressed as a level by adding back each plot's own anchor.
        # The anchor is June-only, so this adds no knowledge of 12 November.
        anchor = df[[f"g0_db_filled_{c}" for c in ("T1", "T2")]].to_numpy(float).mean(axis=1)
        truth = df[f"g0_db_filled_{TARGET_DATE}"].to_numpy(float)
        preds = {k: v + anchor for k, v in preds.items()}
    else:
        raise ValueError(f"unknown target {target!r}")

    ok = np.isfinite(truth) & np.all([np.isfinite(v) for v in preds.values()], axis=0)
    truth = truth[ok]
    rng = np.random.default_rng(RANDOM_STATE)
    base = preds["B1 persistence"][ok]

    rows = []
    for name, p in preds.items():
        p = p[ok]
        s = _scores(truth, p)
        s["predictor"] = name
        s["n"] = int(ok.sum())
        s["skill_vs_persistence"] = 1.0 - np.mean((p - truth) ** 2) / np.mean(
            (base - truth) ** 2)
        s["ci_lo"], s["ci_hi"] = _skill_ci(truth, p, base, rng)
        rows.append(s)
    return pd.DataFrame(rows)[["predictor", "n", "MAE", "RMSE", "bias",
                               "skill_vs_persistence", "ci_lo", "ci_hi"]]


def per_crop(df: pd.DataFrame, target: str = "departure") -> pd.DataFrame:
    rows = []
    for crop, g in df.groupby("crop_r2"):
        if len(g) < 20:
            continue
        r = run(g, target)
        best = r.loc[r.RMSE.idxmin()]
        model = r[r.predictor == "B4 shipped rule (flat hold)"].iloc[0]
        rows.append({"crop": crop, "n": len(g), "model_RMSE": model.RMSE,
                     "model_skill": model.skill_vs_persistence,
                     "ci_lo": model.ci_lo, "ci_hi": model.ci_hi,
                     "best_predictor": best.predictor})
    return pd.DataFrame(rows)


def report(df: pd.DataFrame) -> dict:
    print("LEAVE-FUTURE-OUT BACK-TEST -- fit on T1-T4 (6 Jun to 13 Oct), predict T6 (12 Nov)")
    print(f"crop labels are Round 2's, derived from T1-T4 only, so no T6 information "
          f"reaches any predictor")
    out = {}
    for target, label in (("departure", "canopy departure from each plot's own June soil"),
                          ("level", "raw gamma0 level -- nothing about 12 Nov assumed"),
                          ("level_driftaware",
                           "raw level, every predictor given the T6 scene drift (control)")):
        r = run(df, target)
        out[target] = r
        print(f"\ntarget: {label}   (dB)")
        print("  predictor                     n     MAE    RMSE    bias   skill vs "
              "persistence [95% CI]")
        for _, x in r.iterrows():
            print(f"  {x.predictor:<28s}{x.n:5d}  {x.MAE:6.3f}  {x.RMSE:6.3f}  "
                  f"{x.bias:+6.3f}   {x.skill_vs_persistence:+7.3f}  "
                  f"[{x.ci_lo:+.3f}, {x.ci_hi:+.3f}]")
    ship = shipped_configuration(df)
    out["shipped"] = ship
    print("\nrestricted to where the projection rule actually changes the answer")
    print("  subset                                              n  model  persist   skill")
    for _, x in ship.iterrows():
        print(f"  {x.subset:<50s}{x.n:5d}  {x.model_RMSE:5.3f}  {x.persistence_RMSE:7.3f}  "
              f"{x.skill:+6.3f}")

    print("\nper crop, on the departure target: does the shipped rule beat persistence "
          "everywhere or only on average?")
    pc = per_crop(df)
    out["per_crop"] = pc
    print("  crop         n   model RMSE   skill [95% CI]           best predictor")
    for _, x in pc.iterrows():
        print(f"  {x.crop:<10}{x.n:5d}   {x.model_RMSE:9.3f}   {x.model_skill:+.3f} "
              f"[{x.ci_lo:+.3f}, {x.ci_hi:+.3f}]   {x.best_predictor}")
    return out


def shipped_configuration(df: pd.DataFrame) -> pd.DataFrame:
    """The back-test restricted to the case the shipped model actually faces.

    This matters and it is easy to miss. In the shipped forecast the projection rule fires
    for cotton and for nothing else -- every other crop's calendar harvest falls on or
    before 12 November, so its `extrapolated_fraction` is exactly 0 and no projection is
    made. Moving the vantage point back to 13 October forces the rule to project across a
    harvest for four crops it never has to project across in production.

    So the whole-stack table below answers "would this rule have worked from October", and
    this function answers the narrower question the shipped model depends on: when the rule
    IS applied, does it beat carrying the last observation forward?
    """
    preds = _predictors(df)
    truth = df[f"departure_{TARGET_DATE}"].to_numpy(float)
    fires = ~np.isclose(preds["B4 shipped rule (flat hold)"], preds["B1 persistence"])
    rows = []
    for label, m in (("rule fires (projection differs from persistence)", fires),
                     ("rule is silent (identical to persistence)", ~fires)):
        if m.sum() < 10:
            continue
        t, p, b = truth[m], preds["B4 shipped rule (flat hold)"][m], preds["B1 persistence"][m]
        rows.append({"subset": label, "n": int(m.sum()),
                     "model_RMSE": float(np.sqrt(np.mean((p - t) ** 2))),
                     "persistence_RMSE": float(np.sqrt(np.mean((b - t) ** 2))),
                     "skill": 1.0 - np.mean((p - t) ** 2) / np.mean((b - t) ** 2)})
    return pd.DataFrame(rows)


def frame() -> pd.DataFrame:
    """The frame every predictor is scored on.

    Round 2's crop labels on purpose: they were derived from T1-T4 alone, so no information
    about the withheld 12 November pass can reach a predictor through its label. Measured
    plots only -- an imputed plot's "observation" at T6 is a neighbour's, which would score
    the imputation rather than the forecast.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    phen = pd.read_csv(os.path.join(root, "work", "farm_phenology.csv"))
    r2 = pd.read_csv(geocode.round2_crops_path(),
                     usecols=["farm_id", "crop_type"]).rename(columns={"crop_type": "crop_r2"})
    out = phen.merge(r2, on="farm_id", how="inner")
    return out[out.data_quality == "measured"]


if __name__ == "__main__":
    report(frame())
