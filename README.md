# Sokhda kharif 2025 — final yield forecast from six Capella X-band passes

**ANRF AISEHack 2.0, Round 3.** 966 farm plots, one village (Sokhda, Vadodara district,
Gujarat), six Capella X-band HH SLC acquisitions from 6 June to 12 November 2025, no ground
truth and no leaderboard.

    Y_final(plot) = Y_ref(crop, kharif 2025-26) × a(season-complete canopy integral)

Shipped answer: **893.9 t over 447.5 ha, 2.00 t/ha area-weighted.**

Because there is no label to fit, **validation is the deliverable**. Start with
[`writeup.md`](writeup.md) (2000 words) and [`docs/validation_strategy.md`](docs/validation_strategy.md).

---

## What you need

**1. The competition data.** It is *not* in this repository — it is 3.2 GB of Competition Data
and the rules forbid redistributing it. Download it from the competition page:

<https://www.kaggle.com/competitions/anrf-aise-hack-2-0-round-3-sar-crop-yield-forecasting/data>

Unpack it so the directory holds the six `CAPELLA_C14_SM_SLC_HH_*` scene folders plus
`Farm_boundaries_shp/` and `Village_Shp/`, then point the pipeline at it:

```sh
export SAR_DATA_DIR=/path/to/the/unpacked/competition/data
```

`geocode._data_dir()` also finds it automatically at `/kaggle/input/...` on Kaggle, or at a
`Data/` directory beside this one. If none of those resolve it raises and lists every path it
tried — resolution happens at import, so this fails immediately rather than halfway through a
run.

**2. Round 2's crop labels.** Three validation steps score against this team's own Round 2
output — the canopy-sign arbitration, the back-test, and the label-sensitivity term. A copy
ships at [`kaggle_dataset/round2_crops.csv`](kaggle_dataset/round2_crops.csv) (966 rows;
`farm_id`, `crop_type`, `crop_confidence`) and is found automatically. It is our own model
output from a previous round, not competition data. To override:

```sh
export ROUND2_CROPS=/path/to/round2_crops.csv
```

**3. Python 3.11+ and GDAL.** See [`requirements.txt`](requirements.txt) — GDAL needs the
system library installed first and cannot come from pip alone.

```sh
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
pip install "gdal==$(gdal-config --version)"
```

**4. Network,** for the Sentinel-2 and NASA POWER fetches — on the first run only. Both are
cached to `work/`, and `work/s2_cache/` holds the STAC search responses as well as the
rasters, so a second run is fully offline. To run with no network at all and no cache, use
`--no-s2`: the forecast is unchanged (it consumes no optical data) but every external
validation is lost, and the run says so.

## Run it

```sh
python src/pipeline.py                    # full chain, ~15 min, writes outputs/ and figures/
python src/pipeline.py --no-s2            # no network; forecast only, no external validation
python -m pytest tests/ -q                # 50 tests
python build_notebook.py --check          # verify the notebook matches src/
python audit_writeup.py --trace writeup.md   # every number traced to the shipped log
```

The tests import `geocode` and `farm_features`, which resolve the data at import time, so they
need `SAR_DATA_DIR` set too.

## What is here

```
src/                 the pipeline. 16 modules, executed in the order listed in pipeline.py
tests/               50 tests, each one a defect that actually happened
docs/                methodology, validation strategy, leakage analysis, research log
kaggle_dataset/      round2_crops.csv and s1_per_farm.csv, both found automatically
outputs/             the three shipped tables: farm, village, zone
figures/             the 15-figure gallery, including the pre-registration ledger
logs/pipeline_clean.log   the shipped run every number in the write-up is traced to
writeup.md           the 2000-word submission
AGENTS.md            the full development log, S0-S33. Long, and not required reading
docs/judge_report.md an adversarial audit of this submission, including its own defects
sokhda_yield_forecast.ipynb   GENERATED from src/ by build_notebook.py — never edit directly
```

`src/*.py` is the source of truth. The Kaggle notebook is generated from it, so a module and
the notebook cannot disagree; if they ever do, re-run `build_notebook.py`.

## Reading it critically

Every number in `writeup.md` is printed by the run in `logs/pipeline_clean.log`, and
`audit_writeup.py --trace` writes the token-to-log-line mapping to `logs/writeup_trace.txt`.

Seventeen claims were written down before the data that could test them was opened; **nine
were contradicted** and the model or the claim was changed to match. The ledger lives in the
source as `validate.LEDGER`, is printed by every run, and is drawn as `figures/ledger.png`;
the narrative is at the top of [`docs/research_log.md`](docs/research_log.md). [`docs/judge_report.md`](docs/judge_report.md)
is a hostile audit of this submission that found further defects — two false claims in our own
leakage analysis, a p-value that was a resolution floor, and a default argument that had
silently invalidated one of the pre-registered tests. All are corrected in place and
recorded rather than quietly removed; §23 of that report tracks what is closed and what is not.

## Data licence

The competition data is **Competition Use only** and is not redistributed here. External data
used — Sentinel-2 L2A via Earth Search, NASA POWER, DA&FW advance estimates — is public and free
to all participants, as the rules require. Sources are listed in `docs/research_log.md`.
