"""Assemble the Kaggle notebook from the real modules in `src/`.

Round 2 kept its modules only as `%%writefile` cells inside its notebook. That makes local
iteration painful -- there is nothing to import, nothing to unit-test, and nothing a linter
can see -- and it lets a module and the notebook drift apart with nothing to notice.

Round 3 inverts it. `src/*.py` is the source of truth, this script is the only thing that
writes the notebook, and the notebook's code cells are those files verbatim. A module and
the notebook therefore cannot disagree: if they did, the fix is to re-run this script.

The generator is idempotent. Cell ids are derived from the cell's role rather than
randomised, no execution counts or outputs are emitted, and the JSON is written with a
fixed separator and indent, so running it twice on unchanged sources produces a
byte-identical file and `git diff` shows only what actually changed.

    python build_notebook.py            # writes sokhda_yield_forecast.ipynb
    python build_notebook.py --check    # exits 1 if the notebook is out of date
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "src")
NOTEBOOK = os.path.join(ROOT, "sokhda_yield_forecast.ipynb")

# Round 2's crop labels reach the notebook as an ATTACHED KAGGLE DATASET, not as a cell.
# They were a `%%writefile work/round2_crops.csv` cell for one run, which put a 15 KB data
# table in the middle of a listing whose whole claim is that every cell is a real module.
# A dataset is what Kaggle has for data; `geocode.round2_crops_path()` prefers
# `/kaggle/input/*/round2_crops.csv` and names it in the raise if it is missing.

# Dependency order: a module may only import ones above it. `pipeline` is last because it
# imports everything. This is the order the cells are written to disk in, which matters
# because a Kaggle reader executes top to bottom and the writefile cells must all have run
# before the pipeline cell imports anything.
MODULES = [
    "geocode",
    "coreg_calib",
    "gates",
    "farm_features",
    "scene_diagnostics",
    "season_context",
    "s2_ndvi",
    "phenology",
    "canopy_sign",
    "crop_type",
    "yield_forecast",
    "backtest",
    "validate",
    "s1_audit",
    "submit",
    "figures",
    "pipeline",
]

TITLE = """\
# Sokhda kharif 2025 — final yield forecast from six Capella X-band passes

**ANRF AISEHack 2.0, Round 3.** 966 farm plots, one village (Sokhda, Vadodara district,
Gujarat), six Capella X-band HH SLC acquisitions from 6 June to 12 November 2025, no ground
truth and no leaderboard.

    Y_final(plot) = Y_ref(crop, kharif 2025) x a(season-complete canopy integral)

`Y_ref` is the official Gujarat state kharif yield for 2025-26 (DA&FW Directorate of
Economics and Statistics, five-year advance estimates). `a` is a bounded, cohort-centred
response to the one per-plot SAR quantity in this pipeline that has independent external
support: the season integral of each plot's backscatter departure from its own June bare
soil, which correlates at rho = +0.564 with Sentinel-2 NDVI on 813 plots and is positive on
all five crops.

Because there is no label to fit, **validation is the deliverable**, and it runs inside this
notebook rather than beside it:

- a **leave-future-out back-test** — fit on T1-T4, predict the withheld 12 November pass,
  scored against four baselines with 2000-sample bootstrap intervals;
- a **pre-registered canopy-sign arbitration** against same-day Sentinel-2, whose expected
  signs are written as a module constant above the code that opens the optical file;
- **two reserved Sentinel-2 dates** (12 December 2025, 16 January 2026) that an assertion
  in the run forbids any module but the validator from reading;
- **confound controls**: a look-direction test for the one right-looking pass, a
  scene-level radiometric drift control, and Moran's I with a permutation null.

Thirteen claims in this pipeline were written down before the data that could test them was
opened. **Seven were contradicted**, one was not met, five held. Every one is recorded as a
finding and the model was changed to match, not the other way round — four of the seven
deleted a term, a rule or a whole module. The ledger is in `docs/research_log.md`.

## How this notebook is put together

Every code cell below is a real file from the project's `src/` directory, written verbatim
by `build_notebook.py`. Nothing here is notebook-only, and nothing in `src/` is missing from
here. The final cell runs the whole chain end to end.
"""

SETUP = '''\
import os, sys, subprocess

# Kaggle mounts the competition at one of two paths depending on the kernel image; geocode
# probes both, plus SAR_DATA_DIR, plus the local repo layout. Nothing is downloaded.
os.makedirs("src", exist_ok=True)
os.makedirs("work", exist_ok=True)
if "src" not in sys.path:
    sys.path.insert(0, "src")

for mod in ("osgeo", "numpy", "pandas", "scipy", "sklearn", "matplotlib"):
    __import__(mod)
from osgeo import gdal
gdal.UseExceptions()
gdal.SetCacheMax(256 * 1024 * 1024)          # six 1 m scenes; the default cache thrashes
print("GDAL", gdal.__version__)
'''

RUN = '''\
# The full chain: calibrate and geocode six SLCs, gate the warp, build farm statistics,
# measure the canopy sign against optical, label crops, fetch the season reference, forecast,
# back-test, validate, aggregate, draw the gallery.
#
# `with_s2=False` drops every external validation but leaves the forecast identical -- the
# forecast itself consumes no optical data. Use it if this kernel has no internet.
import pipeline

fc = pipeline.run(with_s2=True, make_figures=True)
'''

SHOW = '''\
import pandas as pd
from IPython.display import display, Image

for name in ("farm_forecast", "village_summary", "zone_summary"):
    df = pd.read_csv(f"outputs/{name}.csv")
    print(f"\\noutputs/{name}.csv   {len(df)} rows x {len(df.columns)} columns")
    display(df.head(8))

for fig in ("cover", "sar_composite", "yield_forecast_map", "crop_type_map",
            "trajectories", "canopy_departure", "canopy_sign", "model_chain",
            "extrapolation", "backtest", "reserved_optical", "zone_map",
            "village_summary", "uncertainty_budget"):
    display(Image(filename=f"figures/{fig}.png"))
'''


ROUND2_NOTE = """\
## Round 2's crop labels

Three modules below score against the crop labels this team produced in Round 2, and each
has a reason that is about validity rather than convenience:

- `canopy_sign` measures the canopy sign against the Round 2 labels because the sign was
  measured before the Round 3 labels existed, and re-running it against labels the sign
  itself helped produce would be circular.
- `backtest` uses them because they were derived from T1-T4 alone, so no information about
  the withheld 12 November pass can reach a predictor through its label.
- `yield_forecast.label_sensitivity` swaps them in deliberately, to measure how much of the
  village total is a labelling choice.

This is our own model output from a previous round -- `farm_id`, `crop_type`,
`crop_confidence`, one row per plot -- and not competition data. It is **attached to this
notebook as a Kaggle dataset** rather than written from a cell: every other cell here is a
real module from `src/`, and a data table pasted among them would not be.

`geocode.round2_crops_path()` resolves it, preferring `/kaggle/input/*/round2_crops.csv`,
then a `ROUND2_CROPS` override, then a sibling `Round 2/` directory. It raises and names
every candidate it tried if none is present -- the three tests above are validation gates,
and a run that quietly skipped them would be worse than one that stops.
"""


def _lines(text: str) -> list[str]:
    """Notebook source is a list of lines, each keeping its newline except the last."""
    out = text.splitlines(keepends=True)
    if out and out[-1].endswith("\n"):
        out[-1] = out[-1][:-1]
    return out


def _cell(kind: str, key: str, text: str) -> dict:
    cell = {
        "cell_type": kind,
        "id": hashlib.sha1(key.encode()).hexdigest()[:8],
        "metadata": {},
        "source": _lines(text),
    }
    if kind == "code":
        cell["execution_count"] = None
        cell["outputs"] = []
    return cell


def build() -> dict:
    cells = [_cell("markdown", "title", TITLE),
             _cell("code", "setup", SETUP),
             _cell("markdown", "modules", "## The pipeline modules\n\n"
                   "Each cell writes one file from `src/`, verbatim. Read them as the "
                   "documentation of the method; the docstrings carry the reasoning and "
                   "the measurements that set every constant.\n")]

    cells.append(_cell("markdown", "r2-md", ROUND2_NOTE))

    for name in MODULES:
        path = os.path.join(SRC, f"{name}.py")
        if not os.path.isfile(path):
            raise FileNotFoundError(f"{path} is listed in MODULES but does not exist")
        with open(path) as fh:
            body = fh.read()
        cells.append(_cell("code", f"mod:{name}",
                           f"%%writefile src/{name}.py\n{body}"))

    stray = sorted(f[:-3] for f in os.listdir(SRC)
                   if f.endswith(".py") and f[:-3] not in MODULES)
    if stray:
        raise RuntimeError(f"src/ has modules the notebook would omit: {stray}. "
                           "Add them to MODULES or delete them.")

    cells.append(_cell("markdown", "run-md", "## Run\n"))
    cells.append(_cell("code", "run", RUN))
    cells.append(_cell("markdown", "show-md",
                       "## The shipped tables and the gallery\n"))
    cells.append(_cell("code", "show", SHOW))

    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python",
                           "name": "python3"},
            "language_info": {"name": "python", "version": "3.11"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def render(nb: dict) -> str:
    return json.dumps(nb, indent=1, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if the notebook is stale rather than rewriting it")
    args = ap.parse_args()

    text = render(build())
    if args.check:
        current = open(NOTEBOOK).read() if os.path.isfile(NOTEBOOK) else ""
        if current != text:
            sys.exit(f"{NOTEBOOK} is out of date; run `python build_notebook.py`")
        print(f"{NOTEBOOK} is up to date")
    else:
        with open(NOTEBOOK, "w") as fh:
            fh.write(text)
        n_code = sum(c["cell_type"] == "code" for c in build()["cells"])
        print(f"wrote {NOTEBOOK}: {len(build()['cells'])} cells "
              f"({n_code} code), {len(text) / 1024:.0f} KB, "
              f"{len(MODULES)} modules")
