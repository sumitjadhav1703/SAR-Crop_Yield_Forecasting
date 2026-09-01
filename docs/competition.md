# The competition, verified from source

Verified directly from the Kaggle competition pages and the Kaggle API on 2026-08-25, not
inferred from the brief.

## What is being asked

**ANRF AISEHack 2.0 Round 3: SAR Crop Yield Forecasting**, hosted by GalaxEye. The final
round; six teams carried forward from Round 2.

Produce a **final yield forecast — not a yield-to-date estimate** — for each of 966 farm
plots from the complete six-pass Capella X-band SAR time series, plus village-level
summaries by crop (Rice, Cotton, Maize, Bajra, Groundnut). No ground truth is provided at
plot level, and that is stated as intentional: "part of the challenge is building a
defensible methodology to arrive at plot-level and village-level yield predictions without
labeled targets to fit against directly."

Any methodology is allowed. External data is explicitly permitted — "weather, soil,
historical yield statistics, literature-derived crop coefficients" — provided the write-up
justifies it.

## How it is scored

There is **no leaderboard and no metric**. The Kaggle file listing is 42 files: six Capella
scene folders and two shapefiles. No `train.csv`, no `test.csv`, no `sample_submission.csv`.

> "Since no ground truth yield is provided, submissions are judged on the strength and
> defensibility of the methodology, not a match to a hidden label."

| Criterion | Points |
|---|---|
| Technical Soundness — a rigorous, well-justified method for producing a final forecast from the full six-pass series | 25 |
| Creativity — a novel or thoughtful modelling approach, including sensible use of external data | 15 |
| Plausibility & Defensibility — physically and agronomically plausible values, with clear reasoning and sanity checks given the absence of ground truth | 25 |
| Aggregation — sound logic for rolling plot-level forecasts up to village level, by crop | 15 |
| Documentation & Presentation | 20 |

Fifty of the hundred points are Technical Soundness plus Plausibility & Defensibility, and
both are about whether the reasoning holds rather than whether a number is close to
anything. This is why the project spends its effort on controls and held-out tests.

## What must be submitted

A Kaggle Writeup, submitted (not left as a draft) before **2026-09-03 07:00 UTC**, carrying:

- **Written documentation** ≤ 2000 words covering methodology, external data, assumptions
  made in the absence of ground truth, and how plot forecasts were aggregated to village
  level. No video this round.
- **Media gallery** — maps, charts, temporal backscatter trends. A cover image is required.
  Kaggle crops gallery thumbnails to 16:9.
- **A public notebook** containing the full pipeline. A private notebook attached to a
  public write-up is made public automatically after the deadline.
- **A 10-minute PowerPoint** for the Grand Finale in Goa, 2–3 September 2026.

## What the rules constrain

- Competition Data is **"Competition Use only"**: it must not be transmitted, duplicated,
  published or redistributed to non-participants. No SAR pixels leave the notebook.
- External data must be **publicly available at no cost to all participants**. Everything
  used here qualifies: Sentinel-2 L2A through Earth Search's anonymous STAC endpoint, NASA
  POWER, CHIRPS, and the DA&FW Directorate of Economics & Statistics advance estimates.

## What changed from Round 2, and what did not

Round 2 asked for yield-to-date as of 13 October on four passes. Its yield equation carried
a hand-set per-crop constant `g` discounting the unobserved remainder of the season —
Cotton 0.45, Bajra 1.00. **Round 3 replaces that constant with measurement.** Six dates let
each plot's season integral be closed by observation where the crop has finished, and
projected with a stated `extrapolated_fraction` where it has not.

What did not change: the AOI, the 966 plots, the single village, or the absence of labels.
